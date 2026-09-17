#!/usr/bin/env node
/**
 * md-print-pdf · print_pdf.js
 * 把 A4 打印版 HTML 转成 PDF（playwright-core 驱动系统 Edge，走 stdio 管道，不依赖网络）。
 *
 * 用法：
 *   NODE_PATH="<node_modules 目录>" node print_pdf.js \
 *     --html <输入 html> --pdf <输出 pdf> [--config <config.json>] [--quiet]
 */
'use strict';

const fs = require('fs');
const path = require('path');

const TAG = '[md-print-pdf]';

function die(msg, code) {
  console.error(TAG + ' 错误：' + msg);
  process.exit(code || 2);
}
function info(msg) {
  if (!QUIET) console.log(TAG + ' ' + msg);
}

/* ---------------------------------------------------------------- 参数 */
const argv = process.argv.slice(2);
let QUIET = false;
function arg(name, def) {
  const i = argv.indexOf('--' + name);
  if (i < 0) return def;
  const v = argv[i + 1];
  return (v === undefined || v.startsWith('--')) ? true : v;
}
const HTML = arg('html');
const OUT = arg('pdf');
const CFG_PATH = arg('config');
QUIET = argv.includes('--quiet');

if (!HTML || !OUT) {
  die('缺少必填参数。用法：node print_pdf.js --html <in.html> --pdf <out.pdf> [--config <cfg.json>]', 1);
}
if (!fs.existsSync(HTML)) die('输入 HTML 不存在：' + HTML, 1);

/* ------------------------------------------------------- 依赖探测 */
function loadPlaywright() {
  const attempts = [];
  attempts.push({ how: '当前目录', fn: () => require('playwright-core') });
  const np = process.env.NODE_PATH || '';
  for (const d of np.split(path.delimiter)) {
    if (!d.trim()) continue;
    attempts.push({
      how: 'NODE_PATH: ' + d,
      fn: () => require(path.join(d, 'playwright-core')),
    });
  }
  const local = path.join(__dirname, '..', 'node_modules', 'playwright-core');
  attempts.push({ how: '项目内', fn: () => require(local) });

  for (const a of attempts) {
    try { return a.fn(); } catch (e) { /* 继续尝试 */ }
  }
  die('未找到 playwright-core。\n' +
      '  解决方式（三选一）：\n' +
      '    1) 设置环境变量 NODE_PATH 指向其所在 node_modules 目录；\n' +
      '    2) 在本脚本同目录执行 npm i playwright-core；\n' +
      '    3) 在本项目根目录建立 node_modules 并安装。\n' +
      '  已尝试：' + attempts.map(a => a.how).join('、'), 3);
}

const EDGE_CANDIDATES = [
  process.env.EDGE_PATH,
  process.env.CHROME_PATH,
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
  '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/usr/bin/microsoft-edge',
  '/usr/bin/google-chrome',
  '/usr/bin/chromium',
  '/usr/bin/chromium-browser',
];

function findBrowser() {
  for (const c of EDGE_CANDIDATES) {
    if (!c) continue;
    try { if (fs.statSync(c).isFile()) return c; } catch (e) { /* 不存在 */ }
  }
  die('未找到浏览器内核（Edge / Chrome）。\n' +
      '  解决方式：设置环境变量 EDGE_PATH 指向浏览器可执行文件。\n' +
      '  Linux 示例：export EDGE_PATH=/usr/bin/chromium', 3);
}

/* ------------------------------------------------------- 配置读取 */
const DEFAULT_CFG = {
  paper: { size: 'A4', orientation: 'portrait' },
  margin: { top: '18mm', bottom: '22mm', left: '18mm', right: '18mm' },
  headerFooter: {
    preset: 'title-pagefooter',
    footerFormat: '第 {page} 页 / 共 {total} 页',
    footerLine: true,
    linePlacement: 'below',
    lineColor: '#DCDCDC',
    fontSize: '10.5px',
    color: '#6B7280',
  },
  metadata: { title: '', author: '', subject: '', keywords: '' },
  bookmarks: { enabled: true },
};

function deepMerge(base, over) {
  const out = Object.assign({}, base);
  for (const k of Object.keys(over || {})) {
    const v = over[k];
    if (v && typeof v === 'object' && !Array.isArray(v) && base[k] && typeof base[k] === 'object') {
      out[k] = deepMerge(base[k], v);
    } else {
      out[k] = v;
    }
  }
  return out;
}

let cfg = DEFAULT_CFG;
if (CFG_PATH && fs.existsSync(CFG_PATH)) {
  try {
    cfg = deepMerge(DEFAULT_CFG, JSON.parse(fs.readFileSync(CFG_PATH, 'utf8')));
  } catch (e) {
    die('配置文件解析失败：' + CFG_PATH + ' → ' + e.message, 1);
  }
}

/* ------------------------------------------------------- 页脚模板 */
const PRESETS = ['none', 'pagenum-only', 'title-pagefooter', 'chapter-pagefooter'];

