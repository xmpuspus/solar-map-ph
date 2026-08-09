import { chromium } from "playwright";
const b = await chromium.launch();
// Start in LIGHT system preference so the [data-theme="dark"] block, not the
// media query, is what produces dark. That block was hand-duplicated and no
// colorScheme screenshot can exercise it.
const ctx = await b.newContext({ colorScheme: "light", viewport: { width: 1440, height: 900 } });
const p = await ctx.newPage();
const errs = [];
p.on("pageerror", (e) => errs.push("PAGEERROR: " + e.message));

for (const path of ["/", "/map", "/methodology"]) {
  await p.goto("http://localhost:4322" + path, { waitUntil: "networkidle", timeout: 60000 });
  await p.waitForTimeout(path === "/map" ? 4500 : 2500);
  for (const expect of ["light", "dark", "auto"]) {
    await p.click("[data-theme-toggle]");
    await p.waitForTimeout(path === "/map" ? 2200 : 1400);
    const state = await p.evaluate(() => {
      const cs = getComputedStyle(document.documentElement);
      const body = getComputedStyle(document.body);
      return {
        attr: document.documentElement.getAttribute("data-theme"),
        label: document.querySelector("[data-theme-label]")?.textContent,
        stored: localStorage.getItem("solarmap-theme"),
        paper: cs.getPropertyValue("--paper").trim(),
        bright: cs.getPropertyValue("--basemap-brightness-max").trim(),
        bodyBg: body.backgroundColor,
      };
    });
    const ok = state.label === expect;
    console.log(`${path.padEnd(13)} -> ${expect.padEnd(5)} ${ok ? "OK " : "MISMATCH"} attr=${state.attr} stored=${state.stored} paper=${state.paper} basemap=${state.bright} bodyBg=${state.bodyBg}`);
    if (expect === "dark") {
      const slug = path === "/" ? "home" : path.slice(1);
      await p.screenshot({ path: `../docs/screenshots/qa-2026-08/toggle-${slug}-dark.png` });
    }
  }
}
console.log("errors:", errs.slice(0, 5));
await b.close();
