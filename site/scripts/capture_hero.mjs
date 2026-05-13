// Capture a real hero screenshot of the /map page.
// Forces the MapLibre canvas to fill the viewport so the hero crop is hero-sized.
// Writes docs/screenshots/map-hero.png.

import { chromium } from "playwright";
import { execSync } from "node:child_process";
import path from "node:path";

const ROOT = "/Users/xavier/Desktop/ghost-watts";
const OUT_PNG = path.join(ROOT, "docs/screenshots/map-hero.png");

async function main() {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({
    viewport: { width: 1600, height: 900 },
    deviceScaleFactor: 1,
    reducedMotion: "reduce",
  });
  const page = await ctx.newPage();

  page.on("pageerror", (e) => console.error("[pageerror]", e.message));
  page.on("console", (msg) => {
    if (msg.type() === "error") console.error("[console.error]", msg.text());
  });

  console.log("[hero] navigating to /map");
  await page.goto("http://localhost:4321/map", { waitUntil: "networkidle", timeout: 30000 });

  // Hide the click-a-city sidebar and the surrounding article chrome, then
  // collapse the grid so the map fills the whole content column. The map
  // page wraps content in `max-w-6xl` (1152 px); we override that for the
  // capture by promoting the map root to viewport width.
  await page.addStyleTag({
    content: `
      header, footer, .max-w-6xl section, .max-w-6xl details, h1, h2, h3, p { display: none !important; }
      #map-root { grid-template-columns: 1fr !important; max-width: 100vw !important; padding: 0 !important; }
      aside#side-panel { display: none !important; }
      #map { width: 100% !important; height: 100vh !important; border: 0 !important; border-radius: 0 !important; }
      body { padding: 0 !important; margin: 0 !important; }
    `,
  });

  // Tell MapLibre the container changed size, then wait for the canvas to
  // expand to match.
  await page.evaluate(() => window.dispatchEvent(new Event("resize")));
  await page.waitForFunction(
    () => {
      const c = document.querySelector(".maplibregl-canvas");
      if (!c) return false;
      const r = c.getBoundingClientRect();
      return r.width >= 1200 && r.height >= 600;
    },
    { timeout: 15000 },
  );

  // Give tiles + data layers a beat to re-stream into the new viewport.
  await page.waitForTimeout(5000);

  const clip = { x: 0, y: 0, width: 1600, height: 900 };
  await page.screenshot({ path: OUT_PNG, clip, type: "png" });
  const size = execSync(`stat -f '%z' '${OUT_PNG}'`).toString().trim();
  console.log(`[hero] wrote ${OUT_PNG} (${size} bytes, ${clip.width}x${clip.height} clip @ 2x)`);

  await browser.close();
}

main().catch((e) => {
  console.error("[hero] failed:", e);
  process.exit(1);
});
