# @wjx-ai/dsh-selenium-test

> DeepSeek Harness(DSH)Selenium 浏览器自动化测试工具插件 —— 为 DSH 提供一个可直接调用的
> **`selenium_test`** 工具,输入页面 URL 与操作列表,通过真实浏览器按顺序执行测试并返回每步结果与截图路径。

[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Node](https://img.shields.io/badge/node-%3E%3D18-339933.svg)](package.json)

---

## 简介

`@wjx-ai/dsh-selenium-test` 是 DSH 的一个 **Host 侧工具插件**。它以 Cordis 插件的形式注册一个动态工具
`selenium_test`,用真实 Chrome 浏览器对目标网页执行自动化测试。

- 输入页面 URL 和操作列表(点击 / 输入 / 截图 / 等待 / 断言 / 跳转 / 执行 JS)。
- 逐条记录并返回每一步是否成功,失败即终止并给出原因。
- 截图保存到本地(默认临时目录,可指定路径),并在结果中返回截图路径。
- 适用场景:让 Agent 打开某个页面,检查元素/文案、填写表单、验证行为、截图取证等。

## 特性

- **零配置上手**:装好后即可用,Python 脚本随包分发、由 `__dirname` 定位,无机器绝对路径。
- **真实浏览器**:基于 Selenium `webdriver` + `webdriver-manager`,自动拉取匹配的 chromedriver。
- **失败降级保护**:插件注册全程 `try/catch`,即使脚本或服务异常也不会拖垮 DSH 启动。
- **清晰结果**:每步独立记录 `ok`/`error`,整体 `success`;缺依赖/缺参数都会返回可读错误。

## 环境要求

| 依赖 | 说明 |
| --- | --- |
| DSH(DeepSeek Harness) | 提供 `tools` / `subprocess` Service,并负责按 `cordis:include` 加载插件 |
| Node.js | 运行本插件 **>= 18**([ESM](https://nodejs.org/api/esm.html)) |
| Python 3 | 用于驱动脚本;脚本惰性导入 Selenium,缺依赖会返回可读错误 |
| Google Chrome | 本机安装的 Chrome,供 `webdriver-manager` 驱动 |
| Python 三方包 | `pip install selenium webdriver-manager` |

## 安装

```powershell
dsh plugin --profile web add @wjx-ai/dsh-selenium-test
```

或从 GitHub 直接安装:

```powershell
dsh plugin --profile web add github:wjx-ai/dsh-selenium-test
```

`dsh plugin add` 会把包装进 profile 并自动激活(包内 `cordis.patch.yml` 会插入 `selenium-test` 条目),然后 `dsh web` 重启生效,启动日志出现 `[selenium-test] registered selenium_test tool` 即成功。

## 使用

装好并重启后,直接让 Agent 调用 `selenium_test` 工具对指定页面执行浏览器自动化测试即可。

## 变更记录

### v0.1.8（2026-09-16）—— 中文编码修复（需重启 DSH 生效）

**修复的真实缺陷**：Windows 上 Python 的 `stdout` 默认编码是 `cp936(GBK)`。插件用
`print(json.dumps(result, ensure_ascii=False))` 输出含中文的结果时，写出的是 **GBK 字节**，
而 JS 侧按 **UTF-8** 读取 → 结果里所有中文（标题、步骤返回值、断言文本、console_errors）
全部乱码，且输出本身不是合法 UTF-8；若文本含 GBK 编不了的字（emoji、生僻字），更会直接
`UnicodeEncodeError` 让脚本崩掉、返回“脚本无输出”。

**修复**：

- **JS 侧**：以 `python -X utf8` 启动脚本，强制 Python 进入 UTF-8 模式。
- **脚本侧**：`_force_utf8_stdio()` 对 stdin/stdout/stderr 执行 `reconfigure(encoding="utf-8")` 兜底。
- **`assert` 改为浏览器端 ASCII 安全判定**：期望值先经 `json.dumps(..., ensure_ascii=True)`
  转义为纯 ASCII（中文 → `\uXXXX`）再拼进下发的脚本，因此**发给 ChromeDriver 的请求体永远是纯 ASCII**，
  从根本上规避多字节字符导致的 `missing command parameters`；判断在浏览器里用 `indexOf` 完成，
  回程只传 `true/false`，断言的是 `document.body.innerText`（活 DOM，即**真实渲染内容**，非状态码）。
  新增可选 `selector`：把断言范围限定到某个元素。

**结论：脚本源与断言期望值里可以直接写中文，无需再手工 `\u` 转义。**

**回归测试**：新增 `test/encoding.mjs` —— Tier 1（默认，无需 Chrome）验证 stdout 为合法 UTF-8 且中文完好；
Tier 2（`DSH_SELENIUM_TEST_E2E=1`）在真实 Chrome 里跑「中文 eval + 中文断言」。`npm test` 已接入 Tier 1。

### v0.1.7（2026-07-08）—— SPA 健壮性升级（需重启 DSH 生效）

`lib/selenium_test.py` 新增/增强（向后兼容,旧调用不受影响）：

- **`execute_async_script` 动作**：正确 await JS Promise（`cb` 约定绑定末位 callback；同步 `execute_script` 不会等 Promise）。
- **`settle` 动作**：JS 睡眠 + DOM-ready 探测,吸收「点击后异步渲染未完成」竞态（`ms` 参数,默认 1000）。
- **`_send` 就绪探测 + 重试**：`page_load_strategy=none` 时导航未落定的瞬态 `invalid argument` 自动小步重试,不再整轮崩。
- **`assert` 活 DOM + `poll`**：默认查 `document.body.innerText`（覆盖 JS 渲染）并按 `poll` 秒轮询,SPA 异步渲染可断言；仍保留 `page_source` 兜底。
- **`console_errors` 采集**：注入 `window.__dshErrs` + `driver.get_log('browser')`,结果回带（`collect_console` 开关,默认 true）。
- **避免重复 `driver.get`**：首动作是 `navigate` 时不再预导航。
- **`script_timeout` 选项**：含 `setTimeout` 的异步脚本须设足够大,否则报 `script timeout`（默认 0=用 ChromeDriver 30s）。

**配套 `lib/index.js`**：schema 暴露 `execute_async_script / settle / poll / ms / implicitly_wait / collect_console / script_timeout`,输出与渲染回带 `console_errors`。

**验证**：`py_compile` ✓、`node --check` ✓、`test/smoke.mjs` ✓；静态 SPA 页 e2e（异步等待/活 DOM 断言/中文/控制台错误）全绿；万象 `/wanxiang` 全量点击（登录→8 选项卡→辨证→五运四块断言）`console_errors=[]` 跑通。

> **正在运行的 DSH 实例要用本升级,须重启一次**（插件在启动时注册；工具描述与 schema 亦随之更新）。

## 免责声明

本插件仅用于技术学习与合法内容整理。自动化测试请遵守目标站点条款与相关法律法规,勿用于侵权、绕过风控或商业滥用;
因使用本插件产生的一切后果由使用者自行承担。

## License

[MIT](LICENSE) © [wjx-ai](https://github.com/wjx-ai)
