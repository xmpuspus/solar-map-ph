// Storyboarded hero GIF for the README. Records a real interaction sequence
// that surfaces the project's payoff: city stats sidebar, then per-building
// kWp / panel area / confidence / OSM way id readout.
//
// Story (10 s):
//   Stage A  0.0-2.0  Wide overview. Choropleth + stats strip + dots.
//   Stage B  2.0-3.5  Click Quezon City. Sidebar opens with detection summary.
//   Stage C  3.5-5.0  flyTo a 1266 kWp retail rooftop at zoom 16.5.
//   Stage D  5.0-7.5  Click the building. Sidebar swaps to detection-detail
//                     card (kWp, panel area, confidence, OSM id, building type).
//   Stage E  7.5-10.0 flyTo back to wide. Final clean panoramic frame.
//
// Output: docs/screenshots/map-hero.gif

import { chromium } from "playwright";
import { execSync } from "node:child_process";
import { mkdirSync, readdirSync, statSync, unlinkSync } from "node:fs";
import path from "node:path";

const ROOT = "/Users/xavier/Desktop/ghost-watts";
const OUT_GIF = path.join(ROOT, "docs/screenshots/map-hero.gif");
const VIDEO_DIR = "/tmp/ghost-watts-hero-video";
const SITE_URL = "http://localhost:4322/map";

// Real high-confidence retail rooftop, OSM way 48173643.
// Properties: kWp 1265.93, panel area 7595.6 m^2, confidence 0.961,
// building_type retail, in Quezon City.
const BUILDING = { lng: 120.98425, lat: 14.65516 };

// QC interior point well inside the polygon, used for the city click.
const QC_POINT = { lng: 121.043, lat: 14.668 };

// Initial fitBounds extent (Meralco franchise).
const WIDE = { lng: 121.05, lat: 14.6, zoom: 9.5 };

async function settleMap(page) {
  await page.evaluate(() => {
    const m = window.__ghostWattsMap;
    if (m && m.resize) m.resize();
    window.dispatchEvent(new Event("resize"));
  });
  // Poll for a canvas with non-zero geometry. Don't require a specific size
  // since the layout depends on whether the CSS injection landed.
  await page.waitForFunction(
    () => {
      const c = document.querySelector(".maplibregl-canvas");
      if (!c) return false;
      const r = c.getBoundingClientRect();
      return r.width >= 400 && r.height >= 300;
    },
    { timeout: 15000 },
  );
  // Tile streaming after the resize.
  await page.waitForTimeout(1800);
}

async function clickLngLat(page, lng, lat) {
  const mapBox = await page.locator(".maplibregl-map").first().boundingBox();
  const screen = await page.evaluate(({ lng, lat }) => {
    const p = window.__ghostWattsMap.project([lng, lat]);
    return { x: p.x, y: p.y };
  }, { lng, lat });
  // Hover for ~150ms before clicking so MapLibre's mouseenter handler swaps
  // the cursor and the click is registered against the right layer.
  await page.mouse.move(mapBox.x + screen.x, mapBox.y + screen.y);
  await page.waitForTimeout(180);
  await page.mouse.click(mapBox.x + screen.x, mapBox.y + screen.y);
}