function footerTemplate(hf) {
  const preset = hf.preset || 'title-pagefooter';
  if (preset === 'none') return null;
  if (!PRESETS.includes(preset)) {
    console.warn(TAG + ' 告警：未知页脚预设 "' + preset + '"，回退为 title-pagefooter');
  }
  const pn = '第 <span class="pageNumber"></span> 页 / 共 <span class="totalPages"></span> 页';
  const fmt = hf.footerFormat || '第 {page} 页 / 共 {total} 页';
  const custom = fmt.replace('{page}', '<span class="pageNumber"></span>')
                     .replace('{total}', '<span class="totalPages"></span>');
  const body = (fmt === DEFAULT_CFG.headerFooter.footerFormat) ? pn : custom;

  let inner;
  if (preset === 'pagenum-only') inner = body;
  else inner = '<span class="title"></span>　｜　' + body;   // title-pagefooter / chapter-pagefooter

  const color = hf.color || '#6B7280';
  const fs2 = hf.fontSize || '10.5px';
  const lc = hf.lineColor || '#DCDCDC';
  const font = '\'Times New Roman\', SimSun, \\5B8B\\4F53, serif';
  const wantLine = hf.footerLine !== false;
  const above = hf.linePlacement === 'above';

  const css = [
    'width:100%',
    'padding:0 18mm',
    'box-sizing:border-box',
  ].join(';');
  const cssInner = [
    'font-family:' + font,
    'font-size:' + fs2,
    'color:' + color,
    'text-align:center',
    above ? 'border-top:0.5pt solid ' + lc + ';padding-top:4px' : 'padding-bottom:4px',
    (wantLine && !above) ? 'border-bottom:0.5pt solid ' + lc : '',
  ].filter(Boolean).join(';');

  return '<div style="' + css + '"><div style="' + cssInner + '">' + inner + '</div></div>';
}

/* ------------------------------------------------------- 主流程 */
(async () => {
  const { chromium } = loadPlaywright();
  const browserPath = findBrowser();
  info('浏览器内核：' + browserPath);

  const browser = await chromium.launch({
    executablePath: browserPath,
    headless: true,
    args: ['--no-sandbox', '--disable-gpu', '--allow-file-access-from-files'],
  });

  try {
    const page = await browser.newPage({ viewport: { width: 1000, height: 1400 } });
    const fileUri = 'file:///' + path.resolve(HTML).replace(/\\/g, '/');
    await page.goto(fileUri, { waitUntil: 'load' });

    // 等 KaTeX 渲染握手完成（md2html 注入 data-math-state）
    try {
      await page.waitForFunction(
        () => document.documentElement.getAttribute('data-math-state') !== 'pending',
        { timeout: 15000 }
      );
    } catch (e) {
      console.warn(TAG + ' 告警：公式渲染状态未在 15s 内到达终态，按当前状态输出');
    }
    await page.waitForTimeout(1200);       // 等图片解码

    // PDF 元数据：Chromium 从 document.title 与 <meta> 读取
    const md = cfg.metadata || {};
    await page.evaluate((m) => {
      if (m.title) document.title = m.title;
      const setMeta = (name, content) => {
        if (!content) return;
        let el = document.querySelector('meta[name="' + name + '"]');
        if (!el) { el = document.createElement('meta'); el.setAttribute('name', name); document.head.appendChild(el); }
        el.setAttribute('content', content);
      };
      setMeta('author', m.author);
      setMeta('description', m.subject);
      setMeta('keywords', m.keywords);
    }, md);

    const hf = cfg.headerFooter || {};
    const footer = footerTemplate(hf);
    const mg = cfg.margin || {};

    const baseOpts = {
      path: path.resolve(OUT),
      format: cfg.paper && cfg.paper.size ? cfg.paper.size : 'A4',
      landscape: !!(cfg.paper && cfg.paper.orientation === 'landscape'),
      printBackground: true,
      displayHeaderFooter: !!footer,
      headerTemplate: '<div></div>',
      footerTemplate: footer || '<div></div>',
      margin: {
        top: mg.top || '18mm',
        bottom: mg.bottom || '22mm',
        left: mg.left || '18mm',
        right: mg.right || '18mm',
      },
    };

    const wantOutline = !(cfg.bookmarks && cfg.bookmarks.enabled === false);
    let warned = [];
    if (hf.preset === 'chapter-pagefooter') {
      warned.push('页脚预设 chapter-pagefooter 已按 title-pagefooter 渲染：'
                + '浏览器打印引擎无法把「当前章名」注入页脚（同类限制见 README「目录无页码」说明）。');
    }
    if (md.author || md.subject || md.keywords) {
      info('Author/Subject/Keywords 由 run.py 的 pdf_meta 后处理写入 PDF Info（引擎只写 Title）。');
    }

    // 坑位23（2026-09-17 实测）：Edge/Chromium 的书签生成必须 outline 与 tagged
    // 同时开启，只给 outline 会静默不产出 /Outlines。
    const pdfOpts = wantOutline ? Object.assign({ outline: true, tagged: true }, baseOpts)
                                : baseOpts;
    try {
      await page.pdf(pdfOpts);
    } catch (e) {
      // 老版本 playwright 不认 outline/tagged 选项 → 去掉重试
      if (/outline|tagged|unknown option|Unexpected/i.test(e.message)) {
        warned.push('当前 playwright-core 版本不支持 outline/tagged 选项，已跳过 PDF 书签生成。');
        await page.pdf(baseOpts);
      } else {
        throw e;
      }
    }

    const st = fs.statSync(path.resolve(OUT));
    info('PDF 已写出：' + OUT + '（' + (st.size / 1024).toFixed(1) + ' KB）');
    for (const w of warned) console.warn(TAG + ' 告警：' + w);

    // 供 run.py 汇总的机器可读结果
    process.stdout.write('@@RESULT@@' + JSON.stringify({
      ok: true, pdf: path.resolve(OUT), bytes: st.size,
      preset: (hf.preset || 'title-pagefooter'), warnings: warned,
    }) + '\n');
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error(TAG + ' 失败：' + (e && e.message ? e.message : e));
  process.exit(1);
});
