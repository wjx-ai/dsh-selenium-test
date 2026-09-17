/**
 * DSH Selenium 浏览器自动化测试工具插件 —— Host 端
 *
 * 注册 selenium_test 动态工具：通过真实浏览器（Chrome + Selenium）对网页执行
 * 点击 / 输入 / 截图 / 等待 / 断言 / 跳转 / 执行 JS 等操作，返回每步结果与截图路径。
 *
 * 浏览器驱动交给 lib/selenium_test.py（基于 Selenium + webdriver-manager），
 * 插件的 JS 侧只负责把操作 spec 通过 stdin 交给脚本、读取脚本输出的 JSON 结果。
 *
 * 可移植性：
 *  - Python 解释器默认取 PATH 上的 `python`（Windows）/`python3`（其它平台），
 *    可用环境变量 DSH_SELENIUM_TEST_PYTHON 覆盖（指向解释器绝对路径）。
 *  - 脚本路径由本文件目录（__dirname）相对定位，随包分发，无需机器绝对路径。
 *
 * 依赖 DSH Host 提供的 `tools`、`subprocess` 两个 Service（经 Cordis 注入）。
 */

import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));

// Python 解释器：优先环境变量，否则用平台默认
const PYTHON = process.env.DSH_SELENIUM_TEST_PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
// Selenium 脚本随包定位
const SCRIPT = join(__dirname, 'selenium_test.py');

