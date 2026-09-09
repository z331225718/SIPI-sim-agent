const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL, fileURLToPath } = require('node:url');
const { chromium } = require('playwright');

async function main() {
  const report = path.resolve(process.argv[2]);
  const output = path.resolve(process.argv[3]);
  fs.mkdirSync(output, { recursive: false });
  const root = path.dirname(report);
  const result = JSON.parse(fs.readFileSync(path.join(root, 'result.json'), 'utf8'));
  const completeCases = result.cases.filter(item => item.runs.length);
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const proof = [];
  try {
    for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }]) {
      const page = await browser.newPage({ viewport });
      const errors = [];
      page.on('pageerror', error => errors.push(String(error)));
      await page.goto(pathToFileURL(report).href, { waitUntil: 'networkidle' });
      await page.locator('img').last().waitFor();
      assert.equal(await page.title(), 'SIPI / ADS Channel Bench');
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
      const images = await page.locator('img').evaluateAll(items => items.map(item => ({
        src: item.src, complete: item.complete, width: item.naturalWidth, height: item.naturalHeight,
      })));
      assert.equal(images.length, completeCases.length * 2);
      for (const img of images) {
        assert(img.complete && img.width === 1680 && img.height === 812);
        const data = fs.readFileSync(fileURLToPath(img.src));
        const colored = await page.evaluate(async url => {
          const img = new Image();
          img.src = url;
          await img.decode();
          const canvas = document.createElement('canvas');
          canvas.width = img.width;
          canvas.height = img.height;
          const context = canvas.getContext('2d');
          context.drawImage(img, 0, 0);
          const pixels = context.getImageData(0, 0, img.width, img.height).data;
          let count = 0;
          for (let i = 0; i < pixels.length; i += 4) {
            const rgb = [pixels[i], pixels[i + 1], pixels[i + 2]];
            if (Math.max(...rgb) - Math.min(...rgb) > 30 && Math.min(...rgb) < 210) count++;
          }
          return count;
        }, `data:image/png;base64,${data.toString('base64')}`);
        assert(colored > 500, `${img.src}: blank plot`);
      }
      const links = await page.locator('a').evaluateAll(items => items.map(item => item.href));
      for (const link of links) {
        const url = new URL(link);
        assert.equal(url.protocol, 'file:');
        assert(fs.statSync(fileURLToPath(url)).isFile());
      }
      await page.screenshot({ path: path.join(output, `overview-${viewport.width}.png`) });
      await page.locator('summary').click();
      assert(await page.locator('details').evaluate(item => item.open));
      const expectedGates = result.cases.reduce((n, item) => n + item.runs.reduce((k, run) => k + Object.keys(run.gates).length, 0), 0);
      const failedCases = result.cases.filter(item => item.error).length;
      assert.equal(await page.locator('details tbody tr').count(), expectedGates + failedCases);
      if (completeCases.some(item => item.runs[0].dc_reference)) {
        const version = result.schema.endsWith('.v3') ? 'v3' : 'v2';
        assert(await page.getByText(`Reference ${version}:`, { exact: false }).isVisible());
        assert(await page.getByRole('columnheader', { name: 'Raw line control', exact: true }).isVisible());
      }
      await page.locator('summary').click();
      await page.locator(`section#${completeCases[1].name}`).scrollIntoViewIfNeeded();
      await page.screenshot({ path: path.join(output, `curves-${viewport.width}.png`) });
      await page.locator('section').first().getByRole('link', { name: 'Comparison', exact: true }).click();
      await page.waitForURL('**/comparison.json');
      assert.equal(errors.length, 0, errors.join('\n'));
      proof.push({ viewport, images: images.length, links: links.length, gates: expectedGates, incompleteCases: failedCases, nonblank: true, noHorizontalPageOverflow: true });
      await page.close();
    }
  } finally {
    await browser.close();
  }
  fs.writeFileSync(path.join(output, 'visual-verification.json'), JSON.stringify({ passed: true, proof }, null, 2), { flag: 'wx' });
  process.stdout.write(JSON.stringify(proof));
}

main().catch(error => { process.stderr.write(`${error.stack}\n`); process.exitCode = 1; });
