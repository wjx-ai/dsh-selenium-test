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
- **可移植依赖**:Python 解释器默认取 `python`(Windows)/`python3`(其它平台),可用环境变量
  `DSH_SELENIUM_TEST_PYTHON` 覆盖指向任意解释器路径。
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

> 无需配置 API Key,不需要 Selenium / 浏览器的时候也能安全降级(工具未被调用即不触发)。

## 安装

`dsh plugin add` 把包装进 profile 后,dsh 会把它当做一个 **profile 层自动激活**(本包在 `package.json`
声明了 `"dsh": { "bundle": { "patch": "./cordis.patch.yml" } }`,会自动应用自带的
`cordis.patch.yml` 插入 `selenium-test` 条目),通常无需手动挂载。

### 方式一:从 npm 安装(推荐,带 @)

```powershell
dsh plugin --profile web add @wjx-ai/dsh-selenium-test
```

### 方式二:从 GitHub 直接安装

```powershell
# pnpm 会从 GitHub 拉取并 link;安装后的包名为 @wjx-ai/dsh-selenium-test
dsh plugin --profile web add github:wjx-ai/dsh-selenium-test
```

### 挂载校验(通常无需手动,提供兜底)

如果装好后 dsh 没有自动激活该插件(例如旧版 dsh、或插件是在声明 `dsh.bundle` 之前安装的),二选一:

**A. 加入 `dsh.profile.bundles`(推荐)**:在 `$env:USERPROFILE\.dsh\profiles\web\package.json` 的
`dsh.profile.bundles` 数组里加上 `"@wjx-ai/dsh-selenium-test"`(与 `@deepseek-ai/dsh-base`、`@deepseek-ai/dsh-web-app` 并列)。

**B. 在 `cordis.patch.yml` 追加 insert**:

```yaml
- insert:
    - id: selenium-test
      name: '@wjx-ai/dsh-selenium-test'
```

### 重启生效

```powershell
dsh web
```

启动日志出现 `[selenium-test] registered selenium_test tool` 即成功。

### 升级到最新版

无需指定版本号。在 DSH profile 目录下(把 `web` 换成你的 profile 名)执行:

```powershell
cd $env:USERPROFILE\.dsh\profiles\web
pnpm update @wjx-ai/dsh-selenium-test
```

之后重启生效:

```powershell
dsh web
```

> **注意(pnpm 供应链策略)**:如果刚发布了新版本但 `pnpm update` 提示 `Already up to date`,
> 那是 pnpm 的 `minimumReleaseAge` 安全策略在限制“太年轻”的包。要么等它满足最低年龄,
> 要么在 profile 的 `pnpm-workspace.yaml` 里设 `minimumReleaseAge: 0` 后再更新。

## 使用

装好并重启后,直接让 Agent 调用工具即可。例如测试本机一个页面的开屏广告:

```
请用 selenium_test 测试 http://localhost:8081/ 的开屏广告:检查广告是否显示、滚动是否锁定,并截图保存。
```

### 工具 Schema

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `url`(入参,必填) | string | 要测试的页面完整 URL |
| `actions`(入参,必填) | array | 按顺序执行的操作列表,每项为对象 |
| `timeout`(入参,可选) | number | 页面加载与整体测试超时(毫秒),默认 `30000` |
| `headless`(入参,可选) | boolean | 是否无头运行,默认 `true` |
| `width` / `height`(入参,可选) | number | 视口尺寸,默认 `1920` / `1080` |
| `success`(出参) | boolean | 整体是否成功 |
| `url`(出参) | string | 测试结束时的实际 URL |
| `title`(出参) | string | 页面标题 |
| `actions`(出参) | array | 每步 `{ index, type, ok, error?, ... }` |
| `screenshots`(出参) | array | 截图保存路径列表 |
| `error`(出参) | string | 失败原因 |

