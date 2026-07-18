import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';

const [, , url, outputPath, reportPath, browserPath, nodeModules] = process.argv;
if (![url, outputPath, reportPath, browserPath, nodeModules].every(Boolean)) process.exit(2);
const requireFromInstall = createRequire(path.join(nodeModules, 'playwright-core', 'package.json'));
const { chromium } = requireFromInstall('playwright-core');
const errors = [];
let browser;
try {
  browser = await chromium.launch({ executablePath: browserPath, headless: true, timeout: 60000 });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  page.on('console', (message) => { if (message.type() === 'error') errors.push(message.text()); });
  page.on('pageerror', (error) => errors.push(String(error)));
  page.on('response', (response) => { if (response.status() >= 400) errors.push(`HTTP ${response.status()} ${response.url()}`); });
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.waitForFunction(() => [...document.images].every((image) => image.complete && image.naturalWidth > 0), null, { timeout: 30000 });
  await page.screenshot({ path: outputPath, type: 'png', fullPage: true });
  fs.writeFileSync(reportPath, JSON.stringify({ ok: errors.length === 0, console_errors: errors }, null, 2));
  if (errors.length) process.exitCode = 1;
} catch (error) {
  fs.writeFileSync(reportPath, JSON.stringify({ ok: false, console_errors: errors, error: String(error?.stack || error) }, null, 2));
  process.exitCode = 1;
} finally {
  await browser?.close();
}