function apply(ctx) {
  // 任何注册失败都绝不能拖垮 host 启动：整段包在 try/catch 中，异常时
  // 仅记录日志并降级为「不注册工具」，保证服务照常启动。
  try {
    const subprocess = ctx.subprocess;
    const tools = ctx.tools;
    if (!subprocess || !tools) {
      console.error('[selenium-test] required service missing at apply: subprocess=%s tools=%s', !!subprocess, !!tools);
      return;
    }

    const toolDef = {
      name: 'selenium_test',
      description: '使用 Selenium + 真实浏览器对网页执行自动化测试。输入页面 URL、操作列表和超时时间，脚本按顺序执行点击/输入/截图/等待/断言/跳转/执行JS 并把每一步结果与截图路径返回。执行依赖本机已安装 Chrome 与 Python 的 selenium、webdriver-manager。',
      parameters: {
        type: 'object',
        properties: {
          url: { type: 'string', description: '要测试的页面完整 URL，例如 https://example.com/' },
          actions: {
            type: 'array',
            description: '按顺序执行的测试操作列表。每个操作是一个对象：type 取值 navigate/click/click_js/click_by_text/wait_for_element/click_and_wait/type/screenshot/wait/wait_selector/assert/eval/execute_script/foreach，其余字段按需。',
            items: {
              type: 'object',
              properties: {
                type: { type: 'string', description: '操作类型：navigate/click/click_js/click_by_text/wait_for_element/click_and_wait/type/screenshot/wait/wait_selector/assert/eval/execute_script/execute_async_script/settle/foreach' },
                selector: { type: 'string', description: '元素选择器，默认按 CSS；供 click/type/wait_selector/wait_for_element/click_and_wait 使用' },
                by: { type: 'string', description: '选择器方式：css/xpath/id/name/tag/class/link_text/partial_link_text，默认 css' },
                value: { type: 'string', description: 'type 的输入文本 / navigate 的目标 URL / eval/execute_script 的 JS 脚本 / click_by_text 的匹配文本' },
                url: { type: 'string', description: 'navigate 的目标 URL' },
                script: { type: 'string', description: 'eval/execute_script/execute_async_script 的 JS 脚本；execute_async_script 须最后调用 callback(result) 以正确 await JS Promise' },
                path: { type: 'string', description: 'screenshot 的保存路径（缺省用临时目录）' },
                countTowardsLimit: { type: 'boolean', description: 'screenshot 是否计入动作上限，默认 true；设为 false 则截图不占用 max_actions 名额' },
                expected: { type: 'string', description: 'assert 需在渲染内容（活 DOM innerText）或页面源码中出现的子串' },
                poll: { type: 'number', description: 'assert 的轮询秒数（默认 0）：>0 时按该时长反复检查活 DOM，适配 SPA 异步渲染；0 时检查一次后回退 page_source' },
                duration: { type: 'number', description: 'wait 的等待秒数，默认 1' },
                ms: { type: 'number', description: 'settle 的 JS 睡眠毫秒数（默认 1000），用于吸收「点击后异步渲染未完成」的竞态' },
                wait: { type: 'number', description: '查找元素/等待条件的最长等待秒数，默认 10' },
                text: { type: 'string', description: 'click_by_text 要匹配的可见文本' },
                exact: { type: 'boolean', description: 'click_by_text 是否精确匹配文本，默认 true' },
                condition: { type: 'string', enum: ['presence', 'visible', 'clickable'], description: 'wait_for_element/click_and_wait 的等待条件：presence/visible/clickable' },
                wait_selector: { type: 'string', description: 'click_and_wait 点击后等待的选择器' },
                wait_by: { type: 'string', description: 'click_and_wait 等待选择器的定位方式，默认 css' },
                wait_condition: { type: 'string', enum: ['presence', 'visible', 'clickable'], description: 'click_and_wait 等待的条件，默认 presence' },
                items: { type: 'array', description: 'foreach 循环遍历的数组' },
                do: { type: 'array', description: 'foreach 每次迭代执行的动作模板数组' },
                actions: { type: 'array', description: 'foreach 的动作模板（同 do）' }
              },
              additionalProperties: true
            }
          },
          timeout: { type: 'number', description: '页面加载与整体测试超时（毫秒），默认 30000' },
          headless: { type: 'boolean', description: '是否无头运行，默认 false（默认打开可见浏览器）' },
          page_load_strategy: { type: 'string', enum: ['normal', 'eager', 'none'], description: '页面加载策略：normal=等 load 事件(默认)，eager=等 DOMContentLoaded，none=不等待，适合 SPA 资源卡住场景' },
          max_actions: { type: 'number', description: '单次测试最大动作数（含点击、输入、断言等；截图可设 countTowardsLimit=false 不计入），默认 50' },
          width: { type: 'number', description: '视口宽度，默认 1920' },
          height: { type: 'number', description: '视口高度，默认 1080' },
          implicitly_wait: { type: 'number', description: 'Selenium 隐式等待秒数（默认 0），元素查找缺失时按此时长轮询；SPA 场景建议配合显式 wait 用' },
          collect_console: { type: 'boolean', description: '是否采集 JS 异常与浏览器 console 错误并在结果回带 console_errors，默认 true' },
          script_timeout: { type: 'number', description: 'execute_script / execute_async_script 的单条脚本执行上限（秒，默认 0=用 ChromeDriver 默认 30s）；含 setTimeout 的异步脚本须设足够大，否则报 script timeout' }
        },
        required: ['url', 'actions'],
        additionalProperties: false
      },
      output: {
        schema: {
          type: 'object',
          properties: {
            success: { type: 'boolean' },
            url: { type: 'string' },
            title: { type: 'string' },
            actions: { type: 'array', items: { type: 'object' } },
            screenshots: { type: 'array', items: { type: 'string' } },
            console_errors: { type: 'array', items: { type: 'string' } },
            error: { type: 'string' }
          },
          additionalProperties: false
        },
        render: (args, value) => {
          const r = value && typeof value === 'object' ? value : {};
          if (!r.success) {
            return [{ type: 'text', text: '❌ Selenium 测试失败: ' + (r.error || '未知错误') }];
          }
          const lines = [];
          lines.push('✅ ' + (r.title || '(无标题)') + '\nURL: ' + (r.url || args && args.url || ''));
          const acts = Array.isArray(r.actions) ? r.actions : [];
          for (const a of acts) {
            const icon = a && a.ok ? '✓' : '✗';
            const detail = a && a.error ? ' ' + a.error : '';
            let line = `${icon} [${a && a.type || 'step'}]${detail}`;
            // 新 action 类型的额外信息
            if (a && a.type === 'click_by_text' && a.matched_text) {
              line += ' → 文本: "' + a.matched_text + '"';
            }
            if (a && a.type === 'wait_for_element' && a.condition) {
              line += ' → 条件: ' + a.condition;
            }
            if (a && a.type === 'click_and_wait' && a.wait_selector) {
              line += ' → 等待: ' + a.wait_selector;
            }
            if (a && a.type === 'foreach' && a._foreach_index !== undefined) {
              line += ' → 迭代 #' + a._foreach_index;
            }
            if (a && a.type === 'assert' && a.asserted !== undefined) {
              line += ' → 断言: "' + a.expected + '" ' + (a.asserted ? '通过' : '失败');
            }
            if (a && a.result !== undefined && a.result !== null && a.result !== true && a.result !== false) {
              const resStr = typeof a.result === 'string' ? a.result : JSON.stringify(a.result, null, 2);
              line += '\n    → 返回: ' + (resStr.length > 500 ? resStr.slice(0, 500) + '…' : resStr);
            }
            lines.push(line);
          }
          const ce = Array.isArray(r.console_errors) ? r.console_errors : [];
          lines.push('\nJS/Console 错误: ' + (ce.length > 0 ? ce.length + ' 条' : '无'));
          if (ce.length > 0) {
            for (const c of ce.slice(0, 20)) lines.push('  - ' + String(c).slice(0, 200));
            if (ce.length > 20) lines.push('  …(另有 ' + (ce.length - 20) + ' 条未列)');
          }
          const shots = Array.isArray(r.screenshots) ? r.screenshots : [];
          if (shots.length > 0) lines.push('\n截图:\n' + shots.join('\n'));
          return [{ type: 'text', text: lines.join('\n') }];
        },
        presentationMeta: (args, value) => ({})
      },
      async execute(args) {
        const trace = [];
        try {
          const url = args && typeof args.url === 'string' ? args.url : '';
          const actions = Array.isArray(args && args.actions) ? args.actions : [];
          if (!url) {
            return { success: false, url: '', title: '', actions: [], screenshots: [], console_errors: [], error: '缺少 url 参数' };
          }

          const spec = {
            url: url,
            actions: actions,
            timeout: typeof args.timeout === 'number' ? args.timeout : 30000,
            options: {
              headless: args.headless === true ? true : false,
              page_load_strategy: typeof args.page_load_strategy === 'string' ? args.page_load_strategy : 'normal',
              max_actions: typeof args.max_actions === 'number' ? args.max_actions : 50,
              width: typeof args.width === 'number' ? args.width : 1920,
              height: typeof args.height === 'number' ? args.height : 1080,
              implicitly_wait: typeof args.implicitly_wait === 'number' ? args.implicitly_wait : 0,
              collect_console: args.collect_console !== false,
              script_timeout: typeof args.script_timeout === 'number' ? args.script_timeout : 0
            }
          };

          const handle = subprocess.spawn({
            // -X utf8：强制 Python UTF-8 模式。Windows 上 Python 默认用 GBK(cp936) 写
            // stdout，会让结果里的中文变成非 UTF-8 字节（乱码 / 甚至 UnicodeEncodeError 崩掉）。
            argv: [PYTHON, '-X', 'utf8', SCRIPT],
            cwd: __dirname,
            stdio: {
              stdin: { data: JSON.stringify(spec) },
              stdout: { maxBytes: 10485760, spill: { maxBytes: 16777216 } },
              stderr: { maxBytes: 1048576, spill: { maxBytes: 16777216 } }
            },
            graceMs: 3000
          });
          trace.push('spawned');

          const outcome = await handle.done;
          const so = handle.collected && handle.collected.stdout ? handle.collected.stdout.readFrom(0) : null;
          const se = handle.collected && handle.collected.stderr ? handle.collected.stderr.readFrom(0) : null;
          const stdout = so ? so.text : '';
          const stderr = se ? se.text : '';
          const exitCode = outcome && outcome.exitCode !== undefined ? outcome.exitCode : 'unknown';
          trace.push('exit=' + exitCode, 'out=' + stdout.length + 'B');

          const trimmed = stdout.trim();
          if (!trimmed) {
            return { success: false, url: url, title: '', actions: [], screenshots: [], console_errors: [], error: '脚本无输出 exit=' + exitCode + ' stderr=' + (stderr.slice(0, 300) || '空') };
          }

          try {
            const parsed = JSON.parse(trimmed);
            return {
              success: parsed.success === true,
              url: typeof parsed.url === 'string' ? parsed.url : url,
              title: typeof parsed.title === 'string' ? parsed.title : '',
              actions: Array.isArray(parsed.actions) ? parsed.actions : [],
              screenshots: Array.isArray(parsed.screenshots) ? parsed.screenshots : [],
              console_errors: Array.isArray(parsed.console_errors) ? parsed.console_errors : [],
              error: typeof parsed.error === 'string' ? parsed.error : ''
            };
          } catch (pe) {
            return { success: false, url: url, title: '', actions: [], screenshots: [], console_errors: [], error: '输出非 JSON: ' + trimmed.slice(0, 200) + ' [trace: ' + trace.join('; ') + ']' };
          }
        } catch (e) {
          const msg = e && e.message ? e.message : String(e);
          return { success: false, url: '', title: '', actions: [], screenshots: [], console_errors: [], error: '执行异常: ' + msg.slice(0, 300) + ' [trace: ' + trace.join('; ') + ']' };
        }
      }
    };

    const dispose = tools.register(toolDef);
    console.log('[selenium-test] registered selenium_test tool');
    return dispose;
  } catch (error) {
    const msg = error && error.message ? error.message : String(error);
    console.error('[selenium-test] plugin activation failed; continuing without it: ' + msg.slice(0, 400));
    return;
  }
}

export default { inject: ['tools', 'subprocess'], apply };
