// Screenshot every page at the two QA viewports, both color schemes.
// Usage: node scripts/shoot.mjs <outdir> [baseUrl]
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";

const outDir = process.argv[2] ?? "../docs/screenshots/adhoc";
const base = process.argv[3] ?? "http://localhost:4321";

const pages = ["/", "/map", "/regions", "/methodology", "/safety", "/faq", "/privacy", "/me"];
const viewports = [
  { name: "1920x1080", width: 1920, height: 1080 },
  { name: "1440x900", width: 1440, height: 900 },
  { name: "390x844", width: 390, height: 844 },
];
const schemes = ["light", "dark"];

mkdirSync(outDir, { recursive: true });

const browser = await chromium.launch();
for (const scheme of schemes) {
  for (const vp of viewports) {
    const ctx = await browser.newContext({
      viewport: { width: vp.width, height: vp.height },
      deviceScaleFactor: 1,
      colorScheme: scheme,
    });
    const page = await ctx.newPage();
    for (const path of pages) {
      const slug = path === "/" ? "home" : path.replace(/\//g, "");
      await page.goto(base + path, { waitUntil: "networkidle", timeout: 60000 }).catch(() => {});
      await page.waitForTimeout(path === "/map" ? 4000 : 900);
      const h = await page.evaluate(() => document.documentElement.scrollHeight);
      await page.screenshot({
        path: `${outDir}/${slug}-${vp.name}-${scheme}.png`,
        fullPage: false,
      });
      console.log(`${slug} ${vp.name} ${scheme} scrollHeight=${h}`);
    }
    await ctx.close();
  }
}
await browser.close();
