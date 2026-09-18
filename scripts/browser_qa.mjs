import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
const require = createRequire(import.meta.url);
let chromium;
try {
  ({ chromium } = require('../web/node_modules/@playwright/test'));
} catch {
  ({ chromium } = require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES + '/playwright'));
}
const root = path.resolve(import.meta.dirname, '..');
const output = path.join(root, 'artifacts', 'browser');
await mkdir(output, { recursive: true });
const python = process.env.DP_QA_PYTHON || path.join(root, '.venv', 'bin', 'python');
const server = spawn(python, ['scripts/qa_server.py'], { cwd: root, stdio: ['ignore', 'pipe', 'pipe'] });
let logs = '';
server.stderr.on('data', (x) => {
  logs += String(x);
});
const checks = [],
  errors = [];
let browser;
const check = (name, condition) => {
  if (!condition) throw Error(name);
  checks.push(name);
};
const until = async (predicate) => {
  const end = Date.now() + 30000;
  while (Date.now() < end) {
    if (await predicate()) return;
    await new Promise((resolve) => setTimeout(resolve, 150));
  }
  throw Error('Timed out waiting for the pipeline state');
};
try {
  await new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(Error('QA server startup timeout: ' + logs)), 90000);
    server.stdout.on('data', (x) => {
      if (String(x).includes('QA_READY')) {
        clearTimeout(timeout);
        resolve();
      }
    });
    server.on('exit', (code) => reject(Error('QA server exited ' + code + ': ' + logs)));
  });
  let launchOptions = { headless: true, args: ['--no-sandbox'] };
  // Optional serverless browser for restricted test runners. Normal development uses Playwright's browser.
  if (process.env.DP_QA_CHROMIUM_MODULE) {
    const module = await import(process.env.DP_QA_CHROMIUM_MODULE);
    const bundled = module.default;
    launchOptions = {
      ...launchOptions,
      executablePath: process.env.DP_QA_BROWSER_PATH || (await bundled.executablePath()),
      args: bundled.args.filter((arg) => !['--single-process', '--disable-web-security'].includes(arg)),
    };
  }
  browser = await chromium.launch(launchOptions);
  const page = await browser.newPage({ viewport: { width: 1512, height: 1100 }, deviceScaleFactor: 1 });
  page.on('pageerror', (error) => errors.push(error.message));
  const failedResponses = [];
  page.on('response', (r) => {
    if (r.status() >= 400 && !r.url().endsWith('/api/auth/me'))
      failedResponses.push(r.status() + ' ' + r.url());
  });
  await page.goto('http://127.0.0.1:8765');
  await page.getByLabel('Email address').fill('qa@example.test');
  await page.getByLabel('Password', { exact: true }).fill('local-browser-test-password');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await page.getByRole('heading', { name: 'Reliability overview' }).waitFor();
  await page.getByText('Live updates connected', { exact: false }).waitFor();
  const get = (path) => page.evaluate(async (p) => (await fetch('/api' + p)).json(), path);
  let state = await get('/overview');
  check('Healthy baseline has 19 real datasets', state.stats.datasets === 19 && state.stats.healthy === 19);
  check('Baseline has no active incidents', state.stats.active_incidents === 0);
  await page.waitForTimeout(600);
  await page.screenshot({ path: path.join(output, 'overview-healthy.png'), fullPage: true });
  await page.getByRole('link', { name: 'Datasets', exact: true }).click();
  await page.getByRole('textbox', { name: 'Filter datasets' }).fill('raw_payments');
  await page.getByRole('button', { name: 'raw_payments', exact: true }).click();
  await page.getByRole('tab', { name: 'Schema & profile' }).click();
  await page.getByText('payment_method', { exact: true }).first().waitFor();
  check('Dataset profile renders measured schema', true);
  await page.getByRole('link', { name: 'Quality rules', exact: true }).click();
  await page.getByRole('button', { name: 'Create rule', exact: true }).click();
  await page.getByLabel('Rule name').fill('QA required order ID');
  await page.getByLabel('Column', { exact: true }).fill('order_id');
  await page.getByRole('button', { name: 'Create rule', exact: true }).last().click();
  await page.getByText('QA required order ID', { exact: true }).waitFor();
  check(
    'Rule creation persists through API',
    (await get('/rules')).some((r) => r.name === 'QA required order ID'),
  );
  await page.getByRole('link', { name: 'Sources', exact: true }).click();
  await page.getByRole('button', { name: 'Test connection' }).first().click();
  await page.getByText('passed', { exact: true }).first().waitFor();
  check('SQL source connection check works', true);
  await page.getByRole('link', { name: 'Failure lab', exact: false }).click();
  await page.getByRole('button', { name: /Country code change/ }).click();
  const submitted = page.waitForResponse(
    (r) => r.url().endsWith('/api/runs') && r.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Inject & run', exact: true }).click();
  const faultRun = (await (await submitted).json()).id;
  await until(async () => {
    state = await get('/overview');
    return (
      state.runs.find((r) => r.id === faultRun)?.status === 'succeeded' && state.stats.active_incidents > 0
    );
  });
  await writeFile(path.join(output, 'fault-state.json'), JSON.stringify(state, null, 2));
  check('Injected source fault forms one coherent incident', state.stats.active_incidents === 1);
  const incidentId = state.incidents[0].id;
  check('Raw payment source ranks first', state.incidents[0].root_dataset_id === 'raw_payments');
  await page.getByRole('link', { name: 'Overview', exact: true }).click();
  await page.getByRole('heading', { name: 'Reliability overview' }).waitFor();
  await page.waitForTimeout(600);
  await page.screenshot({ path: path.join(output, 'overview-incident.png'), fullPage: true });
  await page.goto('http://127.0.0.1:8765/#incidents/' + incidentId);
  await page.getByRole('button', { name: 'Generate investigation', exact: true }).click();
  await page.getByRole('heading', { name: 'Verified evidence', exact: true }).waitFor();
  check('Evidence-grounded report generated', true);
  await page.screenshot({ path: path.join(output, 'incident-investigation.png'), fullPage: true });
  await page.getByRole('button', { name: 'Assign to me', exact: true }).click();
  await page.getByText('qa@example.test', { exact: true }).waitFor();
  check('Incident ownership and state update work', true);
  await page.getByRole('tab', { name: /Evidence/ }).click();
  await page.locator('.evidence-ledger summary').first().click();
  await page.locator('.evidence-body').first().waitFor();
  await page.screenshot({ path: path.join(output, 'evidence-ledger.png'), fullPage: true });
  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('link', { name: 'Export report' }).click();
  const download = await downloadPromise;
  check('Incident report exports as Markdown', download.suggestedFilename().endsWith('.md'));
  await page.goto('http://127.0.0.1:8765/#lineage/raw_payments');
  await page.locator('.react-flow__node').first().waitFor();
  await page.getByRole('heading', { name: 'Asset details', exact: true }).waitFor();
  await page.screenshot({ path: path.join(output, 'lineage.png'), fullPage: true });
  check(
    'Interactive lineage is connected to dataset registry',
    (await page.locator('.react-flow__node').count()) === 19,
  );
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('http://127.0.0.1:8765/#overview');
  await page.getByRole('heading', { name: 'Reliability overview' }).waitFor();
  await page.waitForTimeout(600);
  if (await page.getByRole('button', { name: 'Dismiss notification' }).count())
    await page.getByRole('button', { name: 'Dismiss notification' }).click();
  check(
    'Mobile navigation is hidden until requested',
    await page.locator('.sidebar').evaluate((el) => el.getBoundingClientRect().right <= 1),
  );
  await page.screenshot({ path: path.join(output, 'mobile-overview.png'), fullPage: true });
  check(
    'Mobile viewport has no document overflow',
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
  );
  await page.getByRole('button', { name: 'Open navigation' }).click();
  await page.getByRole('link', { name: 'Incidents', exact: true }).click();
  await page.getByRole('heading', { name: 'Incident inbox', exact: true }).waitFor();
  check('Mobile navigation works', true);
  await page.setViewportSize({ width: 1512, height: 1100 });
  await page.goto('http://127.0.0.1:8765/#simulator');
  await page.getByRole('button', { name: 'Restore healthy source', exact: true }).click();
  for (let n = 0; n < 2; n++) {
    const queued = page.waitForResponse(
      (r) => r.url().endsWith('/api/runs') && r.request().method() === 'POST',
    );
    await page.getByRole('button', { name: 'Run pipeline', exact: true }).click();
    const recoveryRun = (await (await queued).json()).id;
    await until(async () => (await get('/runs')).find((r) => r.id === recoveryRun)?.status === 'succeeded');
  }
  check(
    'Two clean runs automatically resolve the incident',
    (await get('/incidents/' + incidentId)).incident.status === 'resolved',
  );
  await page.goto('http://127.0.0.1:8765/api/docs');
  await page.getByRole('heading', { name: /Data Police API/ }).waitFor();
  check('API documentation loads without a third-party CDN', true);
  check('No JavaScript runtime errors', errors.length === 0);
  check('No unexpected HTTP errors', failedResponses.length === 0);
  await writeFile(
    path.join(output, 'results.json'),
    JSON.stringify({ status: 'passed', checks, errors, failedResponses }, null, 2),
  );
  process.stdout.write(JSON.stringify({ status: 'passed', checks, screenshots: output }, null, 2) + '\n');
} catch (error) {
  await writeFile(
    path.join(output, 'results.json'),
    JSON.stringify({ status: 'failed', checks, error: String(error), errors, logs }, null, 2),
  );
  process.stderr.write(String(error) + '\n');
  process.exitCode = 1;
} finally {
  if (browser) await browser.close();
  server.kill('SIGTERM');
}
