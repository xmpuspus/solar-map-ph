import { chromium } from "playwright";
const b = await chromium.launch();

async function run(label, width, height, openMenu) {
  const ctx = await b.newContext({ colorScheme: "dark", viewport: { width, height } });
  const p = await ctx.newPage();
  await p.goto("http://localhost:4322/", { waitUntil: "networkidle", timeout: 60000 });
  const sel = openMenu ? "details [data-theme-toggle]" : "nav.hidden [data-theme-toggle], nav [data-theme-toggle]";
  const read = () => p.evaluate(() => {
    const tags = [...document.querySelectorAll('meta[name="theme-color"]')];
    const eff = tags.filter((t) => !t.media || matchMedia(t.media).matches).pop();
    return { tags: tags.length, chrome: eff?.getAttribute("content"), theme: document.documentElement.getAttribute("data-theme") };
  });
  console.log(`[${label}] start (OS dark, auto):`, JSON.stringify(await read()));
  for (const expect of ["light", "dark", "auto"]) {
    if (openMenu && !(await p.locator("details").first().evaluate((d) => d.open))) {
      await p.locator("details > summary").click();
      await p.waitForTimeout(200);
    }
    await p.locator(sel).first().click();
    await p.waitForTimeout(400);
    const s = await read();
    const want = expect === "light" ? "#fbfaf6" : "#10151c";
    console.log(`[${label}] ${expect.padEnd(5)} -> ${s.chrome === want ? "OK " : "MISMATCH"} ${JSON.stringify(s)}`);
  }
  await ctx.close();
}

await run("desktop", 1440, 900, false);
await run("mobile ", 390, 844, true);
await b.close();
