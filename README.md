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

## 免责声明

本插件仅用于技术学习与合法内容整理。自动化测试请遵守目标站点条款与相关法律法规,勿用于侵权、绕过风控或商业滥用;
因使用本插件产生的一切后果由使用者自行承担。

## License

[MIT](LICENSE) © [wjx-ai](https://github.com/wjx-ai)
