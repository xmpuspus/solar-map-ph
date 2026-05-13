# PH solar policy context (research notes, 2026-05-08)

Source material gathered during the SolarMap.PH design phase. Use as inputs for the inaugural post and the methodology page. Direct quotes are flagged with the source URL.

## The five-actor map

### 1. Meralco
- VP and head of utility economics: **Lawrence Fernandez**
- Asks (publicly stated): equipment certification, installer accreditation, anti-islanding compliance, "crackdown on guerrilla installations," ERC authority to redefine net-metering scope
- Quote: "Issue is not opposition to solar adoption but the manner in which it is integrated." (CleanTechnica, 2026-05-04)
- Real concerns:
  - Distribution-charge revenue erosion as customers self-generate
  - Net-metering at full retail rate creates cross-subsidy from non-solar to solar customers
  - Demand forecasting accuracy when up to 1/3 of installs are unmeasured
  - Worker safety from non-anti-islanding inverters during outages
- Public position aligns with Sen. Gatchalian's streamlining push (per Manila Times, 2026-05-07)

### 2. DOE + Sen. Sherwin Gatchalian
- Streamliners, not blockers
- April 2026 DOE circular:
  - 10 working day approval target for net metering
  - 3-day LGU electrical permit
  - 7-day Certificate of Final Electrical Inspection
  - Deemed-approved on LGU silence
- Gatchalian publicly backs Meralco's call for streamlining (notable: not blocking it)

### 3. Energy Regulatory Commission (ERC)
- 2018: opposed cap-raise above 100 kW (transmission concerns)
- 2019: opposed full-rate compensation for net-metering exports (cross-subsidy concern, "higher generation cost to other end-users")
- Sept 22, 2025: Advisory to all on-grid distribution utilities for uniform implementation of net metering
- Pattern: structurally cautious about anything that shifts costs onto non-solar captive customers

### 4. LGUs (the silent blocker)
- **₱153,000 vs ₱16,000** for the same 520 kWp project. Rizal vs Laguna. Same province, different LGU. (Power Philippines, citing developer comparisons)
- "Most municipalities do not have a standardized approach, so requirements vary widely and may change per project and per case officer."
- April 2026 DOE circular tries to fix this with deemed-approved on silence + 3-day deadline; adoption is uneven as of May 2026

### 5. Households / "guerrilla solar"
- ICSC: ~1/3 of rooftop solar in Meralco's franchise is unregistered
- ~20,000 registered installations totaling ~170 MW
- Additional ~370 MW in commercial outside formal program
- Total estimated ~500 MW solar capacity in franchise
- Formal install: ₱200,000-350,000 for residential, weeks-to-months
- Guerrilla install: cheaper, faster, illegal, no net-metering credits, real worker-safety risk if anti-islanding fails

## The economic core

PH residential electricity rates: highest in SEA, ~₱10-12/kWh typical, hit ₱8.39/kWh on generation charge alone in April 2026.

Net metering at full retail: when a solar exporter gets credited at full retail (~₱12.5/kWh as of Q2 2026), they're effectively getting paid for distribution + transmission + system loss + cross-subsidies they didn't deliver. Captive customers (non-solar) pay the difference.

This is the same fight in California (NEM 3.0), Arizona (Salt River Project), Australia. Utility resistance to full-retail compensation is rationally about avoiding cross-subsidy, even when public framing is "utility hates solar."

## The duck curve angle

Luzon WESM:
- Q1-Q2 2026: tight supply, ₱8.39/kWh generation charge in April
- Higher seasonal demand + plant outages + thin reserves
- Solar growth (registered + unregistered) shifts midday load profile
- Without aggregate visibility into rooftop solar, grid operators systematically over-forecast demand on sunny days

The Energy Storage Systems Act (HB 6676, passed early 2026) addresses storage but not the rooftop visibility gap directly.

## The 100 kW cap

- RA 9513 (Renewable Energy Act 2008) sets the 100 kW net-metering ceiling
- Above 100 kW: not eligible for credits
- Sen. Grace Poe pushed Senate Bill 1719 in 2018 to raise the cap; ERC opposed
- Cap is the binding constraint on commercial-rooftop economics for malls, factories, large warehouses
- For residential (typical 3-10 kWp) the cap is not binding; LGU permit friction is the binding constraint

## Satellite-signal precedent

- Stanford DeepSolar (Yu et al., 2018, Joule): 1.47M solar installs mapped in US, 93.1% precision residential, 88.5% recall, 93.7% precision non-residential. Public dataset.
- Method: CNN classifier on tile-level satellite imagery, trained on 366,467 weakly labeled images
- Resolution requirement: ~30cm-60cm (high-res aerial), works on Bing/Google Static Maps. Sentinel-2 at 10m is too coarse for individual residential.

For SolarMap.PH (no GPU, free-tier compute):
- Sentinel-2 at 10m: aggregate-only signal, neighborhood-scale, free, weekly
- Landsat 8/9 thermal: 30m, free, ~16-day cadence
- VIIRS DNB nightlights: 500m, free, monthly
- All available in Google Earth Engine free tier

## Political risk to flag

- Anything that publishes per-address data is dangerous: enforcement risk for households, PII risk, lawsuit risk
- Aggregate framing only is the safe path
- Comparison tables in /me must be descriptive, not prescriptive: never imply guerrilla install is recommended
- The cross-subsidy framing is technically accurate but politically loaded; stick to math, link to Meralco's 2019 ERC filing for primary source

## Style notes for the post

- Direct technical tone, no AI-fingerprint verbs ("delve", "land", "tuned to", "leverages", "seamlessly")
- No em-dashes; use commas, colons, periods, parentheses
- Cite every specific number
- "Consistent with," "aligns with," never "proves"
- Inline links to primary sources, not Wikipedia
- No HN/Reddit/X distribution, optional LinkedIn