async function main() {
  mkdirSync(VIDEO_DIR, { recursive: true });
  for (const f of readdirSync(VIDEO_DIR)) {
    try { unlinkSync(path.join(VIDEO_DIR, f)); } catch {}
  }

  const browser = await chromium.launch();
  const ctx = await browser.newContext({
    viewport: { width: 1400, height: 800 },
    deviceScaleFactor: 1,
    reducedMotion: "no-preference",
    recordVideo: { dir: VIDEO_DIR, size: { width: 1400, height: 800 } },
  });
  const page = await ctx.newPage();
  page.on("pageerror", (e) => console.error("[pageerror]", e.message));

  console.log("[gif] loading /map");
  await page.goto(SITE_URL, { waitUntil: "networkidle", timeout: 30000 });

  // CSS injection after load -- by the time we reach here, the map and
  // sidebar DOM elements exist. The map instance is created during Astro
  // hydration, exposed as window.__ghostWattsMap.
  // Tight hero crop: keep the stats strip (4 KPI cells) + map + sidebar.
  // Hide the page header, footer, the long description paragraph, and the
  // collapsible "How to read this map" so the data + interactivity is what
  // a reader sees.
  await page.addStyleTag({
    content: `
      header, footer { display: none !important; }
      .max-w-6xl details { display: none !important; }
      /* The hero <h1> and the explainer <p> sit in the first <section> on the page.
         They eat 200+ vertical px we want for the map. The stats strip is the
         second .max-w-6xl wrapper -- keep that. */
      section.max-w-6xl:nth-of-type(1) { display: none !important; }
      .max-w-6xl { max-width: 100vw !important; padding-left: 12px !important; padding-right: 12px !important; }
      #map { height: 720px !important; }
      #side-panel { height: 720px !important; max-height: 720px !important; overflow: auto; }
      body { padding: 0 !important; margin: 0 !important; }
    `,
  });

  await page.waitForFunction(() => window.__ghostWattsMap !== undefined, { timeout: 15000 });
  await settleMap(page);
  const canvasSize = await page.evaluate(() => {
    const c = document.querySelector(".maplibregl-canvas");
    const r = c.getBoundingClientRect();
    return { w: r.width, h: r.height };
  });
  console.log(`[gif] canvas: ${canvasSize.w}x${canvasSize.h}`);

  // ===== Stage A: wide overview =========================================
  console.log("[gif] A wide overview");
  await page.evaluate((c) => {
    window.__ghostWattsMap.jumpTo({ center: [c.lng, c.lat], zoom: c.zoom });
  }, WIDE);
  await page.waitForTimeout(2000);

  // ===== Stage B: click Quezon City =====================================
  console.log("[gif] B click Quezon City");
  await clickLngLat(page, QC_POINT.lng, QC_POINT.lat);
  // Verify the sidebar actually swapped. If it didn't (the click missed the
  // polygon at this zoom), we won't fail the run, just log it.
  const cityShown = await page.evaluate(
    () => !document.getElementById("city-detail")?.classList.contains("hidden"),
  );
  console.log(`[gif]   city-detail visible: ${cityShown}`);
  await page.waitForTimeout(1500);

  // ===== Stage C: flyTo retail building =================================
  console.log("[gif] C flyTo retail building");
  await page.evaluate((b) => {
    window.__ghostWattsMap.flyTo({
      center: [b.lng, b.lat], zoom: 16.5, duration: 1500, essential: true,
    });
  }, BUILDING);
  await page.waitForTimeout(1700);

  // ===== Stage D: click the building polygon ============================
  console.log("[gif] D click building polygon");
  // Wait until buildings-fill has the target feature rendered.
  await page.waitForFunction(
    (b) => {
      const m = window.__ghostWattsMap;
      if (!m.getLayer("buildings-fill")) return false;
      const feats = m.queryRenderedFeatures(m.project([b.lng, b.lat]), {
        layers: ["buildings-fill"],
      });
      return feats && feats.length > 0;
    },
    BUILDING,
    { timeout: 10000 },
  );
  await clickLngLat(page, BUILDING.lng, BUILDING.lat);
  const detShown = await page.evaluate(
    () => !document.getElementById("detection-detail")?.classList.contains("hidden"),
  );
  console.log(`[gif]   detection-detail visible: ${detShown}`);
  // Hold long enough for a reader to actually read the kWp / area / OSM id
  // values that just appeared.
  await page.waitForTimeout(2500);

  // ===== Stage E: zoom back out =========================================
  console.log("[gif] E flyTo wide");
  await page.evaluate((c) => {
    window.__ghostWattsMap.flyTo({
      center: [c.lng, c.lat], zoom: c.zoom, duration: 1500, essential: true,
    });
  }, WIDE);
  await page.waitForTimeout(1800);

  console.log("[gif] capture complete");
  await page.close();
  await ctx.close();
  await browser.close();

  // ===== Convert to GIF =================================================
  const files = readdirSync(VIDEO_DIR).filter((f) => f.endsWith(".webm"));
  if (!files.length) throw new Error("no video recorded");
  const webm = path.join(VIDEO_DIR, files[0]);
  console.log(`[gif] webm: ${webm} (${statSync(webm).size} bytes)`);

  const PALETTE = path.join(VIDEO_DIR, "palette.png");
  // Trim the pre-storyboard settle. We start the timeline at the wide
  // overview jump, which fires after the waitForFunction + settleMap.
  // Empirically this is around t=4.5s into the recording.
  const SS = "4.0";
  const T = "10.5";

  console.log("[gif] ffmpeg palette pass");
  execSync(
    `ffmpeg -y -ss ${SS} -t ${T} -i ${webm} -vf "fps=8,scale=900:-1:flags=lanczos,palettegen=max_colors=80" ${PALETTE}`,
    { stdio: "inherit" },
  );
  console.log("[gif] ffmpeg apply pass");
  execSync(
    `ffmpeg -y -ss ${SS} -t ${T} -i ${webm} -i ${PALETTE} -filter_complex "fps=8,scale=900:-1:flags=lanczos[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=5" ${OUT_GIF}`,
    { stdio: "inherit" },
  );

  console.log(`[gif] wrote ${OUT_GIF} (${statSync(OUT_GIF).size} bytes)`);
}

main().catch((e) => {
  console.error("[gif] failed:", e);
  process.exit(1);
});
