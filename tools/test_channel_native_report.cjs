// Developer-only visual check; the generated report has no JS/runtime dependency.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { pathToFileURL, fileURLToPath } = require('node:url');
const { chromium } = require('playwright');

const [reportArgument, outputArgument] = process.argv.slice(2);
assert.ok(reportArgument && outputArgument, 'Usage: node test_channel_native_report.cjs REPORT.html NEW_OUTPUT_DIRECTORY');
const report = path.resolve(reportArgument);
const output = path.resolve(outputArgument);
fs.mkdirSync(output);
const hash = file => crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');

(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'msedge' });
  const record = { passed: false, reportSha256: hash(report), scriptSha256: hash(__filename), views: [], errors: [] };
  try {
    for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }]) {
      const page = await browser.newPage({ viewport });
      page.on('pageerror', error => record.errors.push(String(error)));
      page.on('request', request => assert.ok(request.url().startsWith('file:'), request.url()));
      await page.goto(pathToFileURL(report).href, { waitUntil: 'load' });
      const state = await page.evaluate(() => ({
        title: document.querySelector('h1').textContent,
        overflow: document.documentElement.scrollWidth > innerWidth + 1,
        acceptanceFalse: document.querySelector('.status').textContent.includes('acceptance: false'),
        plots: Array.from(document.querySelectorAll('.plot svg'), svg => ({
          curves: svg.querySelectorAll('polyline').length,
          pointsFinite: Array.from(svg.querySelectorAll('polyline'), p => Array.from(p.points).every(v => Number.isFinite(v.x) && Number.isFinite(v.y))).every(Boolean),
          labelsFit: Array.from(svg.querySelectorAll('text'), text => {
            const b = text.getBBox();
            return b.x >= 0 && b.y >= 0 && b.x + b.width <= 1000 && b.y + b.height <= 280;
          }).every(Boolean),
          source: svg.outerHTML,
        })),
        links: Array.from(document.querySelectorAll('nav a'), link => link.href),
      }));
      assert.equal(state.title, 'SIPI Channel');
      assert.equal(state.overflow, false);
      assert.equal(state.acceptanceFalse, true);
      assert.deepEqual(state.plots.map(p => p.curves), [4, 1]);
      assert.ok(state.plots.every(p => p.pointsFinite && p.labelsFit), JSON.stringify(state.plots.map(({source, ...rest}) => rest)));
      assert.equal(state.links.length, 6);
      for (const href of state.links) assert.ok(fs.statSync(fileURLToPath(href)).isFile());

      // Rasterize actual SVG data in an isolated blank page, not by weakening
      // the report's CSP or injecting active content into its document.
      const pixelPage = await browser.newPage();
      const coloredPixels = await pixelPage.evaluate(async plots => {
        const result = [];
        for (const source of plots) {
          const url = URL.createObjectURL(new Blob([source], { type: 'image/svg+xml' }));
          try {
            const image = new Image(); image.src = url; await image.decode();
            const canvas = document.createElement('canvas'); canvas.width = 1000; canvas.height = 280;
            const context = canvas.getContext('2d'); context.drawImage(image, 0, 0, 1000, 280);
            const pixels = context.getImageData(0, 0, 1000, 280).data;
            let count = 0;
            for (let i = 0; i < pixels.length; i += 4) {
              if (pixels[i + 3] && Math.max(pixels[i], pixels[i + 1], pixels[i + 2]) - Math.min(pixels[i], pixels[i + 1], pixels[i + 2]) > 40) count++;
            }
            result.push(count);
          } finally { URL.revokeObjectURL(url); }
        }
        return result;
      }, state.plots.map(p => p.source));
      await pixelPage.close();
      assert.ok(coloredPixels.every(n => n > 500), String(coloredPixels));
      for (const plot of state.plots) delete plot.source;
      if (viewport.width < 600) {
        const scrolling = await page.locator('.plot').evaluateAll(plots => plots.every(plot => {
          plot.scrollLeft = plot.scrollWidth;
          const reached = plot.scrollLeft > 0;
          plot.scrollLeft = 0;
          return reached;
        }));
        assert.equal(scrolling, true);
      }
      const screenshot = path.join(output, `channel-${viewport.width}.png`);
      await page.screenshot({ path: screenshot, fullPage: true });
      await page.getByText('Effective request', { exact: true }).click();
      assert.equal(await page.locator('details').first().evaluate(d => d.open), true);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false);
      await page.getByRole('link', { name: 'Run receipt', exact: true }).click();
      assert.ok(page.url().endsWith('/receipt.json'));
      record.views.push({ viewport, ...state, coloredPixels, screenshotSha256: hash(screenshot), detailsExpanded: true, receiptLinkOpened: true });
      await page.close();
    }
    assert.deepEqual(record.errors, []);
    assert.equal(hash(report), record.reportSha256);
    record.passed = true;
    console.log(JSON.stringify({ passed: true, views: record.views.length }));
  } catch (error) {
    record.errors.push(String(error));
    throw error;
  } finally {
    fs.writeFileSync(path.join(output, 'visual-verification.json'), JSON.stringify(record, null, 2) + '\n');
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
