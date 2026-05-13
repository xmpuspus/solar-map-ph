// Run with: node scripts/qa_screenshots.mjs
// Captures full-page screenshots of every public page at 4 viewports.
// Used as the visual QA gate for SolarMap.PH pre-launch.
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";

const BASE = process.env.QA_BASE || "http://localhost:4322";
const OUT_DIR = path.resolve(process.cwd(), "../docs/screenshots/qa-2026-05");
const VIEWPORTS = [
  { name: "375", width: 375, height: 812 },
  { name: "414", width: 414, height: 896 },
  { name: "768", width: 768, height: 1024 },
  { name: "1024", width: 1024, height: 768 },
];
const PAGES = [
  { name: "index", path: "/" },
  { name: "map", path: "/map" },
  { name: "methodology", path: "/methodology" },
  { name: "safety", path: "/safety" },
  { name: "faq", path: "/faq" },
  { name: "privacy", path: "/privacy" },
];

fs.mkdirSync(OUT_DIR, { recursive: true });

const browser = await chromium.launch();
const errors = [];
for (const vp of VIEWPORTS) {
  const ctx = await browser.newContext({ viewport: { width: vp.width, height: vp.height } });
  const page = await ctx.newPage();
  page.on("pageerror", (err) => errors.push(`${vp.name} ${page.url()}: ${err.message}`));
  page.on("console", (msg) => {
    if (msg.type() === "error") errors.push(`${vp.name} ${page.url()} console: ${msg.text()}`);
  });
  for (const p of PAGES) {
    const url = BASE + p.path;
    try {
      await page.goto(url, { waitUntil: "networkidle", timeout: 15000 });
    } catch (e) {
      try {
        await page.goto(url, { waitUntil: "domcontentloaded", timeout: 15000 });
      } catch (e2) {
        errors.push(`${vp.name} ${url}: navigate failed: ${e2.message}`);
        continue;
      }
    }
    await page.waitForTimeout(500);
    const file = path.join(OUT_DIR, `${vp.name}-${p.name}.png`);
    await page.screenshot({ path: file, fullPage: true });
    console.log(`saved ${path.relative(process.cwd(), file)}`);
  }
  await ctx.close();
}
await browser.close();
if (errors.length) {
  console.log(`\n=== ${errors.length} page errors / console errors ===`);
  for (const e of errors) console.log(`  ${e}`);
} else {
  console.log("\n=== no page errors or console errors ===");
}
