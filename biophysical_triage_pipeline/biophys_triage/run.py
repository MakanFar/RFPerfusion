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
from collections import Counter
import pandas as pd

from . import tiers

# Tier rank for sorting the output TSV, most-advanced first. `final_tier_reached`
# is a string ("passed_T0_pending_T1" sorts above "passed_T1" alphabetically),
# so an explicit rank is required or the funnel's real survivors end up buried
# under rows nobody has evaluated yet.
TIER_RANK = {
    "passed_T1": 0,
    "passed_T0_pending_T1": 1,
    "rejected_T1": 2,
    "rejected_T0": 3,
}


def read_fasta(path):
    recs, sid, buf = [], None, []
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if line.startswith(">"):
                if sid is not None:
                    recs.append((sid, "".join(buf)))
                tokens = line[1:].split()
                sid = tokens[0] if tokens else f"unnamed_{len(recs) + 1}"
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

    if not records:
        sys.exit(f"[triage] {fasta} contains no sequences -- nothing to triage")

    id_counts = Counter(sid for sid, _ in records)
    dupes = sorted(sid for sid, c in id_counts.items() if c > 1)
    if dupes:
        sys.exit(f"[triage] duplicate seq_id(s) in {fasta}: {dupes} -- "
                  "disambiguate the FASTA headers and re-run; a duplicate id "
                  "fans out the T1 merge and mis-attributes features")

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
        log(f"[triage] T1 structure filters: {int(master['t1_pass'].sum())}/{len(survivors)} pass")
    else:
        master["t1_pass"] = False
        master["t1_reject_reason"] = ""
        if smap:
            log("[triage] T1 skipped -- structures were supplied but no T0 "
                "survivor's seq_id matched a structure filename")
        else:
            log("[triage] T1 skipped -- no structures supplied")

    # Per-row reject reason, set uniformly whether or not any protein reached
    # T1: distinguishing "never got to T1 because T0 rejected it" from "T0
    # survivor but no matching structure file" -- and, within the latter,
    # whether structures were supplied at all -- so the no-survivors case
    # cannot misdiagnose "structures supplied but nothing matched" as
    # "no structures supplied".
    master.loc[~master["t0_pass"], "t1_reject_reason"] = "not evaluated (failed T0)"
    no_struct_mask = master["t0_pass"] & master["structure_path"].isna()
    if smap:
        master.loc[no_struct_mask, "t1_reject_reason"] = "no structure supplied for this seq_id"
    else:
        master.loc[no_struct_mask, "t1_reject_reason"] = "not evaluated (no structures supplied)"

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
    # Sort by tier rank (most-advanced first), not the "final_tier_reached"
    # string -- alphabetically "passed_T0_pending_T1" < "passed_T1", which
    # buries real T1 survivors under rows nobody has evaluated yet.
    tier_rank = master["final_tier_reached"].map(TIER_RANK).fillna(len(TIER_RANK))
    master = master[cols].assign(_tier_rank=tier_rank.to_numpy()).sort_values(
        ["_tier_rank", "t0_composite_z"], ascending=[True, False]).drop(columns="_tier_rank")
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
