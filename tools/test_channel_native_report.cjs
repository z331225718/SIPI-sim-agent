// Developer-only browser and full-array check for the offline native report.
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
const receipt = JSON.parse(fs.readFileSync(path.join(path.dirname(report), 'receipt.json'), 'utf8'));
const physical = receipt.channel_policy === 'physical-voltage-v1';
assert.ok(physical || (receipt.channel_policy ?? 'pb-02-compat') === 'pb-02-compat');
for (const [name, identity] of Object.entries(receipt.artifacts)) {
  const file = path.join(path.dirname(report), name);
  assert.equal(fs.statSync(file).size, identity.byte_length);
  assert.equal(hash(file), identity.sha256);
}
const readCsv = name => {
  const lines = fs.readFileSync(path.join(path.dirname(report), name), 'utf8').trimEnd().split('\n');
  const names = lines.shift().trim().split(',');
  const columns = names.map(() => []);
  for (const line of lines) {
    const values = line.trim().split(',').map(Number);
    assert.equal(values.length, names.length);
    assert.ok(values.every(Number.isFinite));
    values.forEach((value, i) => columns[i].push(value));
  }
  return { names, columns };
};
const expected = { waveform: readCsv('waveforms.csv'), impulse: readCsv('channel-impulse.csv') };

(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'msedge' });
  const record = { passed: false, reportSha256: hash(report), scriptSha256: hash(__filename), views: [], errors: [] };
  try {
    for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }]) {
      const page = await browser.newPage({ viewport });
      page.on('pageerror', error => record.errors.push(String(error)));
      page.on('request', request => assert.ok(request.url().startsWith('file:'), request.url()));
      await page.goto(pathToFileURL(report).href, { waitUntil: 'load' });
      await page.waitForSelector('html[data-channel-report-ready="true"]');
      const allData = await page.evaluate(expected => {
        const data = JSON.parse(document.getElementById('channel-data').textContent);
        let valuesChecked = 0;
        for (const [kind, csv] of Object.entries(expected)) {
          const actual = [data[kind].time, ...data[kind].columns];
          if (actual.length !== csv.columns.length) throw new Error(`Column count: ${kind}`);
          actual.forEach((values, column) => {
            if (values.length !== csv.columns[column].length) throw new Error(`Row count: ${kind}`);
            values.forEach((value, index) => {
              if (!Object.is(value, csv.columns[column][index])) throw new Error(`Non-exact embedded value: ${kind}/${column}/${index}`);
              valuesChecked++;
            });
          });
        }
        return { valuesChecked, exactAgainstAllCsvRows: true };
      }, expected);
      const state = await page.evaluate(() => ({
        title: document.querySelector('h1').textContent,
        overflow: document.documentElement.scrollWidth > innerWidth + 1,
        acceptanceFalse: document.querySelector('.status').textContent.includes('acceptance: false'),
        plots: Array.from(document.querySelectorAll('.plot svg'), svg => ({
          curves: svg.querySelectorAll('polyline').length,
          pointsFinite: Array.from(svg.querySelectorAll('polyline'), p => Array.from(p.points).every(v => Number.isFinite(v.x) && Number.isFinite(v.y))).every(Boolean),
          labelsFit: Array.from(svg.querySelectorAll('text'), text => {
            const b = text.getBBox();
            const view = svg.viewBox.baseVal;
            return b.x >= 0 && b.y >= 0 && b.x + b.width <= view.width && b.y + b.height <= view.height;
          }).every(Boolean),
          source: svg.outerHTML,
        })),
        links: Array.from(document.querySelectorAll('a'), link => link.href),
      }));
      assert.equal(state.title, 'SIPI Channel');
      assert.equal(state.overflow, false);
      assert.equal(state.acceptanceFalse, true);
      assert.deepEqual(state.plots.map(p => p.curves), [4, 1]);
      assert.ok(state.plots.every(p => p.pointsFinite && p.labelsFit), JSON.stringify(state.plots.map(({source, ...rest}) => rest)));
      assert.equal(state.links.length, physical ? 7 : 6);
      for (const href of state.links) assert.ok(fs.statSync(fileURLToPath(href)).isFile());
      if (physical) {
        assert.ok(await page.getByText('Physical load voltage / absolute impulse origin / finite-band kernel', { exact: true }).isVisible());
        const frequencyLink = page.getByRole('link', { name: 'Physical frequency response CSV', exact: true });
        assert.equal(await frequencyLink.getAttribute('href'), 'frequency-response.csv');
      }

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
      const screenshot = path.join(output, `channel-${viewport.width}.png`);
      await page.screenshot({ path: screenshot, fullPage: true });
      const interactions = [];
      for (const kind of ['waveform', 'impulse']) {
        const section = page.locator(`section[data-view="${kind}"]`);
        const control = name => section.locator(`[data-control="${name}"]`);
        const last = expected[kind].columns[0].length - 1;
        await control('cursor').fill(String(last));
        await control('cursor').press('Tab');
        assert.equal(Number(await section.getAttribute('data-last-sample')), last);
        const readout = await section.locator('[data-value]').evaluateAll(nodes => Object.fromEntries(nodes.map(n => [n.dataset.value, Number(n.textContent)])));
        assert.equal(readout.sample_index, last);
        expected[kind].names.forEach((name, column) => assert.ok(Object.is(readout[name], expected[kind].columns[column][last]), `${kind}/${name}/last`));
        const lateShot = path.join(output, `${kind}-late-${viewport.width}.png`);
        await section.screenshot({ path: lateShot });
        await control('count').fill('9999999');
        await control('count').press('Tab');
        assert.equal(Number(await control('count').inputValue()), Math.min(last + 1, 4096));
        await control('count').fill('-3');
        await control('count').press('Tab');
        assert.equal(await control('count').inputValue(), '1');
        await control('position').focus();
        await control('position').press('End');
        assert.equal(Number(await section.getAttribute('data-first-sample')), last);
        assert.ok(await section.locator('polyline').evaluateAll(lines => lines.every(p => p.points.length === 1 && Number.isFinite(p.points[0].x) && Number.isFinite(p.points[0].y))));
        assert.equal(await section.locator('circle').count(), expected[kind].names.length - 1);
        await control('count').fill('');
        await control('count').press('Tab');
        assert.equal(await control('count').inputValue(), '1');
        await control('position').focus();
        await control('position').press('Home');
        await control('count').fill('17');
        await control('count').press('Tab');
        assert.equal(Number(await section.getAttribute('data-first-sample')), 0);
        const checks = section.locator('.legend input');
        for (let i = 0; i < await checks.count(); i++) await checks.nth(i).uncheck();
        assert.equal(await section.locator('polyline').count(), 0);
        assert.ok(await section.getByText('No stages selected', { exact: true }).isVisible());
        for (let i = 0; i < await checks.count(); i++) await checks.nth(i).check();
        const projection = await section.evaluate((section, expected) => {
          const data = expected.columns;
          const first = Number(section.dataset.firstSample), last = Number(section.dataset.lastSample);
          const width = section.querySelector('svg').viewBox.baseVal.width;
          const values = data.slice(1).flatMap(column => column.slice(first, last + 1));
          const low = Math.min(0, ...values), high = Math.max(0, ...values), span = Math.max(high - low, 1e-12);
          for (const [column, line] of Array.from(section.querySelectorAll('polyline')).entries()) {
            if (line.points.length !== last - first + 1) return false;
            for (let i = first; i <= last; i++) {
              const point = line.points[i - first];
              const x = first === last ? (80 + width - 20) / 2 : 80 + (data[0][i] - data[0][first]) / (data[0][last] - data[0][first]) * (width - 100);
              const y = 250 - (data[column + 1][i] - low) / span * 226;
              // SVGPoint exposes float32 coordinates; source and readout checks above use exact f64.
              if (Math.abs(point.x - x) > 1e-3 || Math.abs(point.y - y) > 1e-3) return false;
            }
          }
          return true;
        }, expected[kind]);
        assert.equal(projection, true, `${kind} original contiguous point projection`);
        const plot = section.locator('.plot svg');
        const bounds = await plot.boundingBox();
        await plot.hover({ position: { x: bounds.width - 21, y: 150 } });
        assert.equal(Number(await control('cursor').inputValue()), Math.min(last, 16));
        interactions.push({ kind, lastSampleExact: true, singlePointFinite: true, limitsAndEmptyInputChecked: true, legendChecked: true, originalPointProjectionChecked: true, pointerCursorChecked: true, lateScreenshotSha256: hash(lateShot) });
      }
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false);
      const fallbackPage = await browser.newPage({ viewport, javaScriptEnabled: false });
      await fallbackPage.goto(pathToFileURL(report).href);
      assert.equal(await fallbackPage.locator('polyline').count(), 5);
      assert.equal(await fallbackPage.locator('.controls:visible').count(), 0);
      await fallbackPage.close();
      await page.getByText('Effective request', { exact: true }).click();
      assert.equal(await page.locator('details').first().evaluate(d => d.open), true);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false);
      await page.getByRole('link', { name: 'Run receipt', exact: true }).click();
      assert.ok(page.url().endsWith('/receipt.json'));
      record.views.push({ viewport, ...state, allData, interactions, staticFallbackChecked: true, coloredPixels, screenshotSha256: hash(screenshot), detailsExpanded: true, receiptLinkOpened: true });
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
