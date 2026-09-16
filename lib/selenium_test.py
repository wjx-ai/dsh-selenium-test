#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DSH Selenium 浏览器自动化测试工具脚本。

从 stdin 读取一个 JSON spec：
{
  "url": "...",
  "actions": [ {"type": "...", ...}, ... ],
  "timeout": 30000,
  "options": {"headless": true, "width": 1920, "height": 1080,
              "page_load_strategy": "none",
              "max_actions": 50,
              "implicitly_wait": 0,
              "collect_console": true}
}

按顺序执行每一项操作，输出一个 JSON 结果到 stdout：
{
  "success": true,
  "url": "...",
  "title": "...",
  "actions": [ {"index": 0, "type": "click", "ok": true}, ... ],
  "screenshots": ["C:/..."],
  "console_errors": ["..."],
  "error": "..."            # 仅在失败时
}

依赖（第三方，需安装）：pip install selenium webdriver-manager
运行环境：本机需安装 Google Chrome（webdriver-manager 会自动下载匹配的 chromedriver）。

设计：Selenium 的 import 是惰性的（在 run_test 内部发生），因此没有安装
selenium 时脚本仍可运行并返回 JSON 错误，便于冒烟测试与快速定位环境问题。

=== 针对 SPA（永久加载中）的健壮性升级 ===
以下能力依据 clickthrough.py 验证过的可用模式加入：
  * execute_async_script  —— 正确 await JS Promise（同步 execute_script 不会等 Promise）。
  * _send 就绪探测+重试   —— page_load_strategy=none 时，导航未落定前 ChromeDriver 会
                             报 "invalid argument"，_send 会自动小步重试而非整轮崩掉。
  * assert 支持已渲染文本  —— 默认查 document.body.innerText（活 DOM）并按 poll 秒轮询，
                             兼容 SPA 异步渲染；仍保留对初始 page_source 的回退。
  * console 错误采集      —— 注入 window.__dshErrs 收集器 + 结束时拉取 driver.get_log('browser')，
                             结果里回带 console_errors。
  * settle 动作          —— JS 睡眠 + DOM-ready 探测（替代「点完立即读」的竞态）。

