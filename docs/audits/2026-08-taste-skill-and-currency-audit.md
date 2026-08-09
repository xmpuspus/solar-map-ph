# The roof tool priced electricity at 12.50 while Meralco charged 14.83, and the homepage breaks 6 taste-skill rules

Audited on 2026-08-09. The last commit before this pass was `446c098`, dated 2026-06-08.
Auditor pass over `site/` against [tasteskill.dev](https://tasteskill.dev)
(`Leonxlnx/taste-skill`, MIT) plus a currency check of every dated claim.

---

## The roof tool prices electricity at 12.50 when Meralco charges 14.83

`site/src/components/RoofLookup.astro:117` and
`site/src/components/HomeownerForm.astro:62` both held this line.

```js
const MERALCO_RATE_PHP_PER_KWH = 12.5;
```

Meralco's rate for a typical residential household was **P14.8261 per kWh in
July 2026**, up from P14.4833 in June ([GMA News, 2026-07-10](https://www.gmanetwork.com/news/money/companies/994402/meralco-electricity-rate-hike-july-2026/story/),
corroborated by [Manila Times, 2026-07-11](https://www.manilatimes.net/2026/07/11/news/national/meralco-electricity-rates-increase-in-july/2382508)).
The August advisory was not public on the audit date. Meralco posts it near the
10th of the month.

The constant shipped on 2026-05-13 and matched the Q2 2026 rate at the time.
It is 3 months old on the audit date and now 15.7% low. Annual savings scale
with the rate, so the tool
reports a payback that is roughly 19% longer than the current tariff supports. A
system that pays back in 6.0 years at 14.83 shows as 7.1 years at 12.50. The
tool tells homeowners solar is worse than it is, and the number carries no date,
so a reader cannot tell it is stale.

`site/src/pages/me.astro:10` repeats the stale figure in prose, calling 12.50
"the current Meralco residential rate". The word "current" is the defect.

**Fix shipped.** Both constants move to `site/public/data/tariff.json`, which
carries an `as_of` date and a source URL per value. `site/src/data/tariff.ts`
reads it at build, the same pattern `site/src/data/stats.ts` already uses for
survey counts. The rate and its as-of month now show next to every peso
figure the tool produces.

## Install cost of 65,000 per kWp is inside the 2026 market range but carries no date

`INSTALL_COST_PHP_PER_KWP = 65000` appears in the same two files. 2026 installer
guides put fully-installed grid-tied residential systems at P55,000 to P75,000
per kWp, with a 5 kWp system landing at P275,000 to P375,000
([SolarWise PH](https://solarwise.ph/solar-panel-price-philippines-2026-2/),
[pinas.solar](https://www.pinas.solar/solar-guides/solar-panel-price-philippines/)).
65,000 sits mid-range, so the number is defensible. It was undated and
unsourced, which is the same defect class as the tariff.

Lower bands circulate. Some 2026 guides say P40,000 to P60,000 per kWp, and
quoted installer prices run P33,000 to P38,000. Those quote panels and an
inverter, or a promotional package, and not a fully installed grid-tied system
with mounting, wiring, breakers, grounding, monitoring, labor and testing.
Install cost is the numerator of payback, so this pass takes the higher all-in
band, which reports the longer payback. `tariff.json` records that choice in
`band_choice_note`.

**Fix shipped.** The point estimate and the range both move into `tariff.json`
with their source and date. The tool shows not just the point but the range.

## The residential 100 kW net-metering cap is still correct, so the copy stays

The April 2026 DOE circular cut the distribution-utility decision window to 10
working days, effective 2026-04-01, and the application counts as approved on
silence ([SolarQuarter, 2026-04-01](https://solarquarter.com/2026/04/01/philippines-doe-mandates-10-day-net-metering-approvals-under-energy-emergency-to-accelerate-rooftop-solar-adoption-and-reduce-power-costs/),
[Philstar, 2026-04-05](https://www.philstar.com/business/2026/04/05/2518672/doe-speeds-net-metering-process)).
The same circular gives LGUs 3 working days for the "electrical permit" and 7
for the Certificate of Final Electrical Inspection.
`pipeline/lgu_friction.json` already records all of this with sources, and the
site copy matches.

Vendor guides report that the same circular lifted the **non-residential** cap
from 100 kW to 1 MW. Two vendor blogs say so. No primary DOE text or mainstream
outlet confirms it. **This claim does not go into public copy.** The residential
cap of 100 kW is unchanged, and the roof tool is residential, so the wording
stays. The figure itself moved into `tariff.json` and is interpolated in
`RoofLookup.astro`, `index.astro` and `safety.astro`, so a future change to the
cap edits one file and not five strings.

Open item for a later pass. Get the circular number and text from
`doe.gov.ph` and, if the 1 MW figure holds, add a one-line non-residential note
to `/safety`.

## Four other dated claims drifted from the data behind them

| Where | Ships now | Problem |
|---|---|---|
| `Footer.astro` | `Current coverage: Greater Metro Manila` | v1.1 added 7 regions outside Metro Manila |
| `Footer.astro` | `Cite as: SolarMap.PH (YYYY-QN)` | Literal placeholder in shipped copy |
| `index.astro:55` | `Calibrated to 96% precision on a held-out validation set` | True for the NCR holdout only. The 7 cross-domain regions carry no precision claim, and 4 of them ship as candidate inventory |
| `map.astro` header | `LAST CALIBRATED 2026-05-10` | Correct and dated. Keep it. It is the pattern the rest of the site needs |

## The design read, the dials, and the mode

The taste-skill wants three declarations before any code. Here they are.

**Design read, skill 0.B.** Reading this as a public-record civic measurement
tool for Filipino homeowners, plus a research map for reporters and policy
readers, with a trust-first data-journalism language, leaning toward the
existing Astro and Tailwind editorial system, evolved and not replaced.

**Dials (skill 1.A).** The brief matches the "trust-first / public-sector /
accessibility-critical" row and the "redesign, preserve" row. Both push the
dials down.

| Dial | Value | Why |
|---|---|---|
| `DESIGN_VARIANCE` | 4 | The existing site reads as 3. Preserve mode says match, then add one |
| `MOTION_INTENSITY` | 3 | Trust-first row caps at 3. A payback calculator does not need choreography |
| `VISUAL_DENSITY` | 5 | Public-sector row is 4 to 5. The map page is genuinely dense |

The baseline the skill ships is 8 / 6 / 4. This project gets 4 / 3 / 5. That is
not a preference but the skill's own arithmetic. It rules out the whole GSAP
layer. No sticky-stack, no horizontal scroll-hijack, no marquee, no magnetic
hover, no mesh gradients.

**Mode, skill 11.A.** Redesign, preserve. Slugs, nav labels, form field names
and anchor IDs do not change (skill 11.F). SEO and analytics continuity outrank
a cleaner information architecture here.

## Six taste-skill rules the site broke, all on pages the skill actually covers

Skill Section 13 puts dashboards, data tables and multi-step product UI out of
scope. That excludes `RoofLookup.astro` (1,475 lines, a multi-step form with a
data readout) and `MapView.astro` (1,138 lines, dense data UI) from the
aesthetic rules. Those two files get only the accessibility rules and the
interactive-state rules, which the skill applies everywhere.

In scope, these files. `index.astro`, `regions.astro`, `faq.astro`, `safety.astro`,
`methodology.astro`, `Header`, `Footer`, `Base`, and the Tailwind tokens.

**1. Eyebrow count is 78 against a budget of about 12.** Skill 9.F calls the
uppercase-tracking micro-label above every heading the single most-violated
rule, and it makes the check mechanical. At most `ceil(sections / 3)`.
`index.astro` alone carries 5 across 4 sections. Counted with
`grep -rc "uppercase tracking" site/src`.

**2. The hero carries 5 text elements, and the skill allows 4.** Eyebrow,
headline, a 25-word lead, a 52-word privacy paragraph, and a 5-item aside list.
Skill 4.7 caps subtext at 20 words and 4 lines.

**3. The address field sits below the fold on a 390 px phone.** The hero text
runs 500 px before the input. The primary action of the whole site is invisible
on first paint on the most common screen. Skill 4.7 wants the CTA visible
without a scroll.

**4. An em-dash ships in the bill-input helper text.** The string reads
`Your average monthly bill [em-dash] edit it so the payback is yours`, with the
em-dash character in place of the bracketed word. Skill 9.G bans it with no allowance, and `CLAUDE.md` in this repo
bans it too. The address placeholder uses `--`, which reads as an em-dash that
did not convert.

**5. The site has no dark mode.** Skill 6.C makes dual-mode mandatory for any
consumer-facing page. Screenshots under `prefers-color-scheme: dark` are the
same pixels as light, because `global.css` pins `color-scheme: light`.

**6. The hero and the form do not share a left edge.** The hero text starts at
x=232 and the form block starts at x=408 on a 1440 px viewport. Two different
container widths stacked without a shared grid.

## Four taste-skill rules lose on a measurement tool, so this pass refuses them

The skill targets landing pages and portfolios. All of it applied to a
measurement tool would cost credibility. This pass refuses four rules on purpose.

**Font swap to Geist or Satoshi (skill 4.1, and the redesign skill's first fix).**
Refused. The CSP header is `font-src 'self'`, so a CDN font is blocked, and the
skill's own 4.1 override lets you keep Inter for accessibility-first and
public-sector briefs. This is exactly that brief. Inter and JetBrains Mono stay,
self-hosted through `@fontsource-variable`.

**Stock photography and "pure-text minimalism is incomplete work" (skill 4.8).**
Refused. Decorative `picsum.photos` imagery on a public-record measurement tool
trades credibility for texture. Every image URL needs a CSP `img-src` entry
that the privacy page then has to show. The satellite tile of the reader's own
roof is the image this product has, and it is real.

**React, Next.js, Motion, Tailwind v4 (skill 3.A).** Refused. This is Astro 5
with Tailwind 3.4, and the redesign skill's own Rules forbid migrating the
stack. Motion on a static site is a bundle regression on a page whose LCP is the
product. Transitions use CSS, and reveal uses IntersectionObserver.

**A dark basemap provider for the map (implied by skill 6.C).** Refused.
A dark tile provider adds a third-party domain to the CSP and to the privacy
page. The map darkens instead through MapLibre `raster-brightness-max` and
`raster-saturation` paint properties, which need no new domain.

## Seven changes shipped, ordered by visual lift per unit of risk

The redesign skill orders fixes by visual lift per unit of risk. This pass
follows that order. The currency fix goes first because it is a correctness
defect and not a design one.

1. Dated tariff and install cost, read at build, with the as-of month visible
2. Stale coverage and citation strings in the footer, and the precision scope on the homepage
3. Dark mode across the site chrome, content pages, map legend and basemap
4. Eyebrow cull from 78 to inside budget on the in-scope pages
5. Hero rebuilt to 4 text elements, a shared left edge, and the address field above the fold
6. Em-dash removal and copy self-audit across every visible string
7. Focus rings, pressed states, and reduced-motion gating

## The survey data still dates from the May 2026 scan

The survey data itself does not change. Detections still date from the May 2026
scan, and this pass shows that date rather than re-running the pipeline. A
reader now sees when the survey ran, but the map still shows May. A re-scan is a
pipeline job with an Esri throttle budget attached. Folding it into a UI pass
hides a multi-day job inside a one-day change. This section exists because the
next correct step for "up to date" is a fresh scan, and nothing in this pass
substitutes for it.
