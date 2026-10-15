/**
 * 教师侧教学闭环 · 真实浏览器走查（Playwright）
 * ============================================================================
 * 覆盖路线图 B5「登录→建班→发任务→学生凭码加入→对抗→六维报告→教师看板」，
 * 及拼图②产品向收尾「看板 CSV 导出（纯前端生成→浏览器下载→落盘校验）」（D 步）。
 *
 * 前置（脚本不负责起服务）：
 *   1) 后端：cd py-server && python main.py            # :8002
 *      建议加 LLM_PROVIDER=deepseek，否则 auto 会先试讯飞（本环境 11200 无权限）
 *      再回退 → 每次调用白等数秒。
 *   2) 前端：npx vite --host 127.0.0.1 --port 5300     # base=/MARS-408/app/
 *      ⚠️ Windows 保留段 5162-5261 含默认端口 5173，直接 npm run dev 会 EACCES。
 *   3) 账号：教师与学生各一（教师需 role=teacher，注册端点只建 student，
 *      需管理员经 POST /api/admin/users 创建）。
 *   4) 学生需已过入学测评，否则登录后落 /diagnostic/start
 *      （POST /api/diagnostic/submit 可清）。
 *
 * 运行：
 *   NODE_PATH=<playwright 所在 node_modules> node scripts/e2e/teacher_loop_walkthrough.cjs
 *   可选环境变量：E2E_BASE / E2E_SHOTS / E2E_TEACHER / E2E_TEACHER_PW /
 *                 E2E_STUDENT / E2E_STUDENT_PW（均有默认值）
 *
 * 说明：本机 playwright 未列为项目依赖，故用 NODE_PATH 指向已有安装；
 *       亦可用 `channel: 'chrome'` 走系统 Chrome，避免下载浏览器。
 *       本脚本**不在 CI 运行**（需人工起服务 + 真实 LLM），属人工走查工具。
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const BASE = process.env.E2E_BASE || 'http://127.0.0.1:5300/MARS-408/app/';
const OUT = process.env.E2E_SHOTS || path.join(process.cwd(), 'e2e-shots');
const T = { u: process.env.E2E_TEACHER || 'e2e_teacher', p: process.env.E2E_TEACHER_PW || 'E2ePass#2026x' };
const S = { u: process.env.E2E_STUDENT || 'e2e_student', p: process.env.E2E_STUDENT_PW || 'E2ePass#2026x' };
const CLASS_NAME = process.env.E2E_CLASS || 'E2E 自动化班';
const ROSTER = process.env.E2E_ROSTER || '1001 E2E 学生\n1002 王五';
const ANSWERS = [
  '我的系统用多智能体分工：检索、出题、评审各一个，主控编排。架构分三层，对外一个入口。',
  '如果依赖失效，我做了降级：先切兜底通道，再退回本地规则评分。代价是评分粒度变粗，用户可感知。',
  '实训场景里单 Agent 会失败在"追问"这一环：它不会根据上一轮回答调整问题深度，我们靠三角色互评解决。',
  '线上故障我们按影响面排优先级：先止血再定位。恢复时间 15 分钟，依据是上次同类故障的实际耗时。',
  '代码冲突我先确认对方诉求和交付时间，再谈实现；有隐患就给出可复现的最小用例，而不是直接否定。',
];
const log = (...a) => console.log(...a);

async function login(page, u, p) {
  // 换角色前先清登录态：否则 /login 被守卫弹回首页，表单根本不存在
  await page.goto(BASE + 'login', { waitUntil: 'domcontentloaded' });
  await page.evaluate(() => { try { localStorage.clear(); } catch { /* noop */ } });
  await page.goto(BASE + 'login', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(1200);
  await page.locator('input').nth(0).fill(u);
  await page.locator('input').nth(1).fill(p);
  await page.getByRole('button', { name: '登录', exact: true }).last().click();
  await page.waitForTimeout(3000);
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ channel: 'chrome' });
  const page = await (await browser.newContext({ viewport: { width: 1440, height: 1000 } })).newPage();
  const errs = [];
  page.on('pageerror', e => errs.push('PAGEERROR ' + String(e.message).slice(0, 140)));
  page.on('response', r => {
    if (r.status() >= 400 && r.url().includes('/api/')) errs.push(`HTTP ${r.status()} ${r.url().split('/api/')[1]}`.slice(0, 130));
  });

  // ── A：教师建班 → 花名册 → 发任务 ─────────────────────────────────
  await login(page, T.u, T.p);
  log('A1 教师登录落点:', page.url(), '（期望 .../teacher，不是 /diagnostic/start）');
  await page.goto(BASE + 'career/teacher', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(2500);
  await page.getByPlaceholder(/班级名称/).fill(CLASS_NAME);
  await page.getByRole('button', { name: '创建', exact: true }).click();
  await page.waitForTimeout(2500);
  await page.getByRole('button', { name: new RegExp(CLASS_NAME) }).first().click();
  await page.waitForTimeout(1500);
  await page.locator('textarea').first().fill(ROSTER);
  await page.getByRole('button', { name: '导入花名册' }).click();
  await page.waitForTimeout(2500);
  await page.getByRole('button', { name: '发布任务' }).click();
  await page.waitForTimeout(3500);
  await page.screenshot({ path: path.join(OUT, '10-teacher-task.png'), fullPage: true });
  const m = (await page.locator('body').innerText()).match(/任务码[：:]\s*([A-Za-z0-9]{4,12})/);
  const CODE = m ? m[1] : null;
  log('A2 任务码:', CODE);
  if (!CODE) throw new Error('未取到任务码');

  // ── B：学生凭码加入 → 对抗 → 六维报告 ─────────────────────────────
  await login(page, S.u, S.p);
  log('B1 学生登录落点:', page.url());
  await page.goto(BASE + 'career/teacher', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(1800);
  log('B1b 学生访问 /career/teacher 后落点:', new URL(page.url()).pathname, '（期望回到 app 根，被守卫拦下）');

  await page.goto(BASE + 'career/training', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(2500);
  await page.getByPlaceholder(/输入任务码/).fill(CODE);
  await page.getByRole('button', { name: /加入实训/ }).click();
  await page.waitForTimeout(3000);
  await page.screenshot({ path: path.join(OUT, '11-student-joined.png'), fullPage: true });
  log('B2 教师任务已加入态:', (await page.locator('body').innerText()).includes('教师任务已加入'));

  await page.getByRole('button', { name: /开始.*实训/ }).click();
  await page.waitForFunction(() => [...document.querySelectorAll('button')].some(b => b.innerText.includes('进入对抗')),
    null, { timeout: 120000 });
  await page.screenshot({ path: path.join(OUT, '12-briefing.png'), fullPage: true });
  const brief = await page.locator('body').innerText();
  const op = brief.match(/对手开场提问\s*\n?\s*“?([^\n”]{10,220})/);
  log('B3 简报开场问题:', op ? op[1].slice(0, 100) : '(未匹配)');

  await page.getByRole('button', { name: /进入对抗/ }).click();
  const ans = page.locator('textarea.answer-input');
  await ans.waitFor({ timeout: 40000 });
  await page.waitForTimeout(1500);
  for (let i = 0; i < 5; i++) {
    await ans.fill(ANSWERS[i]);
    // 不能用「按钮变可用」判完成：提交后输入框清空，按钮按设计就是禁用的
    await Promise.all([
      page.waitForResponse(r => r.url().includes('/answer') && r.request().method() === 'POST', { timeout: 150000 }),
      page.getByRole('button', { name: /提交作答/ }).click(),
    ]);
    await page.waitForTimeout(900);
  }
  await page.screenshot({ path: path.join(OUT, '12b-battle.png'), fullPage: true });
  log('B4 对抗进度:', ((await page.locator('body').innerText()).match(/第 \d+\/\d+ 轮/) || ['(无)'])[0]);

  await page.getByRole('button', { name: /提前结束出报告/ }).click();
  await page.waitForFunction(() => document.body.innerText.includes('六维素养评估报告'), null, { timeout: 120000 })
    .catch(() => log('B5 警告：未在时限内出现「六维素养评估报告」'));
  await page.waitForTimeout(1500);
  await page.screenshot({ path: path.join(OUT, '13-report.png'), fullPage: true });
  const rep = await page.locator('body').innerText();
  log('B5 综合得分:', (rep.match(/综合得分\s*([\d.]+)/) || ['', '(未取到)'])[1]);
  log('B5 评估来源:', rep.includes('AI评估') ? 'AI评估' : (rep.includes('规则评估') ? '规则评估' : '(无)'));

  // ── C：教师看板（须重新以教师身份登录） ────────────────────────────
  await login(page, T.u, T.p);
  await page.goto(BASE + 'career/teacher', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(2500);
  await page.getByRole('button', { name: new RegExp(CLASS_NAME) }).first().click();
  await page.waitForTimeout(1500);
  await page.getByRole('button', { name: '看板', exact: true }).first().click();
  await page.waitForTimeout(4000);
  await page.screenshot({ path: path.join(OUT, '14-dashboard.png'), fullPage: true });
  const dash = await page.locator('body').innerText();
  const stat = dash.match(/参与\s*(\S+)\s*完成\s*(\S+)\s*完成率\s*(\S+)\s*可评估\s*(\S+)/);
  log('C1 班级统计(参与/完成/完成率/可评估):', stat ? stat.slice(1).join(' / ') : '(未匹配)');
  log('C1 含最弱维度与需关注:', /最弱维度/.test(dash) && /需关注/.test(dash));
  log('C1 看板含学生行:', dash.includes(S.u) || /E2E 学生/.test(dash));

  // ── D：看板 CSV 导出（拼图②产品向收尾；exportDashCsv 为纯前端生成，零后端依赖）──
  const exportBtn = page.getByRole('button', { name: /导出 CSV/ });
  const hasExport = await exportBtn.count();
  log('D0 导出按钮存在:', hasExport > 0);
  if (hasExport > 0) {
    const [download] = await Promise.all([
      page.waitForEvent('download', { timeout: 15000 }),
      exportBtn.first().click(),
    ]);
    const csvPath = path.join(OUT, '15-dashboard-export.csv');
    await download.saveAs(csvPath);
    const raw = fs.readFileSync(csvPath);
    const text = raw.toString('utf8');
    const bom = raw[0] === 0xEF && raw[1] === 0xBB && raw[2] === 0xBF;
    const lines = text.replace(/^\ufeff/, '').split('\n').filter(Boolean);
    const head = lines[0] || '';
    const cols = head.split(',');
    const hasStudent = lines.some(l => l.includes(S.u) || l.includes('E2E 学生'));
    const hasAgg = lines.some(l => l.includes('班级均分'));
    const coreOk = ['学号', '姓名', '是否加入', '完成场次', '总会话', 'best_overall'].every(k => head.includes(k));
    log('D1 下载文件名:', download.suggestedFilename(), `（期望 对抗实训看板_${CLASS_NAME}.csv）`);
    log('D2 BOM(UTF-8):', bom, '| 数据行数:', lines.length, '| 列数:', cols.length);
    log('D3 表头:', head);
    log('D4 含花名册学生行:', hasStudent, '| 含班级均分行:', hasAgg);
    log('D5 核心列齐全(≥12 列=6 核心+六维):', coreOk && cols.length >= 12);
    log('D6 落盘 CSV 与页面数据一致(学生行进 CSV):', hasStudent);
    await page.screenshot({ path: path.join(OUT, '15-dashboard-export.png'), fullPage: true });
  }

  log('ERR:', JSON.stringify([...new Set(errs)].slice(0, 8)));
  await browser.close();
})().catch(e => { console.error('FATAL', e.message); process.exit(1); });
