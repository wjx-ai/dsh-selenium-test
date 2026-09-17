/**
 * 编码回归测试：确保插件脚本的 stdout 永远是 UTF-8，中文不会乱码 / 崩溃。
 *
 * 背景（这个测试锁住的真实缺陷）：
 *   Windows 上 Python 的 stdout 默认编码是 cp936(GBK)。插件用
 *   `print(json.dumps(result, ensure_ascii=False))` 输出含中文的结果时，写出的就是
 *   GBK 字节，而父进程(JS)按 UTF-8 读取 → 中文全乱码，且输出不是合法 UTF-8；
 *   遇到 GBK 编不了的字（emoji、生僻字）更会 UnicodeEncodeError 直接崩掉、无输出。
 *
 * 覆盖：
 *   Tier 1（默认，无需 Chrome / 不触网）：中文错误信息的 stdout 必须是合法 UTF-8 且中文完好。
 *   Tier 2（设置 DSH_SELENIUM_TEST_E2E=1 启用，需要 Chrome + selenium）：
 *     真实浏览器里跑「中文 eval 脚本 + 中文断言」，验证返回的中文文本与断言结果。
 *
 * 用法:
 *   node test/encoding.mjs
 *   DSH_SELENIUM_TEST_E2E=1 node test/encoding.mjs   （PowerShell: $env:DSH_SELENIUM_TEST_E2E=1; node test/encoding.mjs）
 */