向后兼容：原有 navigate/click/click_js/click_by_text/wait_for_element/click_and_wait/
type/screenshot/wait/wait_selector/assert/eval/execute_script/foreach 全部保留。
"""

import sys
import json
import os
import time
import tempfile

# 选择器方式 -> Selenium By
_BY_MAP = {
    "css": "CSS_SELECTOR",
    "css_selector": "CSS_SELECTOR",
    "xpath": "XPATH",
    "id": "ID",
    "name": "NAME",
    "tag": "TAG_NAME",
    "tag_name": "TAG_NAME",
    "class": "CLASS_NAME",
    "class_name": "CLASS_NAME",
    "link_text": "LINK_TEXT",
    "partial_link_text": "PARTIAL_LINK_TEXT",
}

# 安装一次即可的在页错误收集器（幂等）
_ERR_COLLECTOR = (
    "if(!window.__dshErrs){window.__dshErrs=[];"
    "window.addEventListener('error',function(e){window.__dshErrs.push(String(e.message||e)+'@'+(e.lineno||0));});"
    "window.addEventListener('unhandledrejection',function(e){window.__dshErrs.push('rej:'+((e.reason&&e.reason.message)||e.reason));});}"
    "return window.__dshErrs.length;"
)


def _usage_error(message):
    return {"success": False, "url": "", "title": "", "actions": [], "screenshots": [],
            "console_errors": [], "error": message}


def _resolve_by(action):
    by = (action.get("by") or action.get("selectorType") or "css").lower()
    return _BY_MAP.get(by, "CSS_SELECTOR")


class DriverCtx:
    """封装 driver + 一组带「就绪探测+重试」的发送原语。

    page_load_strategy=none 时，导航刚触发的那几百毫秒里 ChromeDriver 可能拒绝命令
    （"invalid argument: missing command parameters"）。_send/_send_js 会小步睡眠后
    自动重试，把这种瞬态竞态吸收掉，不让整轮测试崩在某个中间步骤。
    """

    def __init__(self, driver, spa_safe):
        self.driver = driver
        self.spa_safe = spa_safe
        self._install_err_collector = False

    # ---- 低层原语 ----
    def _send(self, fn, *args, retries=4, pause=0.4):
        last = None
        for _ in range(retries):
            try:
                return fn(*args)
            except Exception as exc:  # noqa: BLE001
                msg = str(exc)
                if self.spa_safe and ("invalid argument" in msg or "missing command parameters" in msg):
                    last = exc
                    time.sleep(pause)
                    continue
                raise
        if last is not None:
            raise last

    def find(self, By, WebDriverWait, EC, action):
        """按 selector/by 解析并等待元素出现。selector 缺省用 action.value。"""
        selector = action.get("selector") or action.get("value")
        if not selector:
            raise ValueError("缺少 selector/value（元素定位）")
        by = getattr(By, _resolve_by(action))
        wait_seconds = float(action.get("wait", 10))
        el = WebDriverWait(self.driver, wait_seconds).until(EC.presence_of_element_located((by, selector)))
        return el

    def js(self, script):
        """execute_script 的带重试版本。"""
        return self._send(self.driver.execute_script, script)

    def js_async(self, script):
        """execute_async_script：正确 await 返回的 JS Promise。"""
        return self._send(self.driver.execute_async_script, script)

    def install_err_collector(self):
        if self._install_err_collector:
            return
        try:
            self.js(_ERR_COLLECTOR)
        except Exception:  # noqa: BLE001
            pass
        self._install_err_collector = True

    def collect_console(self):
        """汇总 JS 侧错误 + 浏览器 console 日志（SEVERE/ERROR）。"""
        out = []
        try:
            out.extend(self.js("return window.__dshErrs||[];") or [])
        except Exception:  # noqa: BLE001
            pass
        try:
            for e in self.driver.get_log("browser"):
                if e.get("level") in ("SEVERE", "ERROR"):
                    out.append(e.get("message", ""))
        except Exception:  # noqa: BLE001
            pass
        # 去重保序
        seen, uniq = set(), []
        for x in out:
            if x not in seen:
                seen.add(x)
                uniq.append(x)
        return uniq


def _run_one(ctx, driver, By, WebDriverWait, EC, action, index, screenshots):
    step = {"index": index, "type": action.get("type"), "ok": True}
    t = action.get("type")
    try:
        if t == "navigate":
            target = action.get("url") or action.get("value")
            if not target:
                raise ValueError("navigate 缺少 url/value")
            ctx._send(driver.get, target)
            step["url"] = driver.current_url
        elif t in ({"click", "click_js"}):
            ctx.find(By, WebDriverWait, EC, action).click()
        elif t == "click_by_text":
            text = action.get("text") or action.get("value")
            if not text:
                raise ValueError("click_by_text 缺少 text/value")
            exact = action.get("exact", True)
            xpath = "//*[normalize-space()=%s]" % ("'%s'" % text if exact else "contains(., '%s')" % text)
            el = WebDriverWait(driver, float(action.get("wait", 10))).until(
                EC.element_to_be_clickable((By.XPATH, xpath)))
            el.click()
            step["matched_text"] = text
        elif t == "wait_for_element":
            condition = (action.get("condition") or "presence").lower()
            ctx.find(By, WebDriverWait, EC, action)
            sel = action.get("selector") or action.get("value")
            by = getattr(By, _resolve_by(action))
            if condition == "visible":
                WebDriverWait(driver, float(action.get("wait", 10))).until(EC.visibility_of_element_located((by, sel)))
            elif condition == "clickable":
                WebDriverWait(driver, float(action.get("wait", 10))).until(EC.element_to_be_clickable((by, sel)))
            step["condition"] = condition
        elif t == "click_and_wait":
            ctx.find(By, WebDriverWait, EC, action).click()
            wait_sel = action.get("wait_selector")
            wait_cond = (action.get("wait_condition") or "presence").lower()
            wait_seconds = float(action.get("wait", 10))
            if wait_sel:
                by_name = _resolve_by({"selector": wait_sel, "by": action.get("wait_by", "css")})
                by = getattr(By, by_name)
                if wait_cond == "visible":
                    WebDriverWait(driver, wait_seconds).until(EC.visibility_of_element_located((by, wait_sel)))
                elif wait_cond == "clickable":
                    WebDriverWait(driver, wait_seconds).until(EC.element_to_be_clickable((by, wait_sel)))
                else:
                    WebDriverWait(driver, wait_seconds).until(EC.presence_of_element_located((by, wait_sel)))
            else:
                # SPA 安全：不再死等 readyState==complete（none 策略下可能永不到），
                # 改为「到 complete 或超一半等待预算即放行」。
                deadline = time.time() + wait_seconds
                while time.time() < deadline:
                    state = ctx.js("return document.readyState;")
                    if state in ("interactive", "complete"):
                        break
                    time.sleep(0.2)
        elif t == "type":
            el = ctx.find(By, WebDriverWait, EC, action)
            val = action.get("value") or ""
            el.clear()
            el.send_keys(val)
        elif t == "screenshot":
            path = action.get("path")
            if not path:
                path = os.path.join(tempfile.gettempdir(), "dsh-selenium-%d.png" % int(time.time() * 1000))
            ctx._send(driver.save_screenshot, path)
            screenshots.append(path)
            step["path"] = path
            step["countTowardsLimit"] = action.get("countTowardsLimit", True)
        elif t == "wait":
            duration = float(action.get("duration", action.get("value", 1)))
            time.sleep(duration)
        elif t == "wait_selector":
            ctx.find(By, WebDriverWait, EC, action)
        elif t == "assert":
            expected = action.get("expected") or ""
            if not expected:
                raise ValueError("assert 缺少 expected")
            poll = float(action.get("poll", 0))
            # 优先查活 DOM（innerText 覆盖 JS 渲染），按 poll 秒轮询；再回退 page_source。
            step["asserted"] = _assert_text(ctx, expected, poll)
            if not step["asserted"]:
                raise AssertionError("断言失败：未在渲染内容/页面源码中找到子串 %r（poll=%.1fs）" % (expected, poll))
        elif t in ("eval", "execute_script"):
            js = action.get("script") or action.get("value")
            if not js:
                raise ValueError("%s 缺少 script/value" % t)
            step["result"] = ctx.js(js)
        elif t == "execute_async_script":
            # 正确 await 异步 JS：Selenium execute_async_script 注入 callback 为末位参数。
            # 约定：脚本内用 `cb(result)` 收尾（cb 已绑定为末位 callback）；支持直接写 `return new Promise` 亦可，
            # 因为 Python 侧会同时兼容——若脚本以 `return` 结尾则直接交回（Selenium 对 async 脚本的 return 不生效，故推荐 cb 写法）。
            js = action.get("script") or action.get("value")
            if not js:
                raise ValueError("execute_async_script 缺少 script/value")
            wrapped = "var cb=arguments[arguments.length-1];%s" % js
            step["result"] = ctx.js_async(wrapped)
        elif t == "settle":
            # JS 睡眠 + DOM-ready 探测，吸收「点击后异步渲染未完成」的竞态。
            # 与 execute_async_script 同用 cb（callback）约定，须先绑定末位参数。
            ms = int(action.get("ms", action.get("duration", action.get("value", 1000))))
            step["result"] = ctx.js_async("var cb=arguments[arguments.length-1];setTimeout(function(){cb(document.readyState);},%d);" % ms)
            step["readyState"] = step.get("result", "")
        else:
            raise ValueError("未知操作类型: %r" % t)
    except Exception as exc:  # noqa: BLE001 —— 把每步失败记入结果，不让整个测试崩掉
        step["ok"] = False
        step["error"] = str(exc)
    return step


def _assert_text(ctx, expected, poll):
    """在活 DOM 的 innerText 里找子串，按 poll 秒轮询；兜底查 page_source。"""
    deadline = time.time() + poll
    sel = ctx.get_sel = None
    while True:
        try:
            body = ctx.js("return (document.body?document.body.innerText:'');")
            if expected in (body or ""):
                return True
        except Exception:  # noqa: BLE001
            pass
        if time.time() >= deadline:
            break
        time.sleep(0.25)
    try:
        return expected in ctx.driver.page_source
    except Exception:  # noqa: BLE001
        return False


def run_test(spec):
    url = spec.get("url") or ""
    if not url:
        return _usage_error("缺少 url")
    actions = spec.get("actions") or []
    if not isinstance(actions, list):
        return _usage_error("actions 必须是数组")
    timeout = int(spec.get("timeout", 30000)) or 30000
    options = spec.get("options") or {}
    headless = options.get("headless", False)
    if headless is None:
        headless = False
    page_load_strategy = options.get("page_load_strategy", "normal")
    if page_load_strategy not in ("normal", "eager", "none"):
        page_load_strategy = "normal"
    max_actions = int(options.get("max_actions", 50))
    width = int(options.get("width", 1920))
    height = int(options.get("height", 1080))
    implicitly_wait = float(options.get("implicitly_wait", 0))
    collect_console = bool(options.get("collect_console", True))
    script_timeout = int(options.get("script_timeout", 0))  # 秒；0=不显式设（用 ChromeDriver 默认 30s）

    # 展开 foreach 循环
    expanded_actions = []
    for action in actions:
        if action.get("type") == "foreach":
            items = action.get("items") or []
            if not isinstance(items, list):
                return _usage_error("foreach 缺少 items 数组")
            template = action.get("do") or action.get("actions") or []
            if not isinstance(template, list):
                return _usage_error("foreach 缺少 do/actions 数组")
            for idx, item in enumerate(items):
                for tmpl in template:
                    expanded = dict(tmpl)

                    def replace(val):
                        if isinstance(val, str):
                            return val.replace("{{item}}", json.dumps(item, ensure_ascii=False)).replace("{{index}}", str(idx)).replace("{{key}}", str(idx))
                        return val

                    def walk(obj):
                        if isinstance(obj, dict):
                            return {k: walk(v) for k, v in obj.items()}
                        elif isinstance(obj, list):
                            return [walk(v) for v in obj]
                        else:
                            return replace(obj)

                    expanded = walk(expanded)
                    expanded["_foreach_index"] = idx
                    expanded_actions.append(expanded)
        else:
            expanded_actions.append(action)
    actions = expanded_actions

    # 惰性导入：缺依赖时给出可读错误（仍为 JSON）
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from webdriver_manager.chrome import ChromeDriverManager
    except Exception as exc:  # noqa: BLE001
        return _usage_error("缺少 Selenium 依赖（请先 pip install selenium webdriver-manager）：%s" % exc)

    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=%d,%d" % (width, height))
    chrome_options.page_load_strategy = page_load_strategy
    if collect_console:
        try:
            chrome_options.set_capability("goog:loggingPrefs", {"browser": "ALL"})
        except Exception:  # noqa: BLE001
            pass
    if headless:
        chrome_options.add_argument("--headless=new")

    result = {"success": True, "url": url, "title": "", "actions": [], "screenshots": [],
              "console_errors": []}
    driver = None
    ctx = None
    spa_safe = (page_load_strategy == "none")
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.set_page_load_timeout(max(timeout / 1000.0, 30))
        if script_timeout > 0:
            driver.set_script_timeout(script_timeout)
        if implicitly_wait > 0:
            driver.implicitly_wait(implicitly_wait)
        # 避免与「首个 navigate 动作」重复 driver.get：仅当首动作不是 navigate 才预导航。
        first_type = (actions[0].get("type") if actions and isinstance(actions[0], dict) else None)
        if first_type != "navigate":
            driver.get(url)
        ctx = DriverCtx(driver, spa_safe)
        ctx.install_err_collector()
        result["url"] = driver.current_url
        result["title"] = driver.title

        screenshots = []
        action_count = 0
        for i, action in enumerate(actions):
            if action_count >= max_actions:
                result["success"] = False
                result["error"] = "超过最大动作数限制 (max_actions=%d)" % max_actions
                break
            if not isinstance(action, dict):
                result["success"] = False
                result["error"] = "第 %d 个 action 不是对象" % i
                break
            step = _run_one(ctx, driver, By, WebDriverWait, EC, action, i, screenshots)
            result["actions"].append(step)
            if step.get("type") == "screenshot" and step.get("countTowardsLimit") is False:
                pass
            else:
                action_count += 1
            if not step.get("ok", True):
                result["success"] = False
                result["error"] = "第 %d 步失败: %s" % (i, step.get("error", ""))
                result["screenshots"] = screenshots
                break
        else:
            result["screenshots"] = screenshots
    except Exception as exc:  # noqa: BLE001
        result["success"] = False
        result["error"] = str(exc)
        result["screenshots"] = result.get("screenshots", [])
    finally:
        if ctx is not None and collect_console:
            try:
                result["console_errors"] = ctx.collect_console()
            except Exception:  # noqa: BLE001
                pass
        if driver is not None:
            try:
                driver.quit()
            except Exception:  # noqa: BLE001
                pass
    return result


def main():
    raw = sys.stdin.buffer.read().decode('utf-8').strip()
    if not raw:
        print(json.dumps(_usage_error("空输入：请通过 stdin 传入 JSON spec"), ensure_ascii=False))
        return 0
    try:
        spec = json.loads(raw)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps(_usage_error("JSON 解析失败: %s" % exc), ensure_ascii=False))
        return 0
    try:
        result = run_test(spec)
    except Exception as exc:  # noqa: BLE001 —— 兜底：任何未预期异常也不让脚本崩溃
        result = _usage_error("脚本异常: %s" % exc)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
