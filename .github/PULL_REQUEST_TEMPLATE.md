## What this PR does

<!-- One sentence per logical change. -->

## Why

<!-- The problem this fixes or the capability it adds. Link to issues with #N. -->

## How it works

<!-- Briefly describe the approach, especially anything non-obvious. -->

## Verification

<!-- Tick what applies. Add evidence for the boxes you ticked. -->

- [ ] `pnpm typecheck` clean (site changes only)
- [ ] `pnpm build` succeeds (site changes only)
- [ ] `make hash-verify` passes (classifier or training-chain changes)
- [ ] `make plots` regenerated (calibration or threshold changes)
- [ ] `pytest tests/ -q` passes
- [ ] `CHANGELOG.md` updated under "Unreleased"

## Privacy and trademarks

- [ ] No private residential addresses, names, or contact info in code or data.
- [ ] No Meralco or other utility brand used implying affiliation.

## Reviewer notes

<!-- Anything specific you want reviewed. "Look at the Overpass throttle change carefully." -->
