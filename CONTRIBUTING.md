# Contributing to ghost-watts

Thanks for considering a contribution. This repo welcomes:

1. **Verified false-positive reports** on detections in `site/public/data/per_building_solar_ncr.geojson` (open an issue with the building OSM id and a screenshot).
2. **LGU permit data** for any city or municipality where the published `pipeline/lgu_friction.json` has gaps or stale costs (open a PR with a source URL).
3. **Region extensions** that adapt the pipeline to a new Philippine geography outside the Meralco franchise (Cebu, Davao, Iloilo, Cagayan de Oro). See [examples/run_on_new_region.md](examples/run_on_new_region.md) for the recipe.
4. **Encoder swaps** that improve recall or reduce inference cost (open an issue first with the proposed encoder and a one-paragraph rationale).
5. **Code review and bug fixes** on anything in `detection/` or `pipeline/`.

## Dev setup

```bash
git clone https://github.com/xmpuspus/ghost-watts
cd ghost-watts
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install pytest matplotlib

# Verify the deterministic build before changing anything.
make train          # rebuilds clf_v4.joblib from cached dataset_v4.npz
make hash-verify    # asserts sha256 56900722a8427be4
pytest tests/ -q    # 11 tests, ~1 second
```

For the Astro site:

```bash
cd site
pnpm install
pnpm dev            # http://localhost:4321
pnpm typecheck      # must be clean before opening a PR
pnpm build          # production build, must succeed
```

## PR conventions

- Branch naming: `fix/<short-slug>`, `feat/<short-slug>`, `docs/<short-slug>`.
- One logical change per PR. Bundling unrelated fixes makes review slow and increases the chance of revert.
- Update `CHANGELOG.md` under the `Unreleased` heading with one line describing the change.
- If the change affects the classifier, calibration, or scan logic: re-run `make plots` and include the new figures.
- If the change touches the deterministic-build chain (requirements pinning, training script, dataset builder): re-run `make hash-verify` and update `EXPECTED_HASH` in the Makefile if the hash legitimately moves.

## Testing expectations

| Change type | Required tests |
|---|---|
| New helper function | Pure-function test in `tests/test_<module>.py` |
| Bug fix | Regression test that fails on the broken code and passes after the fix |
| Pipeline behavior change | Manual rerun against the cached imagery + diff against prior output |
| Site UI change | `pnpm typecheck` clean and `pnpm build` succeeds; describe browser checks in the PR body |

Never silence a failing test by editing the assertion. If the test was wrong, document why in the PR body.

## Code style

- Python: 3.11+, `ruff format`, `ruff check`. No `bare except:` outside of the documented urllib-retry shims.
- TypeScript: strict mode, Astro 5, no `any` in new code unless cast at a library boundary.
- Markdown: no em-dashes anywhere (use `--`, comma, or period). Match the existing tone in `README.md`.

## Reporting a security issue

Do not open a public issue. Use the [GitHub Security Advisory form](https://github.com/xmpuspus/ghost-watts/security/advisories/new). See [SECURITY.md](SECURITY.md) for what's in scope.

## Code of conduct

This project follows the [Contributor Covenant 2.1](CODE_OF_CONDUCT.md). Be kind, ask before assuming, no harassment.
