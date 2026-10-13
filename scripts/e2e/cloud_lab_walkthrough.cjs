/**
 * 云实验室 · 真实浏览器走查（puppeteer-core + 系统 Chrome）
 * ============================================================================
 * 与 scripts/e2e/cloud_probe.cjs 的分工：
 *   · cloud_probe.cjs 在 Node 里直连云服务，验「通道通不通」；
 *   · 本脚本在真实浏览器里跑，验「前端接得对不对」——
 *     尤其是 Node 探针**不带 Origin 头**，而服务端按 Origin 精确匹配放行，
 *     本地开发域是否被拒只有真浏览器能验出来。这是本脚本存在的核心理由。
 *
 * 前置：前端已启动（npx vite --host 127.0.0.1 --port 5300；base=/MARS-408/app/）
 *   ⚠️ Windows 保留段 5162-5261 含默认端口 5173，直接 npm run dev 会 EACCES。
 *
 * 运行：
 *   NODE_PATH=<含 puppeteer-core 的 node_modules> node scripts/e2e/cloud_lab_walkthrough.cjs
 *
 * 覆盖：
 *   1. 页面加载无 JS 崩溃、无未捕获异常
 *   2. 云账号区渲染出「未登录」状态
 *   3. AI 助教「刷新模型列表」在浏览器 Origin 下真的拉到模型（关键项）
 *   4. 全过程网络失败与 console 错误留痕
 *
 * ⚠️ 未登录态下的数据库/存储读写会被 RLS 拒绝，这是**预期结果**，不是失败。
 * ⚠️ 本脚本产出是「接入正确性」证据，禁止当成效证据引用。
 */
const puppeteer = require('puppeteer-core');
const fs = require('fs');
const path = require('path');

const BASE = process.env.E2E_BASE || 'http://127.0.0.1:5300/MARS-408/app/';
const PAGE_URL = BASE + 'cloud-lab';
const CHROME =
  process.env.E2E_CHROME ||
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const OUT = process.env.E2E_SHOTS || path.join(process.cwd(), '_e2e_tmp_mdhz', 'shots');

