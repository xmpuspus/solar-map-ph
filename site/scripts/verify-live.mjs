// Post-deploy verification against the live alias. Every assertion is a claim
// this branch changed, so a stale cached deploy fails loudly instead of
// returning a green 200 with old content.
import { chromium } from "playwright";

const BASE = process.argv[2] ?? "https://solarmap.ph";
const results = [];
const check = (name, ok, detail = "") => {
  results.push({ name, ok, detail });
  console.log(`${ok ? "[PASS]" : "[FAIL]"} ${name}${detail ? "  " + detail : ""}`);
};

const b = await chromium.launch();

// 1. Homepage content, light mode, desktop.
{
  const ctx = await b.newContext({ colorScheme: "light", viewport: { width: 1440, height: 900 } });
  const p = await ctx.newPage();
  const errs = [];
  p.on("pageerror", (e) => errs.push(e.message));
  const res = await p.goto(BASE + "/", { waitUntil: "networkidle", timeout: 60000 });
  check("homepage 200", res?.status() === 200, `status=${res?.status()}`);
  const body = await p.locator("body").innerText();
  check("rate 14.8261 in prose", body.includes("14.8261"));
  check("as-of July 2026", /July 2026 Meralco residential rate/.test(body));
  check("10-working-day decision", body.includes("10-working-day"));
  check("no stale 12.50", !body.includes("12.50"));
  check("deliverables strip", body.includes("satellite view") && body.includes("neighbors"));
  check("footer coverage updated", /Coverage: \d+ cities across Greater Metro Manila, plus \d+ regional/.test(body));
  check("no YYYY-QN placeholder", !body.includes("YYYY-QN"));
  check("survey vintage shown", /Survey vintage 2026Q2, generated 2026-05-08/.test(body));
  check("no em-dash or en-dash", !/[—–]/.test(body));
  check("no page errors", errs.length === 0, errs.slice(0, 2).join(" | "));
  await ctx.close();
}

// 2. Theme toggle drives the page and the browser chrome color.
{
  const ctx = await b.newContext({ colorScheme: "light", viewport: { width: 1440, height: 900 } });
  const p = await ctx.newPage();
  await p.goto(BASE + "/", { waitUntil: "networkidle", timeout: 60000 });
  const read = () => p.evaluate(() => {
    const tags = [...document.querySelectorAll('meta[name="theme-color"]')];
    const eff = tags.filter((t) => !t.media || matchMedia(t.media).matches).pop();
    return {
      theme: document.documentElement.getAttribute("data-theme"),
      bg: getComputedStyle(document.body).backgroundColor,
      chrome: eff?.getAttribute("content"),
      label: document.querySelector("[data-theme-label]")?.textContent,
    };
  });
  await p.locator("nav [data-theme-toggle]").first().click();
  await p.waitForTimeout(400);
  let s = await read();
  check("toggle -> light", s.theme === "light" && s.chrome === "#fbfaf6", JSON.stringify(s));
  await p.locator("nav [data-theme-toggle]").first().click();
  await p.waitForTimeout(400);
  s = await read();
  check("toggle -> dark", s.theme === "dark" && s.bg === "rgb(16, 21, 28)" && s.chrome === "#10151c", JSON.stringify(s));
  await ctx.close();
}

// 3. Address field above the fold on a phone.
{
  const ctx = await b.newContext({ viewport: { width: 390, height: 844 } });
  const p = await ctx.newPage();
  await p.goto(BASE + "/", { waitUntil: "networkidle", timeout: 60000 });
  const top = await p.locator("#roof-address").evaluate((el) => el.getBoundingClientRect().top);
  check("address field above the fold at 390px", top > 0 && top < 844, `top=${Math.round(top)}`);
  await ctx.close();
}

// 4. Roof lookup end to end against the live third-party APIs.
{
  const ctx = await b.newContext({ colorScheme: "dark", viewport: { width: 1440, height: 1000 } });
  const p = await ctx.newPage();
  await p.goto(BASE + "/", { waitUntil: "networkidle", timeout: 60000 });
  await p.click('[data-fill="SM Megamall, Mandaluyong"]');
  await p.click("#roof-submit");
  await p.waitForSelector("#roof-results:not(.hidden)", { timeout: 120000 });
  await p.waitForTimeout(3000);
  const t = await p.locator("#roof-results").innerText();
  // The application-packet panel sits in a collapsed <details>, and innerText
  // skips collapsed subtrees. textContent sees it.
  const raw = await p.locator("#roof-results").textContent();
  check("results price at 14.83", /at ₱14\.83\/kWh/.test(t));
  check("results cite July 2026 + range", /July 2026 Meralco residential rate of ₱14\.8261\/kWh/.test(t) && /₱55,000 to ₱75,000 market/.test(t));
  check("packet says 10 working days", /10 working days/.test(raw ?? ""));
  check("payback is a real number", /\d+\.\d/.test(/payback\s*\n\s*([\d.]+)/i.exec(t)?.[1] ?? ""), (/payback\s*\n\s*([\d.]+)/i.exec(t) ?? [])[1]);
  check("no NaN in results", !/NaN/.test(t));
  await p.screenshot({ path: "../docs/screenshots/qa-2026-08/live-results-dark.png", fullPage: false });
  await ctx.close();
}

// 5. Map page: scoping, vintage, and a dimmed basemap in dark mode.
{
  const ctx = await b.newContext({ colorScheme: "dark", viewport: { width: 1440, height: 900 } });
  const p = await ctx.newPage();
  const res = await p.goto(BASE + "/map", { waitUntil: "networkidle", timeout: 60000 });
  check("map 200", res?.status() === 200, `status=${res?.status()}`);
  await p.waitForTimeout(6000);
  const body = await p.locator("body").innerText();
  check("precision scoped to NCR holdout", body.includes("96% precision on the NCR holdout"));
  check("map survey vintage", /survey 2026Q2, generated 2026-05-08/.test(body));
  const brightness = await p.evaluate(() =>
    getComputedStyle(document.documentElement).getPropertyValue("--basemap-brightness-max").trim(),
  );
  check("dark basemap token applied", Math.abs(parseFloat(brightness) - 0.62) < 1e-6, `--basemap-brightness-max=${brightness}`);
  check("map canvas rendered", (await p.locator("#map canvas").count()) > 0);
  await p.screenshot({ path: "../docs/screenshots/qa-2026-08/live-map-dark.png" });
  await ctx.close();
}

// 6. Safety page deadline and the public tariff file.
{
  const ctx = await b.newContext({ viewport: { width: 1440, height: 900 } });
  const p = await ctx.newPage();
  await p.goto(BASE + "/safety", { waitUntil: "networkidle", timeout: 60000 });
  const body = await p.locator("body").innerText();
  check("safety says 10 working days", /10 working days\./.test(body));
  check("safety names the April 2026 cut", /April 2026 DOE circular cut the window/.test(body));
  const r = await p.request.get(BASE + "/data/tariff.json");
  const j = await r.json();
  check("public tariff.json serves 14.8261", j.electricity_rate?.php_per_kwh === 14.8261, `as_of=${j.electricity_rate?.as_of}`);
  await ctx.close();
}

await b.close();
const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
if (failed.length) {
  console.log("FAILED:", failed.map((f) => f.name).join(", "));
  process.exit(1);
}
