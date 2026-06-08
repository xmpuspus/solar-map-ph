// Build-time survey statistics, computed from the actual published data so the
// prose counts on the homepage and map page can never silently drift from the
// GeoJSON the tool serves. Runs in Node at build time (Astro frontmatter); the
// large GeoJSON is read here only to count features and is never shipped to the
// client.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

function readJson(rel: string): any {
  const path = fileURLToPath(new URL(`../../public/data/${rel}`, import.meta.url));
  return JSON.parse(readFileSync(path, "utf-8"));
}

const rooftopNcr = readJson("rooftop_solar_ncr.geojson");
const perBuilding = readJson("per_building_solar_ncr.geojson");
const cityCounts = readJson("city_detection_counts.json");

const features = rooftopNcr.features ?? [];
export const totalDetections: number = features.length;
export const highConfidence: number = features.filter(
  (f: any) => f.properties?.tier === "high",
).length;
export const candidates: number = totalDetections - highConfidence;
export const perBuildingPolygons: number = (perBuilding.features ?? []).length;

const meta = cityCounts._meta ?? {};
export const citiesWithDetections: number = meta.n_cities_with_detections ?? 0;
export const inPolygonHigh: number = meta.n_total_high ?? 0;
export const newHigh: number = meta.n_total_new_high ?? 0;
export const newHighPct: number = inPolygonHigh
  ? Math.round((newHigh / inPolygonHigh) * 100)
  : 0;
