// Probe the live /map page on solar-map-ph.vercel.app and capture
// network + console errors, plus a screenshot.
import { chromium } from "playwright";

const URL = process.env.PROBE_URL || "https://solar-map-ph.vercel.app/map";
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();

const consoleMsgs = [];
const networkResults = [];
const failures = [];

page.on("console", (msg) => {
  consoleMsgs.push({ type: msg.type(), text: msg.text() });
});
page.on("pageerror", (err) => failures.push(`pageerror: ${err.message}`));
page.on("response", async (resp) => {
  const url = resp.url();
  if (url.includes("/data/") || url.includes("geojson") || url.includes(".json")) {
    let contentType = resp.headers()["content-type"] || "";
    let bodyLen = 0;
    try {
      const buf = await resp.body();
      bodyLen = buf.length;
    } catch (e) {}
    networkResults.push({ status: resp.status(), url: url.replace("https://solar-map-ph.vercel.app", ""), contentType, bodyLen });
  }
});

try {
  await page.goto(URL, { waitUntil: "networkidle", timeout: 30000 });
} catch (e) {
  failures.push(`navigation: ${e.message}`);
}
await page.waitForTimeout(2000);

console.log("=== NETWORK (data/json requests) ===");
for (const r of networkResults) {
  console.log(`  ${r.status} ${r.url}  ct="${r.contentType}" body=${r.bodyLen}b`);
}

console.log("\n=== CONSOLE ERRORS ===");
for (const m of consoleMsgs) {
  if (m.type === "error" || m.type === "warning") console.log(`  [${m.type}] ${m.text}`);
}

console.log("\n=== PAGE ERRORS ===");
for (const f of failures) console.log(`  ${f}`);

console.log("\n=== MAP LAYERS ON THE PAGE (from window state) ===");
const layerInfo = await page.evaluate(() => {
  const m = (window).__solarMapPHMap;
  if (!m) return { error: "map not on window" };
  const layers = m.getStyle().layers.map((l) => l.id);
  const sources = Object.keys(m.getStyle().sources);
  const featureCounts = {};
  for (const s of sources) {
    try {
      const src = m.getSource(s);
      if (src && src._data && src._data.features) {
        featureCounts[s] = src._data.features.length;
      }
    } catch (e) {}
  }
  return { layers, sources, featureCounts };
});
console.log(JSON.stringify(layerInfo, null, 2));

await page.screenshot({ path: "/tmp/map-probe.png", fullPage: false });
console.log("\nscreenshot: /tmp/map-probe.png");

await browser.close();