#### 每项 action 的字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `type`(必填) | string | `navigate` / `click` / `type` / `screenshot` / `wait` / `wait_selector` / `assert` / `eval` / `execute_script` |
| `selector` | string | 元素选择器,默认按 CSS;供 `click` / `type` / `wait_selector` 使用 |
| `by` | string | 选择器方式:`css` / `xpath` / `id` / `name` / `tag` / `class` / `link_text` / `partial_link_text`,默认 `css` |
| `value` | string | `type` 的输入文本 / `navigate` 的目标 URL / `eval` 的 JS 脚本 |
| `url` | string | `navigate` 的目标 URL |
| `script` | string | `eval` / `execute_script` 的 JS 脚本 |
| `path` | string | `screenshot` 的保存路径(缺省用临时目录) |
| `expected` | string | `assert` 需在页面源码中出现的子串 |
| `duration` | number | `wait` 的等待秒数,默认 `1` |
| `wait` | number | 查找元素的最长等待秒数,默认 `10` |

### 返回示例

```json
{
  "success": true,
  "url": "https://example.com/",
  "title": "Example Domain",
  "actions": [
    { "index": 0, "type": "click", "ok": true },
    { "index": 1, "type": "screenshot", "ok": true, "path": "C:/Users/.../dsh-selenium-xxxx.png" }
  ],
  "screenshots": ["C:/Users/.../dsh-selenium-xxxx.png"]
}
```

### 常用 action 写法

```js
selenium_test({
  url: "https://example.com/login",
  actions: [
    { type: "type", selector: "#username", value: "user" },
    { type: "type", selector: "#password", value: "pass" },
    { type: "click", selector: "button[type='submit']" },
    { type: "wait", duration: 2 },
    { type: "assert", expected: "Welcome" },
    { type: "screenshot", path: "D:\\dsh\\login.png" }
  ],
  timeout: 30000
})
```

## 配置

### `DSH_SELENIUM_TEST_PYTHON`(可选)

如果 `python` / `python3` 不在 `PATH` 上,或想明确指定解释器,设置环境变量(在启动 DSH 的终端里):

```powershell
$env:DSH_SELENIUM_TEST_PYTHON = "C:\path\to\python.exe"
dsh web
```

优先级:环境变量 > 平台默认(`python` on Windows,`python3` 其它)。

## 开发

```
dsh-selenium-test/
├── .github/
│   └── workflows/
│       └── publish.yml     # 发布:推 v* 标签 → CI 用 OIDC 发到 npm
├── lib/
│   ├── index.js            # Cordis 插件入口(ESM,注册 selenium_test 工具)
│   └── selenium_test.py    # Python Selenium 驱动脚本(惰性导入依赖)
├── test/
│   └── smoke.mjs           # 冒烟测试:验证插件形状 + 脚本可运行
├── cordis.patch.yml        # 推荐的 profile 挂载片段
├── README.md
├── LICENSE
└── package.json
```

### 冒烟测试

```powershell
node test/smoke.mjs
```

覆盖:插件模块能作为 ESM 导出 `{ inject, apply }`;Python 脚本可通过解释器运行并返回合法 JSON。(不访问网络、不需要 Selenium。)

### 本地调试加载

改动 `lib/index.js` 后,重启 `dsh web` 即可;插件注册失败会打印
`[selenium-test] plugin activation failed; continuing without it`。

## 故障排除

| 现象 | 原因 / 处理 |
| --- | --- |
| 启动日志出现 `required service missing at apply` | `tools` / `subprocess` Service 未挂载,需在包含 `dsh-base` 的 profile 里使用 |
| 工具返回 `执行异常: spawn python ENOENT` | 找不到 Python,确保 `python` 在 `PATH`,或设置 `DSH_SELENIUM_TEST_PYTHON` |
| 工具返回 `缺少 Selenium 依赖` | 需 `pip install selenium webdriver-manager` |
| 工具返回 `脚本无输出` | 解释器或脚本路径有误;可自测:`python lib/selenium_test.py` |
| 浏览器启动失败 / chromedriver 下载失败 | 需本机安装 Google Chrome;`webdriver-manager` 自动拉取匹配版本,网络受限时手动安装 chromedriver 并置于 PATH |
| 某步失败并终止 | 见 `actions` 中对应 `error`;常见为选择器未命中(检查 `selector`/`by`) |

## 免责声明

本插件仅用于技术学习与合法内容整理。自动化测试请遵守目标站点条款与相关法律法规,勿用于侵权、绕过风控或商业滥用;
因使用本插件产生的一切后果由使用者自行承担。

## License

[MIT](LICENSE) © [wjx-ai](https://github.com/wjx-ai)
