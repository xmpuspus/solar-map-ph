# Pre-brief outreach list

Send a brief, polite email or DM 48 hours before the public LinkedIn post. Goal: give friendly experts the chance to flag obvious errors, surface their own related work, and prepare to amplify on the public launch day. Do NOT send to anyone whose contact you don't already have or whose contact is publicly listed.

Voice: direct, technical, no fluff. Subject line plain. Attach the press one-pager (`docs/launch/press-one-pager.md`) or link to the unpublished repo (a private/draft GitHub link) if available.

---

## A. Academic and research

### 1. UPD CEEPRRE (Center of Excellence in Electric Power Research and Energy Resources Engineering)
- Department: UP Diliman, EEE department
- Why: PH-side academic authority on rooftop PV interconnection, hosting-capacity studies, and net-metering. Has published on inverter compliance and the 100 kW cap.
- Contact path: department website faculty list; route through Prof. or Dr. heading the renewable-energy track (look up current head before launch).
- Ask: review of methodology + spot-check of any specific detection they'd like to verify.

### 2. UPD School of Statistics / Data Science group
- Why: independent verification of the calibration methodology and the holdout split.
- Contact path: faculty webpage. Look for groups doing applied stats with public-policy datasets.
- Ask: stress-test on the precision/recall numbers; comment on whether the source-disjoint split is honest.

### 3. ICSC (Institute for Climate and Sustainable Cities)
- Why: published SPECTRUM (the closest sibling project, July 2025). Credit them as related work in the README; offer a methodology comparison.
- Contact path: `info@icsc.ngo` or via their solar-mapper page contact form.
- Ask: would they like to swap detection-comparison results on overlapping NCR cells? (Both projects covering the same area independently is a feature, not a conflict.)

## B. Government and regulator

### 4. DOE Renewable Energy Management Bureau (NREB)
- Why: the regulator overseeing Net Metering. Their statutory timelines are quoted in the safety page.
- Contact path: `re@doe.gov.ph` (public general inbox) or specific NREB officer if known.
- Ask: courtesy notification that an independent civic-tech dataset is being published; offer to compare overlap with their formal registry counts.

### 5. ERC (Energy Regulatory Commission)
- Why: rule-making body on the 100 kW cap and net-metering compensation.
- Contact path: complaints/inquiries inbox listed at https://www.erc.gov.ph
- Ask: courtesy notification; no specific request.
- Note: optional. Don't expect a response. The contact is a heads-up, not a permission slip.

## C. Civic-tech and open-data peers

### 6. Open Data Philippines initiatives
- Why: ecosystem peers; potential mutual amplification.
- Contact path: depends on the specific initiative (data.gov.ph community, OpenData PH Slack/Discord if active, Open Knowledge Foundation PH chapter if present).
- Ask: cross-post to community channels; offer to add the dataset to any catalog they maintain.

### 7. Foundation for Economic Freedom / PSEMA (Philippine Solar Energy and Sustainability Alliance)
- Why: industry advocacy group cited in the safety page as a place homeowners can escalate stalled applications.
- Contact path: their website contact form. PSEMA: psema.org.ph (check current url before launch).
- Ask: courtesy notification; offer them the LGU-permit-friction roadmap for contributions.

## D. Journalists and media

### 8. Manila Times / Inquirer Opinion writers covering "guerrilla solar"
- Who: the columnists who wrote the 2026-05 "brewing solar controversy" and "guerrilla solar installers in summer of discontent" pieces.
- Contact path: their published bylines/email (most have a contact link on their author page).
- Ask: this dataset is a quantitative companion to their reporting; offer the one-pager and a 15-minute call.

### 9. Power Philippines newsroom
- Why: published the LGU-permit-friction comparison (`₱16K vs ₱153K` is from their reporting).
- Contact path: editorial inbox on powerphilippines.com.
- Ask: dataset is a quantitative companion to their LGU-friction reporting.

### 10. CleanTechnica PH stringer (if known)
- Why: published Meralco's "crackdown" framing.
- Contact path: byline contact.
- Ask: courtesy notification.

## Pre-brief template

> Subject: Heads-up: SolarMap.PH (rooftop solar detection across NCR) launching Tuesday
>
> Hi [Name],
>
> Quick courtesy heads-up. I'm publishing SolarMap.PH on Tuesday: an open-source computer-vision survey of rooftop solar across Greater Metro Manila, plus a free homeowner roof-lookup tool. Headline: 515 detections across 41 cities, 87% not on any prior public map, 69.9 MWp identified at sub-building resolution. F1 0.87 on an honest 20% holdout. MIT code, CC-BY-4.0 data.
>
> Attaching a one-page methodology summary. If you'd like to spot-check a specific city or a specific OSM building before launch, I can pull the imagery and per-tile scores for you. Genuine criticism welcome: the dataset is calibrated but not infallible, and there's a known limitation with utility-scale ground-mount solar farms being mis-routed to nearby OSM building footprints.
>
> The repo will live at https://github.com/xmpuspus/solar-map-ph on Tuesday morning. Independent civic-tech, not affiliated with Meralco, DOE, ICSC, or any utility.
>
> Cheers,
> Xavier
>
> --
> Xavier Puspus
> DPO: solarmap.ph@gmail.com

## Discipline notes

- Send pre-briefs Sunday/Monday evening for a Tuesday morning public launch.
- DO NOT pre-brief regulators with a request; courtesy only. The dataset is public, not seeking permission.
- DO NOT pre-brief anyone with a takedown-able image of a specific building. Send only the aggregated headline numbers + methodology one-pager.
- DO NOT promise embargoed access; the launch is public.
- DO accept introductions to specific subject-matter experts they recommend.
