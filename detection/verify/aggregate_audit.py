"""Aggregate r2->r3 delta audit results and decide rollback."""
import json, os, sys
from pathlib import Path

VERIFY = Path(__file__).parent
RESULTS = VERIFY / "audit_results"
BATCHES = VERIFY / "audit_batches"

def load_batch_inputs():
    inputs = {}
    for fn in sorted(BATCHES.iterdir()):
        if fn.suffix == ".json":
            with open(fn) as f:
                inputs[fn.stem] = json.load(f)
    return inputs

def load_results():
    out = {}
    for fn in sorted(RESULTS.iterdir()):
        if fn.suffix == ".json":
            with open(fn) as f:
                out[fn.stem] = json.load(f)
    return out

def main():
    inputs = load_batch_inputs()
    results = load_results()

    print(f"Batches: {sorted(inputs)}")
    print(f"Results: {sorted(results)}")

    # Group: newcomers, dropouts, kept_sample
    groups = {"newcomers": [], "dropouts": [], "kept_sample": []}
    for name, items in results.items():
        if name.startswith("newcomers"):
            groups["newcomers"].extend(items)
        elif name.startswith("dropouts"):
            groups["dropouts"].extend(items)
        elif name.startswith("kept"):
            groups["kept_sample"].extend(items)

    # Sanity check: counts match input
    for prefix, items in groups.items():
        if prefix == "newcomers":
            expected = sum(len(v) for k, v in inputs.items() if k.startswith("newcomers"))
        elif prefix == "dropouts":
            expected = sum(len(v) for k, v in inputs.items() if k.startswith("dropouts"))
        else:
            expected = len(inputs.get("kept_sample", []))
        ok = len(items) == expected
        print(f"  {prefix}: {len(items)}/{expected}  {'OK' if ok else 'MISMATCH'}")
        if not ok:
            seen = {x["tile_id"] for x in items}
            inp = []
            if prefix == "newcomers":
                inp = sum((v for k, v in inputs.items() if k.startswith("newcomers")), [])
            elif prefix == "dropouts":
                inp = sum((v for k, v in inputs.items() if k.startswith("dropouts")), [])
            else:
                inp = inputs.get("kept_sample", [])
            missing = [t for t in inp if t not in seen]
            print(f"    missing: {missing[:5]}{'...' if len(missing) > 5 else ''}")

    # Compute FP rate on newcomers
    nc = groups["newcomers"]
    label_counts = {}
    for x in nc:
        label_counts[x["label"]] = label_counts.get(x["label"], 0) + 1
    print()
    print(f"Newcomer label counts: {label_counts}")
    fp = label_counts.get("not-solar", 0)
    total = len(nc)
    fp_rate = (fp / total) * 100 if total else 0
    print(f"FP rate (not-solar/total): {fp}/{total} = {fp_rate:.2f}%")

    # Dropout: count clear solar that we missed
    dr = groups["dropouts"]
    drop_counts = {}
    for x in dr:
        drop_counts[x["label"]] = drop_counts.get(x["label"], 0) + 1
    print(f"Dropout label counts: {drop_counts}")
    missed_solar = drop_counts.get("solar", 0)
    print(f"Solar missed by r3 (dropouts labeled solar): {missed_solar}")

    # Kept sample sanity
    kp = groups["kept_sample"]
    kept_counts = {}
    for x in kp:
        kept_counts[x["label"]] = kept_counts.get(x["label"], 0) + 1
    print(f"Kept-sample label counts: {kept_counts}")

    # Decision
    decision = "keep_r3" if fp_rate < 5.0 else "rollback_r2"
    print()
    print(f"Decision: {decision} (threshold 5.0%, observed {fp_rate:.2f}%)")

    # Write audit JSON
    out_path = VERIFY / "r2_r3_delta_audit.json"
    audit = {
        "newcomers": nc,
        "dropouts": dr,
        "kept_sample": kp,
        "summary": {
            "newcomer_total": total,
            "newcomer_label_counts": label_counts,
            "newcomer_fp_rate_pct": round(fp_rate, 2),
            "dropout_total": len(dr),
            "dropout_label_counts": drop_counts,
            "dropout_missed_solar": missed_solar,
            "kept_sample_total": len(kp),
            "kept_sample_label_counts": kept_counts,
            "decision": decision,
            "threshold_pct": 5.0,
        },
    }
    with open(out_path, "w") as f:
        json.dump(audit, f, indent=2)
    print(f"Wrote {out_path}")

    return decision, fp_rate

if __name__ == "__main__":
    main()
