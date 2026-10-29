// ui_drive.mjs — DATABASE-001 T-05 Vue 端真实 UI 验收驱动（Playwright/Chromium）。
// 由 tests/basic/verify_basic.py 调度；全部经由真实前端页面（无 store 直连、
// 无注入）。链路：打开→树→浏览(分页/搜索/NULL)→Schema→SQL(成功/拒绝/引擎错)→切库。
// 用法: node ui_drive.mjs <front-url> <dbA-path> <dbB-path>
// 输出：逐行 `PASS|FAIL: <step>`；末行 `SUMMARY {json}`；退出码 0/1。

let chromium;
try {
  ({ chromium } = await import('playwright'));
} catch {
  const { pathToFileURL } = await import('node:url');
  const candidates = [process.env.PLAYWRIGHT_MODULE].filter(Boolean);
  for (const c of candidates) {
    try {
      ({ chromium } = await import(pathToFileURL(c).href));
      break;
    } catch {}
  }
}
if (!chromium) {
  console.error('FAIL: playwright module not found (set PLAYWRIGHT_MODULE)');
  process.exit(2);
}

const frontUrl = process.argv[2];
const dbA = process.argv[3];
const dbB = process.argv[4];
if (!frontUrl || !dbA || !dbB) {
  console.error('usage: node ui_drive.mjs <front-url> <dbA> <dbB>');
  process.exit(2);
}

const results = [];
function record(step, ok, detail) {
  results.push({ step, ok: !!ok, detail: detail || '' });
  console.log(`${ok ? 'PASS' : 'FAIL'}: ${step}${detail ? ' — ' + detail : ''}`);
}

const browser = await chromium.launch();
try {
  const page = await browser.newPage();
  const pageErrors = [];
  page.on('pageerror', (e) => pageErrors.push(String(e)));
  await page.goto(frontUrl, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(2000);

  let body = await page.locator('body').innerText();
  record('ui-load', body.includes('Database Studio'), 'front page renders');
  record('no-demo-data', !body.includes('northwind') && !body.includes('Alfreds'),
         'demo strings absent before open');
  record('readonly-badge-closed', body.includes('未打开'), 'closed state visible');

  // 1. 打开 fixture A（真实路径输入 + 真实点击）
  const pathInput = page.locator('input[placeholder*="SQLite"]');
  if ((await pathInput.count()) === 0) throw new Error('path input not found');
  await pathInput.fill(dbA);
  await page.getByRole('button', { name: '打开' }).click();
  await page.waitForTimeout(1500);
  body = await page.locator('body').innerText();
  record('open-a', body.includes('basic_a.db') && body.includes('READ-ONLY'), 'file + readonly badge');
  record('open-a-counts', body.includes('4 Tables') && body.includes('1 Views') && body.includes('2 Indexes'),
         'real counts in header');
  record('tree-chinese', body.includes('客户资料'), 'Chinese table in tree');

  // 2. 数据表：真实列名 + 首行真实值
  record('data-headers', body.includes('company_name') && body.includes('contact_name'),
         'real column headers');
  record('data-first-row', body.includes('Alfreds Futterkiste'), 'real first row');

  // 3. NULL 显示：搜索带 NULL contact 的行
  const search = page.locator('input[placeholder*="Filter records"]');
  await search.fill('Taquer');
  await page.waitForTimeout(1200);
  body = await page.locator('body').innerText();
  record('null-cell-marker', body.includes('NULL'), 'NULL rendered for null contact_name');
  await search.fill('');
  await page.waitForTimeout(1000);

  // 4. 分页：audit_logs 1200 行
  await page.locator('text=audit_logs').first().click();
  await page.waitForTimeout(1200);
  body = await page.locator('body').innerText();
  record('audit-1200', body.includes('1200 rows'), 'total from engine');
  await page.getByRole('button', { name: '››' }).click();
  await page.waitForTimeout(1000);
  body = await page.locator('body').innerText();
  record('audit-last-page', body.includes('120 / 120'), 'last page reached');
  await page.getByRole('button', { name: '50', exact: true }).click();
  await page.waitForTimeout(1000);
  body = await page.locator('body').innerText();
  record('page-size-50', body.includes('Showing 1151 - 1200'), 'page size applied');

  // 5. Schema：中文表 DDL
  await page.locator('text=客户资料').first().click();
  await page.waitForTimeout(1000);
  await page.getByRole('button', { name: 'Schema' }).click();
  await page.waitForTimeout(800);
  body = await page.locator('body').innerText();
  record('schema-ddl', body.includes('CREATE TABLE 客户资料'), 'real DDL text');
  record('schema-cols', body.includes('姓名') && body.includes('备注'), 'real column names');

  // 6. SQL 控制台：成功 / 拒绝 / 引擎错误
  await page.getByRole('button', { name: 'SQL', exact: true }).click();
  await page.waitForTimeout(500);
  await page.getByRole('button', { name: 'GROUP BY' }).click();
  await page.waitForTimeout(300);
  await page.getByRole('button', { name: '▶ Run SQL' }).click();
  await page.waitForTimeout(1500);
  body = await page.locator('body').innerText();
  record('sql-agg-ok', body.includes('rows') && !body.includes('SQL 错误'), 'aggregate query ok');

  await page.getByRole('button', { name: '写语句(应拒绝)' }).click();
  await page.waitForTimeout(300);
  await page.getByRole('button', { name: '▶ Run SQL' }).click();
  await page.waitForTimeout(1000);
  body = await page.locator('body').innerText();
  record('sql-reject-banner', body.includes('已拒绝') && body.includes('not_readonly'),
         'guard rejection visible');

  const sqlInput = page.locator('input[placeholder*="只读 SQL"]');
  await sqlInput.fill('SELECT * FROM no_such_table');
  await page.getByRole('button', { name: '▶ Run SQL' }).click();
  await page.waitForTimeout(1000);
  body = await page.locator('body').innerText();
  record('sql-engine-error', body.includes('no such table'), 'engine error text shown');

  // 7. 切库 B：身份/计数/数据都变
  await pathInput.fill(dbB);
  await page.getByRole('button', { name: '打开' }).click();
  await page.waitForTimeout(1500);
  body = await page.locator('body').innerText();
  record('switch-b', body.includes('basic_b.db') && body.includes('2 Tables'), 'db B identity');
  record('switch-b-data', body.includes('SKU-A1'), 'db B data different');

  // 8. 切回 A：customers 数据恢复
  await pathInput.fill(dbA);
  await page.getByRole('button', { name: '打开' }).click();
  await page.waitForTimeout(1500);
  body = await page.locator('body').innerText();
  record('switch-back-a', body.includes('basic_a.db') && body.includes('Alfreds Futterkiste'),
         'db A data restored');

  record('no-page-errors', pageErrors.length === 0, pageErrors.join('; ').slice(0, 200));

  console.log('SUMMARY ' + JSON.stringify({ results, pageErrors }));
  process.exit(results.every((r) => r.ok) ? 0 : 1);
} finally {
  await browser.close();
}
