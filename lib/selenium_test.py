#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DSH Selenium 浏览器自动化测试工具脚本。

从 stdin 读取一个 JSON spec：
{
  "url": "...",
  "actions": [ {"type": "...", ...}, ... ],
  "timeout": 30000,
  "options": {"headless": true, "width": 1920, "height": 1080}
}

按顺序执行每一项操作，输出一个 JSON 结果到 stdout：
{
  "success": true,
  "url": "...",
  "title": "...",
  "actions": [ {"index": 0, "type": "click", "ok": true}, ... ],
  "screenshots": ["C:/..."],
  "error": "..."            # 仅在失败时
}

依赖（第三方，需安装）：pip install selenium webdriver-manager
运行环境：本机需安装 Google Chrome（webdriver-manager 会自动下载匹配的 chromedriver）。

设计：Selenium 的 import 是惰性的（在 run_test 内部发生），因此没有安装
selenium 时脚本仍可运行并返回 JSON 错误，便于冒烟测试与快速定位环境问题。
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


def _usage_error(message):
    return {"success": False, "url": "", "title": "", "actions": [], "screenshots": [], "error": message}


def _resolve_by(action):
    by = (action.get("by") or action.get("selectorType") or "css").lower()
    return _BY_MAP.get(by, "CSS_SELECTOR")


def _find(driver, By, WebDriverWait, EC, action):
    """按 selector/by 解析并等待元素出现。selector 缺省用 action.value。"""
    selector = action.get("selector") or action.get("value")
    if not selector:
        raise ValueError("缺少 selector/value（元素定位）")
    by_name = _resolve_by(action)
    by = getattr(By, by_name)
    wait_seconds = float(action.get("wait", 10))
    return WebDriverWait(driver, wait_seconds).until(
        EC.presence_of_element_located((by, selector))
    )


def _run_one(driver, By, WebDriverWait, EC, action, index, screenshots):
    step = {"index": index, "type": action.get("type"), "ok": True}
    t = action.get("type")
    try:
        if t == "navigate":
            target = action.get("url") or action.get("value")
            if not target:
                raise ValueError("navigate 缺少 url/value")
            driver.get(target)
            step["url"] = driver.current_url
        elif t in ({"click", "click_js"}):
            _find(driver, By, WebDriverWait, EC, action).click()
        elif t == "type":
            el = _find(driver, By, WebDriverWait, EC, action)
            val = action.get("value") or ""
            el.clear()
            el.send_keys(val)
        elif t == "screenshot":
            path = action.get("path")
            if not path:
                path = os.path.join(tempfile.gettempdir(), "dsh-selenium-%d.png" % int(time.time() * 1000))
            driver.save_screenshot(path)
            screenshots.append(path)
            step["path"] = path
        elif t == "wait":
            duration = float(action.get("duration", action.get("value", 1)))
            time.sleep(duration)
        elif t == "wait_selector":
            _find(driver, By, WebDriverWait, EC, action)
        elif t == "assert":
            expected = action.get("expected") or ""
            if not expected:
                raise ValueError("assert 缺少 expected")
            step["asserted"] = expected in driver.page_source
            if not step["asserted"]:
                raise AssertionError("断言失败：未在页面源码中找到子串 %r" % expected)
        elif t == "eval":
            js = action.get("script") or action.get("value")
            if not js:
                raise ValueError("eval 缺少 script/value")
            step["result"] = driver.execute_script(js)
        elif t == "execute_script":
            js = action.get("script") or action.get("value")
            if not js:
                raise ValueError("execute_script 缺少 script/value")
            driver.execute_script(js)
        else:
            raise ValueError("未知操作类型: %r" % t)
    except Exception as exc:  # noqa: BLE001 —— 把每步失败记入结果，不让整个测试崩掉
        step["ok"] = False
        step["error"] = str(exc)
    return step


def run_test(spec):
    url = spec.get("url") or ""
    if not url:
        return _usage_error("缺少 url")
    actions = spec.get("actions") or []
    if not isinstance(actions, list):
        return _usage_error("actions 必须是数组")
    timeout = int(spec.get("timeout", 30000)) or 30000
    options = spec.get("options") or {}
    headless = options.get("headless", True)
    if headless is None:
        headless = True
    width = int(options.get("width", 1920))
    height = int(options.get("height", 1080))

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
    if headless:
        chrome_options.add_argument("--headless=new")

    result = {"success": True, "url": url, "title": "", "actions": [], "screenshots": []}
    driver = None
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.set_page_load_timeout(timeout / 1000.0)
        driver.get(url)
        result["url"] = driver.current_url
        result["title"] = driver.title

        screenshots = []
        for i, action in enumerate(actions):
            if not isinstance(action, dict):
                result["success"] = False
                result["error"] = "第 %d 个 action 不是对象" % i
                break
            step = _run_one(driver, By, WebDriverWait, EC, action, i, screenshots)
            result["actions"].append(step)
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
        if driver is not None:
            try:
                driver.quit()
            except Exception:  # noqa: BLE001
                pass
    return result


def main():
    raw = sys.stdin.read().strip()
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
