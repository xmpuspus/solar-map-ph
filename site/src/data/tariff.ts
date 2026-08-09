// Dated inputs to the payback math, read at build from the committed JSON the
// site also serves publicly. Same pattern as stats.ts: the number and the month
// it was read travel together, so prose can never claim "current" about a value
// nobody has refreshed. Update public/data/tariff.json, not this file.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

type RateBlock = {
  php_per_kwh: number;
  as_of: string;
  utility: string;
  basis: string;
  previous_month_php_per_kwh: number;
  source_url: string;
  source_note: string;
};

type CostBlock = {
  php_per_kwp: number;
  php_per_kwp_low: number;
  php_per_kwp_high: number;
  as_of: string;
  basis: string;
  source_url: string;
  source_note: string;
};

type YieldBlock = {
  kwh_per_kwp_per_year: number;
  as_of: string;
  basis: string;
  source_url: string;
  source_note: string;
};

type NetMeteringBlock = {
  residential_cap_kw: number;
  du_decision_working_days: number;
  lgu_electrical_permit_working_days: number;
  lgu_cfei_working_days: number;
  deemed_approved_on_silence: boolean;
  as_of: string;
  source_url: string;
  source_note: string;
};

const path = fileURLToPath(new URL("../../public/data/tariff.json", import.meta.url));
const raw = JSON.parse(readFileSync(path, "utf-8"));

// This file gets hand-edited every month when Meralco posts a new advisory, and
// a typo in it reaches a public payback calculator. A quoted number or a missing
// key would satisfy `astro check` and then render "PHP NaN" and "NaN years" to a
// homeowner. So the build fails loudly here instead.
function num(block: string, key: string, min: number, max: number): number {
  const v = raw?.[block]?.[key];
  if (typeof v !== "number" || !Number.isFinite(v)) {
    throw new Error(
      `tariff.json: ${block}.${key} must be a finite number, got ${JSON.stringify(v)}`,
    );
  }
  if (v < min || v > max) {
    throw new Error(
      `tariff.json: ${block}.${key} is ${v}, outside the sane range ${min} to ${max}. ` +
        `Widen the range here if the market really moved.`,
    );
  }
  return v;
}

function month(block: string): string {
  const v = raw?.[block]?.as_of;
  if (typeof v !== "string" || !/^\d{4}-(0[1-9]|1[0-2])$/.test(v)) {
    throw new Error(`tariff.json: ${block}.as_of must look like "2026-07", got ${JSON.stringify(v)}`);
  }
  return v;
}

function url(block: string): string {
  const v = raw?.[block]?.source_url;
  if (typeof v !== "string" || !v.startsWith("https://")) {
    throw new Error(`tariff.json: ${block}.source_url must be an https URL, got ${JSON.stringify(v)}`);
  }
  return v;
}

// Ranges are wide enough to survive real market moves and narrow enough to catch
// a decimal slip or a units mix-up.
num("electricity_rate", "php_per_kwh", 5, 40);
num("electricity_rate", "previous_month_php_per_kwh", 5, 40);
num("install_cost", "php_per_kwp", 20_000, 200_000);
num("install_cost", "php_per_kwp_low", 20_000, 200_000);
num("install_cost", "php_per_kwp_high", 20_000, 200_000);
num("yield", "kwh_per_kwp_per_year", 800, 2_000);
num("net_metering", "residential_cap_kw", 1, 10_000);
num("net_metering", "du_decision_working_days", 1, 90);
num("net_metering", "lgu_electrical_permit_working_days", 1, 90);
num("net_metering", "lgu_cfei_working_days", 1, 90);
for (const b of ["electricity_rate", "install_cost", "yield", "net_metering"]) {
  month(b);
  url(b);
}
// The roof tool calls the point estimate "mid-range for a low-to-high market",
// so the point has to sit inside the band it claims to sit inside.
{
  const { php_per_kwp: mid, php_per_kwp_low: lo, php_per_kwp_high: hi } = raw.install_cost;
  if (lo > hi) {
    throw new Error(`tariff.json: install_cost low ${lo} is above high ${hi}`);
  }
  if (mid < lo || mid > hi) {
    throw new Error(
      `tariff.json: install_cost php_per_kwp is ${mid}, outside its own ${lo} to ${hi} band. ` +
        `The roof tool calls that figure mid-range, so it has to be inside the band.`,
    );
  }
}

export const electricityRate: RateBlock = raw.electricity_rate;
export const installCost: CostBlock = raw.install_cost;
export const pvYield: YieldBlock = raw.yield;
export const netMetering: NetMeteringBlock = raw.net_metering;
export const lastReviewed: string = raw._last_reviewed;

const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

/** "2026-07" to "July 2026". Falls back to the raw string on a bad input. */
export function monthLabel(asOf: string): string {
  const [y, m] = asOf.split("-");
  const name = MONTHS[Number(m) - 1];
  return name ? `${name} ${y}` : asOf;
}

/** The single object the client scripts read out of the page. */
export const clientTariff = {
  ratePhpPerKwh: electricityRate.php_per_kwh,
  rateAsOf: electricityRate.as_of,
  rateAsOfLabel: monthLabel(electricityRate.as_of),
  rateSourceUrl: electricityRate.source_url,
  installPhpPerKwp: installCost.php_per_kwp,
  installLow: installCost.php_per_kwp_low,
  installHigh: installCost.php_per_kwp_high,
  installAsOfLabel: monthLabel(installCost.as_of),
  yieldKwhPerKwpPerYear: pvYield.kwh_per_kwp_per_year,
  netMeteringCapKw: netMetering.residential_cap_kw,
  duDecisionWorkingDays: netMetering.du_decision_working_days,
  netMeteringAsOfLabel: monthLabel(netMetering.as_of),
};
