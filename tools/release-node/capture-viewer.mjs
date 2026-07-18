import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';

const [, , url, screenshotPath, reportPath, browserPath, nodeModules] = process.argv;
if (![url, screenshotPath, reportPath, browserPath, nodeModules].every(Boolean)) {
  process.stderr.write('usage: capture-viewer.mjs <url> <screenshot> <report> <browser> <node_modules>\n');
  process.exit(2);
}
const phases = [];
const checkpoint = (name) => {
  phases.push({ name, at: new Date().toISOString() });
  fs.writeFileSync(reportPath, JSON.stringify({ viewer: { status: 'running' }, console_errors: [], phases }, null, 2));
};
checkpoint('starting');
const requireFromInstall = createRequire(path.join(nodeModules, 'playwright-core', 'package.json'));
const { chromium } = requireFromInstall('playwright-core');
checkpoint('playwright_loaded');
const consoleErrors = [];
let browser;
try {
  browser = await chromium.launch({
    executablePath: browserPath,
    headless: true,
    timeout: 60000,
    args: ['--enable-unsafe-swiftshader', '--use-angle=swiftshader', '--enable-webgl', '--disable-gpu-sandbox'],
  });
  checkpoint('browser_launched');
  const page = await browser.newPage({ viewport: { width: 960, height: 540 }, deviceScaleFactor: 1 });
  page.on('console', (message) => { if (message.type() === 'error') consoleErrors.push(message.text()); });
  page.on('pageerror', (error) => consoleErrors.push(String(error)));
  page.on('response', (response) => { if (response.status() >= 400) consoleErrors.push(`HTTP ${response.status()} ${response.url()}`); });
  page.on('requestfailed', (request) => consoleErrors.push(`REQUEST_FAILED ${request.url()} ${request.failure()?.errorText || ''}`));
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });
  checkpoint('page_loaded');
  await page.waitForFunction(() => ['loaded', 'error'].includes(window.__BAF_RESULT__?.status), null, { timeout: 60000 });
  const viewer = await page.evaluate(() => window.__BAF_RESULT__);
  checkpoint('viewer_finished');
  await page.screenshot({ path: screenshotPath, type: 'png' });
  checkpoint('screenshot_captured');
  fs.writeFileSync(reportPath, JSON.stringify({ viewer, console_errors: consoleErrors, phases }, null, 2));
  if (viewer.status !== 'loaded' || consoleErrors.length) process.exitCode = 1;
} catch (error) {
  fs.writeFileSync(reportPath, JSON.stringify({ viewer: { status: 'error', error: String(error?.stack || error) }, console_errors: consoleErrors, phases }, null, 2));
  process.exitCode = 1;
} finally {
  await browser?.close();
}
