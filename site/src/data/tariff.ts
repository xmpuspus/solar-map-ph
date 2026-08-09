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
};
