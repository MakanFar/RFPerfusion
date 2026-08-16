"""Linear triage runner: FASTA + config -> one TSV with every tier's verdict.

Design contract
---------------
* One row per input sequence, ALWAYS. Rejected proteins are retained with
  their reject reason, never dropped -- a filter you cannot audit is a filter
  you cannot trust.
* Tiers run in order T0 -> T1 -> T2. A protein only enters tier N+1 if it
  passed tier N, so cost scales with survivors, not with input size.
* Every threshold comes from the config file. No magic numbers in code.

Usage
-----
    python -m biophys_triage.run --fasta in.faa --config config.yaml --out results.tsv
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import time
import pandas as pd

from . import tiers


def read_fasta(path):
    recs, sid, buf = [], None, []
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if line.startswith(">"):
                if sid is not None:
                    recs.append((sid, "".join(buf)))
                sid = line[1:].split()[0]
                buf = []
            elif line:
                buf.append(line)
    if sid is not None:
        recs.append((sid, "".join(buf)))
    return recs


def load_config(path):
    if path is None:
        return default_config()
    with open(path) as fh:
        if path.endswith((".yaml", ".yml")):
            import yaml
            return yaml.safe_load(fh)
        return json.load(fh)


def default_config():
    """Permissive defaults -- these keep ~everything and exist so a first run
    succeeds and shows you the feature distributions. Tighten from the report."""
    return {
        "target_temperature_c": 70.0,
        "target_ph": 7.0,
        "plddt_min": 70.0,
        "salt_bridge_cutoff_a": 4.0,
        "t0_filters": {
            "length": {"min": 50, "max": 2000},
            "instability_index": {"max": 60.0},
        },
        "t0_keep_top_fraction": 0.20,
        "t1_filters": {
            "mean_plddt": {"min": 70.0},
            "salt_bridges_per_100aa": {"min": 1.0},
        },
        "t2_filters": {},
    }


def run(fasta, config_path=None, out_tsv="triage_results.tsv",
        structures=None, report_md=None, verbose=True):
    cfg = load_config(config_path)
    t_start = time.time()
    records = read_fasta(fasta)
    log = lambda m: verbose and print(m, file=sys.stderr, flush=True)
    log(f"[triage] loaded {len(records)} sequences from {fasta}")

    # ---- T0 --------------------------------------------------------------
    t0 = tiers.t0_descriptors(records, cfg)
    t0 = tiers.t0_score(t0, cfg)
    t0 = tiers.apply_filters(t0, cfg.get("t0_filters"), "t0")
    if cfg.get("t0_keep_top_fraction"):
        t0 = tiers.top_fraction(t0, "t0_composite_z",
                                cfg["t0_keep_top_fraction"], "t0")
    n0 = int(t0["t0_pass"].sum())
    log(f"[triage] T0 sequence filters: {n0}/{len(t0)} pass")

    master = t0.copy()

    # ---- T1 --------------------------------------------------------------
    # Structures are supplied by the caller (ESMFold2/Boltz upstream); the
    # runner never folds anything itself.
    smap = {}
    if structures and os.path.isdir(structures):
        for fn in os.listdir(structures):
            if fn.endswith((".pdb", ".cif", ".mmcif")):
                smap[os.path.splitext(fn)[0]] = os.path.join(structures, fn)
    master["structure_path"] = master["seq_id"].map(smap)

    survivors = master[master["t0_pass"] & master["structure_path"].notna()]
    if len(survivors):
        t1 = tiers.t1_structure_audit(survivors, cfg)
        t1 = tiers.apply_filters(t1, cfg.get("t1_filters"), "t1")
        master = master.merge(t1, on="seq_id", how="left")
        master["t1_pass"] = master["t1_pass"].fillna(False)
        master.loc[~master["t0_pass"], "t1_reject_reason"] = "not evaluated (failed T0)"
        master.loc[master["t0_pass"] & master["structure_path"].isna(),
                   "t1_reject_reason"] = "no structure supplied"
        log(f"[triage] T1 structure filters: {int(master['t1_pass'].sum())}/{len(survivors)} pass")
    else:
        master["t1_pass"] = False
        master["t1_reject_reason"] = "not evaluated (no structures supplied)"
        log("[triage] T1 skipped -- no structures supplied")

    # ---- verdict ---------------------------------------------------------
    def verdict(r):
        if not r.get("t0_pass"):
            return "rejected_T0"
        if not r.get("t1_pass"):
            rr = str(r.get("t1_reject_reason") or "")
            return "passed_T0_pending_T1" if "not evaluated" in rr or "no structure" in rr else "rejected_T1"
        return "passed_T1"

    master["final_tier_reached"] = master.apply(verdict, axis=1)
    master["target_temperature_c"] = cfg.get("target_temperature_c")
    master["target_ph"] = cfg.get("target_ph")

    front = ["seq_id", "final_tier_reached", "t0_pass", "t0_composite_z",
             "t0_reject_reason", "t1_pass", "t1_reject_reason"]
    cols = [c for c in front if c in master.columns] + \
           [c for c in master.columns if c not in front and c != "seq"] + \
           (["seq"] if "seq" in master.columns else [])
    master = master[cols].sort_values(
        ["final_tier_reached", "t0_composite_z"], ascending=[True, False])
    master.to_csv(out_tsv, sep="\t", index=False, float_format="%.5g")
    log(f"[triage] wrote {out_tsv} ({len(master)} rows, {master.shape[1]} cols) "
        f"in {time.time()-t_start:.1f}s")

    if report_md:
        write_report(master, cfg, report_md, fasta)
    return master


def write_report(df, cfg, path, fasta):
    n = len(df)
    counts = df["final_tier_reached"].value_counts().to_dict()
    lines = [
        "# Triage run report", "",
        f"- Input: `{os.path.basename(fasta)}` ({n} sequences)",
        f"- Target: {cfg.get('target_temperature_c')} °C, pH {cfg.get('target_ph')}",
        f"- T0 reference mode: **{df['t0_reference_mode'].iloc[0] if 't0_reference_mode' in df and n else 'n/a'}**",
        "", "## Funnel", "",
        "| Outcome | Sequences | % of input |", "|---|---:|---:|",
    ]
    for k, v in sorted(counts.items()):
        lines.append(f"| {k} | {v} | {100.0*v/max(1,n):.1f}% |")
    lines += ["", "## Top rejection reasons", "", "| Tier | Reason | Count |", "|---|---|---:|"]
    for tier in ("t0", "t1"):
        col = f"{tier}_reject_reason"
        if col in df.columns:
            vc = df[df[col].astype(str).str.len() > 0][col].value_counts().head(5)
            for reason, cnt in vc.items():
                lines.append(f"| {tier.upper()} | {reason} | {cnt} |")
    with open(path, "w") as fh:
        fh.write("\n".join(lines) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Linear biophysical triage: FASTA in, TSV out.")
    ap.add_argument("--fasta", required=True)
    ap.add_argument("--config")
    ap.add_argument("--structures", help="directory of <seq_id>.pdb from ESMFold2/Boltz")
    ap.add_argument("--out", default="triage_results.tsv")
    ap.add_argument("--report", help="write a markdown run report here")
    a = ap.parse_args(argv)
    run(a.fasta, a.config, a.out, a.structures, a.report)


if __name__ == "__main__":
    main()
