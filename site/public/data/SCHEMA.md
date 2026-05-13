# SolarMap.PH data product schema

Every file in `site/public/data/` is published under CC-BY-4.0. Cite as:

> SolarMap.PH (YYYY-QN), https://github.com/xmpuspus/solar-map-ph

All geometry is in EPSG:4326 (WGS84). All distances are meters unless noted.

## Files

| File | Granularity | Used by |
|---|---|---|
| `per_building_solar_ncr.geojson` | Per OSM building (commercial/industrial/public only) | `/map`, `/safety`, `/` roof lookup |
| `residential_solar_aggregate.json` | Counts only, no geometry | `/safety` |
| `rooftop_solar_ncr.geojson` | Per 240m tile center | `/map` |
| `city_solar_saturation.json` | Per 240m cell, summed across NCR | `/safety` saturation index |
| `solar_map_ph_YYYYQN.geojson` | Per city | `/map` choropleth |
| `solar_map_ph_barangay_YYYYQN.geojson` | Per barangay, urban-area drilldown | `/map` |
| `solar_map_ph_summary_YYYYQN.json` | Franchise-wide totals | `/methodology` |
| `manifest.json` | Index of available quarters | site bootstrap |

## per_building_solar_ncr.geojson

One Feature per OSM building with detected rooftop solar. Residential roofs are intentionally suppressed; see `residential_solar_aggregate.json` for counts.

```jsonc
{
  "type": "Feature",
  "geometry": { "type": "Polygon", "coordinates": [[[lon, lat], ...]] },
  "properties": {
    "building_osm_id": 604560854,        // OSM way or relation id
    "building_osm_type": "way",          // "way" or "relation"
    "building_area_m2": 1834.2,          // m^2, area of the OSM building footprint
    "building_type": "commercial",        // OSM `building=*` value, or `amenity` fallback
    "is_residential": false,             // always false in the published file
    "is_commercial": true,
    "panel_area_m2": 412.7,              // m^2, summed across SAM segments, capped at footprint
    "kwp_estimate": 68.78,               // panel_area_m2 / 6.0 (CSi rule-of-thumb)
    "confidence": 0.9183,                // max calibrated segment score
    "n_segments_merged": 4,              // SAM segments merged onto this building
    "tile_ids": ["14.59345_121.10221", ...],
    "tile_id": "14.59345_121.10221",     // primary (highest-confidence) tile
    "tile_score": 0.9871                 // CLIP+LR tile-level score for the primary tile
  }
}
```

`_meta` on the FeatureCollection root reports `generated_utc`, `tiles_processed`, `buildings_with_solar_published`, `buildings_residential_suppressed`, `kwp_per_m2`, `scoring`, `polygon_strategy`, `area_strategy`, `privacy_policy`, and `tiles_overpass_failed`.

### Caveats

- `kwp_estimate` uses the 2015-era 6 m^2 per kWp rule of thumb (~167 W/m^2). Modern PH commercial installs run 5-7 m^2 per kWp. Use a 0.85-1.20 sensitivity band when downstream of this number.
- `panel_area_m2` is capped at the OSM building footprint area as a sanity gate against SAM over-segmenting nearby ground.
- For solar arrays spanning multiple buildings, `kwp_estimate` is a lower bound: each SAM segment is attributed to a single OSM building.

## residential_solar_aggregate.json

```jsonc
{
  "generated_utc": "2026-05-12T17:55:00Z",
  "n_residential_buildings_with_solar": 27,
  "kwp_residential_total": 917.18,
  "by_building_type": {
    "apartments": 4,
    "house": 21,
    "residential": 2
  },
  "policy": "Residential rooftops are intentionally not published as individual polygons..."
}
```

No geometry, no addresses, no per-building entries. This is the only residential-scoped figure SolarMap.PH releases.

## rooftop_solar_ncr.geojson

One Point feature per 240m tile center that scored above the candidate threshold.

```jsonc
{
  "type": "Feature",
  "geometry": { "type": "Point", "coordinates": [lon, lat] },
  "properties": {
    "tile_id": "14.59345_121.10221",
    "score": 0.9871,             // calibrated probability of containing rooftop solar
    "tier": "high",              // "high" (>=0.85) or "candidate" (0.70-0.85)
    "anchored_to_building": true,
    "osm_status": "confirmed",   // "confirmed" if within 50 m of an OSM solar tag
    "kwp_estimate": 68.78        // copied from per_building when anchored
  }
}
```

## city_solar_saturation.json

One row per 240m cell across NCR with a count of high-confidence detections within a 300 m halo. Used by the saturation-tier card on `/safety` and inside the roof-lookup tool.

```jsonc
[
  {
    "cell_lat": 14.59345,
    "cell_lon": 121.10221,
    "n_high_within_300m": 5,
    "n_buildings_solar_within_300m": 4,
    "kwp_within_300m": 73.21,
    "saturation_tier": "growing"   // "early", "growing", "saturated"
  }
]
```

## solar_map_ph_YYYYQN.geojson (city-level composite)

Earth Engine multi-signal composite, one polygon per franchise city.

```jsonc
{
  "type": "Feature",
  "geometry": { "type": "Polygon", "coordinates": [...] },
  "properties": {
    "city": "Quezon City",
    "province": "Metro Manila",
    "psgc_code": "1380700000",
    "composite": 0.74,           // [0,1], higher = stronger multi-signal solar signature
    "nir_delta_z": 1.42,         // z-scored across cities
    "swir_delta_z": 0.93,
    "lst_anomaly_z": 0.41,
    "nightlight_delta_z": 0.08,
    "built_km2": 161.2,
    "quarter": "2026Q2",
    "baseline_year": 2022
  }
}
```

The composite is correlative, not diagnostic. See `/methodology` on the site for the full algorithm.

## License and citation

All files: CC-BY-4.0. Cite as `SolarMap.PH (YYYY-QN), https://github.com/xmpuspus/solar-map-ph`. Citing the software itself: see `CITATION.cff` at repo root.