const checks = [];
function check(name, ok, detail) {
  checks.push({ name, ok, detail });
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}\n      ${detail}`);
}

async function clickByText(page, text, { last = false } = {}) {
  const handle = await page.evaluateHandle(
    (t, wantLast) => {
      const els = Array.from(document.querySelectorAll('button')).filter(
        (e) => (e.textContent || '').trim() === t,
      );
      if (!els.length) return null;
      return wantLast ? els[els.length - 1] : els[0];
    },
    text,
    last,
  );
  const el = handle.asElement();
  if (!el) throw new Error(`未找到按钮：${text}`);
  await el.click();
}

/**
 * 登录应用（后端账号）。
 * 云实验室页在应用路由守卫之后，未登录会被弹回 /login；
 * 这一步与「云身份登录」是两套独立体系，不要混为一谈。
 */
async function login(page, u, p) {
  await page.goto(BASE + 'login', { waitUntil: 'domcontentloaded' });
  await page.evaluate(() => {
    try {
      localStorage.clear();
    } catch {
      /* noop */
    }
  });
  await page.goto(BASE + 'login', { waitUntil: 'domcontentloaded' });
  await new Promise((r) => setTimeout(r, 1500));
  const inputs = await page.$$('input');
  if (inputs.length < 2) throw new Error('登录表单未渲染');
  await inputs[0].type(u);
  await inputs[1].type(p);
  await clickByText(page, '登录', { last: true });
  await new Promise((r) => setTimeout(r, 3000));
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1280, height: 1400 });

  const consoleErrors = [];
  const pageErrors = [];
  const failedRequests = [];
  page.on('console', (m) => {
    if (m.type() === 'error') consoleErrors.push(m.text());
  });
  page.on('pageerror', (e) => pageErrors.push(String(e && e.message ? e.message : e)));
  page.on('requestfailed', (r) =>
    failedRequests.push(`${r.method()} ${r.url()} :: ${r.failure()?.errorText || '?'}`),
  );

  console.log('=== 云实验室 · 浏览器走查 ===');
  console.log(`URL: ${PAGE_URL}\n`);

  // 应用账号登录（后端 8002 隔离库；账号由本脚本前置注册，真实库零写入）
  const APP_USER = process.env.E2E_APP_USER || 'e2e_cloud';
  const APP_PW = process.env.E2E_APP_PW || 'E2eCloud#2026x';
  await login(page, APP_USER, APP_PW);
  console.log(`已登录应用账号：${APP_USER}，落点 ${page.url()}\n`);

  await page.goto(PAGE_URL, { waitUntil: 'networkidle2', timeout: 60000 });
  await new Promise((r) => setTimeout(r, 1500));
  await page.screenshot({ path: path.join(OUT, 'cloud-lab-01-loaded.png'), fullPage: true });

  // 1) 无未捕获异常
  check(
    '页面加载无未捕获 JS 异常',
    pageErrors.length === 0,
    pageErrors.length ? pageErrors.join(' | ') : '无',
  );

  // 2) 标题渲染
  const title = await page.$eval('h1', (e) => e.textContent.trim()).catch(() => '');
  check('页面标题渲染', title.includes('云端实验存档'), `h1="${title}"`);

  // 3) 未登录态提示
  // ⚠️ 不能用整页 innerText 判断：导航里本就有「登录」二字，会假阳性。
  // 必须定位到「1 · 云账号」卡片内部，确认验证码登录表单真的在。
  const loginUi = await page.evaluate(() => {
    const secs = Array.from(document.querySelectorAll('section.card'));
    const sec = secs.find((s) => (s.querySelector('h2')?.textContent || '').includes('云账号'));
    if (!sec) return { found: false, text: '' };
    const btns = Array.from(sec.querySelectorAll('button')).map((b) => b.textContent.trim());
    return {
      found: true,
      text: (sec.innerText || '').replace(/\n+/g, ' / ').slice(0, 160),
      hasSendCode: btns.includes('获取邮箱验证码'),
      hasVerify: btns.includes('验证码登录 / 注册'),
      hasCodeInput: !!sec.querySelector('input.code'),
    };
  });
  check(
    '未登录态渲染出云账号登录表单',
    loginUi.found && loginUi.hasSendCode && loginUi.hasVerify && loginUi.hasCodeInput,
    loginUi.found
      ? `发码按钮=${loginUi.hasSendCode} 校验按钮=${loginUi.hasVerify} 验证码输入=${loginUi.hasCodeInput}｜${loginUi.text}`
      : '未找到「云账号」卡片',
  );

  // 4) 关键项：浏览器 Origin 下拉取模型列表
  // ⚠️ 同理，页面上不止一个 <select>（科目/语言等），必须定位到「AI 助教」卡片内的那个，
  // 否则会把别的下拉当成模型列表，得出假阳性。
  const tutorSelectProbe = () => {
    const secs = Array.from(document.querySelectorAll('section.card'));
    const sec = secs.find((s) => (s.querySelector('h2')?.textContent || '').includes('AI 助教'));
    const sel = sec ? sec.querySelector('select') : null;
    if (!sel) return null;
    return {
      count: sel.options.length,
      ids: Array.from(sel.options).map((o) => o.value).filter(Boolean),
    };
  };

  let modelCount = -1;
  let modelIds = [];
  try {
    await clickByText(page, '刷新模型列表');
    await page.waitForFunction(
      () => {
        const secs = Array.from(document.querySelectorAll('section.card'));
        const sec = secs.find((s) => (s.querySelector('h2')?.textContent || '').includes('AI 助教'));
        const sel = sec ? sec.querySelector('select') : null;
        return !!sel && sel.options.length > 1;
      },
      { timeout: 30000 },
    );
    await new Promise((r) => setTimeout(r, 800));
    const probe = await page.evaluate(tutorSelectProbe);
    modelCount = probe ? probe.count : -1;
    modelIds = probe ? probe.ids : [];
  } catch (e) {
    const probe = await page.evaluate(tutorSelectProbe).catch(() => null);
    if (probe) {
      modelCount = probe.count;
      modelIds = probe.ids;
    }
    console.log(`      （刷新模型列表等待失败：${e.message}）`);
  }
  await page.screenshot({ path: path.join(OUT, 'cloud-lab-02-models.png'), fullPage: true });

  const modelErr = await page
    .evaluate(() => {
      const secs = Array.from(document.querySelectorAll('section.card'));
      const sec = secs.find((s) => (s.querySelector('h2')?.textContent || '').includes('AI 助教'));
      if (!sec) return '';
      return Array.from(sec.querySelectorAll('.c-error'))
        .map((e) => e.textContent.trim())
        .join(' | ');
    })
    .catch(() => '');

  check(
    'AI 助教在浏览器 Origin 下拉取到模型列表（关键项）',
    modelCount > 1,
    `下拉选项 ${modelCount} 项：${modelIds.slice(0, 10).join(', ')}${modelErr ? `；页面错误提示：${modelErr}` : ''}`,
  );

  // 5) 网络失败汇总（仅记录，不判失败——dev 域的部分请求可能被预期拒绝）
  console.log('\n--- 过程留痕 ---');
  console.log(`console 错误：${consoleErrors.length} 条`);
  consoleErrors.slice(0, 10).forEach((e) => console.log(`   · ${e.slice(0, 200)}`));
  console.log(`请求失败：${failedRequests.length} 条`);
  failedRequests.slice(0, 10).forEach((e) => console.log(`   · ${e.slice(0, 200)}`));

  await browser.close();

  const failed = checks.filter((c) => !c.ok);
  console.log('\n=== 汇总 ===');
  console.log(`通过 ${checks.length - failed.length}/${checks.length}`);
  if (failed.length) failed.forEach((f) => console.log(`  - ${f.name}: ${f.detail}`));

  const outFile = path.join(process.cwd(), '_e2e_tmp_mdhz', 'cloud_browser_result.json');
  fs.writeFileSync(
    outFile,
    JSON.stringify(
      { at: new Date().toISOString(), url: PAGE_URL, checks, consoleErrors, failedRequests },
      null,
      2,
    ),
    'utf8',
  );
  console.log(`\n结果已写入：${path.relative(process.cwd(), outFile)}`);
  console.log(`截图目录：${path.relative(process.cwd(), OUT)}`);

  process.exit(failed.length ? 1 : 0);
})().catch((e) => {
  console.error('走查脚本异常：', e);
  process.exit(1);
});