import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { writeFileSync, mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const script = join(root, 'lib', 'selenium_test.py');
const python = process.env.DSH_SELENIUM_TEST_PYTHON || (process.platform === 'win32' ? 'python' : 'python3');

// 与 lib/index.js 保持一致：强制 Python UTF-8 模式
const PY_ARGS = ['-X', 'utf8'];

let failures = 0;
function fail(msg) {
  console.error('  ✗ ' + msg);
  failures += 1;
}
function pass(msg) {
  console.log('  ✓ ' + msg);
}

/** 跑一次插件脚本，返回 { raw: Buffer, text: string|null, json: any|null } */
function runPlugin(spec, extraArgs = []) {
  const proc = spawnSync(python, [...PY_ARGS, ...extraArgs, script], {
    input: JSON.stringify(spec),
    timeout: 120000,
    maxBuffer: 32 * 1024 * 1024,
  });
  const raw = proc.stdout || Buffer.alloc(0);
  let text = null;
  try {
    text = raw.toString('utf8');
  } catch {
    /* ignore */
  }
  let json = null;
  if (text) {
    try {
      json = JSON.parse(text);
    } catch {
      /* ignore */
    }
  }
  return { raw, text, json, stderr: (proc.stderr || Buffer.alloc(0)).toString('utf8') };
}

// ---------------------------------------------------------------- Tier 1
console.log('[encoding] Tier 1: stdout 必须是合法 UTF-8（无需 Chrome）');
{
  // 该 spec 在导入 selenium / 启动 Chrome 之前就返回中文错误，因此无需浏览器。
  const spec = { url: 'http://example.invalid/', actions: 'not-an-array' };
  const r = runPlugin(spec);

  // 1) 原始字节必须能被严格 UTF-8 解码
  let strict = null;
  try {
    strict = new TextDecoder('utf-8', { fatal: true }).decode(r.raw);
  } catch (e) {
    fail('stdout 不是合法 UTF-8（父进程按 UTF-8 读取会得到乱码）: ' + e.message);
  }
  if (strict !== null) pass('stdout 是合法 UTF-8');

  // 2) 必须是 GBK 解不开（证明没有回退到 cp936 输出）
  if (strict !== null) {
    try {
      Buffer.from(strict, 'utf8').toString('latin1');
      pass('输出路径为 UTF-8（GBK 默认编码已被覆盖）');
    } catch {
      /* ignore */
    }
  }

  // 3) JSON 可解析，且中文完好
  if (!r.json) {
    fail('stdout 不是可解析的 JSON: ' + String(r.text).slice(0, 200));
  } else {
    pass('stdout 是可解析的 JSON');
    const err = r.json.error || '';
    if (err.includes('actions') && err.includes('必须是数组')) {
      pass('中文错误信息完好: ' + JSON.stringify(err));
    } else {
      fail('中文错误信息损坏或缺失，实际为: ' + JSON.stringify(err));
    }
    if (/\uFFFD/.test(err)) fail('错误信息含替换字符 U+FFFD，说明发生过解码失败');
  }
}

// ---------------------------------------------------------------- Tier 2
if (process.env.DSH_SELENIUM_TEST_E2E === '1') {
  console.log('[encoding] Tier 2: 真实浏览器中文 eval / 中文断言');
  const dir = mkdtempSync(join(tmpdir(), 'dsh-enc-'));
  const page = join(dir, 'cn_page.html');
  writeFileSync(
    page,
    '<!doctype html><html><head><meta charset="utf-8"><title>天医门 · 万象</title></head>' +
      '<body><h1 id="h">天医门 · 万象</h1><button id="b">起心动卦</button>' +
      '<div id="out">未点击</div><script>' +
      "document.getElementById('b').addEventListener('click',function(){" +
      "document.getElementById('out').textContent='已点击：起心动卦';});" +
      '</script></body></html>',
    'utf8',
  );

  const spec = {
    url: 'file:///' + page.replace(/\\/g, '/'),
    options: { headless: true, page_load_strategy: 'none' },
    actions: [
      { type: 'eval', script: 'return document.title;' },
      // 中文直接写在脚本源里（不再需要手写 \u 转义）
      { type: 'eval', script: "return document.getElementById('h').textContent.indexOf('万象') >= 0;" },
      { type: 'assert', expected: '天医门' },
      { type: 'click', selector: '#b' },
      { type: 'settle', ms: 300 },
      // 点击后断言「真实渲染出来的内容」
      { type: 'assert', expected: '已点击：起心动卦' },
      { type: 'eval', script: 'return document.getElementById("out").textContent;' },
    ],
  };

  const r = runPlugin(spec);
  if (!r.json) {
    fail('Tier 2 输出不是 JSON（Chrome/selenium 是否可用？）: ' + String(r.text).slice(0, 300) + ' | stderr: ' + r.stderr.slice(0, 300));
  } else if (!r.json.success) {
    fail('Tier 2 测试失败: ' + r.json.error);
    for (const a of r.json.actions || []) {
      if (!a.ok) console.error('      step ' + a.index + ' [' + a.type + '] ' + a.error);
    }
  } else {
    const acts = r.json.actions || [];
    if (r.json.title === '天医门 · 万象') pass('title 中文完好: ' + r.json.title);
    else fail('title 中文损坏: ' + JSON.stringify(r.json.title));

    const s1 = acts.find((a) => a.index === 1);
    if (s1 && s1.result === true) pass('脚本源内直接写中文做 indexOf 判定 -> true');
    else fail('中文 indexOf 判定异常: ' + JSON.stringify(s1 && s1.result));

    const a1 = acts.find((a) => a.index === 2);
    if (a1 && a1.asserted === true) pass('中文断言（点击前）通过');
    else fail('中文断言（点击前）失败');

    const a2 = acts.find((a) => a.index === 5);
    if (a2 && a2.asserted === true) pass('中文断言（点击后，验证真实渲染内容）通过');
    else fail('中文断言（点击后）失败');

    const s6 = acts.find((a) => a.index === 6);
    if (s6 && s6.result === '已点击：起心动卦') pass('中文返回值完好: ' + JSON.stringify(s6.result));
    else fail('中文返回值损坏: ' + JSON.stringify(s6 && s6.result));
  }
} else {
  console.log('[encoding] Tier 2 已跳过（设置 DSH_SELENIUM_TEST_E2E=1 启用真实浏览器验证）');
}

if (failures > 0) {
  console.error('[encoding] FAILED: ' + failures + ' 项未通过');
  process.exit(1);
}
console.log('[encoding] ENCODING OK');
process.exit(0);
