"""Tier implementations for the biophysical triage pipeline.

Each tier exposes:
    run(records, cfg) -> (DataFrame of features, DataFrame of pass/fail)

`records` is a list of (seq_id, sequence) for T0, or a DataFrame carrying a
`structure_path` column for T1/T2.  Every tier is pure: it computes features
and applies thresholds from cfg, and never mutates its input.
"""
from __future__ import annotations
import math
import numpy as np
import pandas as pd

# Residues whose frequency shifts with thermal adaptation.
IVYWREL = set("IVYWREL")
THERMOLABILE = set("QNCMDST")   # deamidation / oxidation prone
CHARGED = set("DEKR")
POLAR_UNCHARGED = set("NQSTY")


# ---------------------------------------------------------------- T0
def t0_descriptors(records, cfg):
    """Sequence-only biophysical descriptors. ~10 ms/protein, pure CPU."""
    import peptides

    ph = float(cfg.get("target_ph", 7.0))
    rows = []
    for sid, seq in records:
        seq = str(seq).upper().replace("*", "")
        clean = "".join(c for c in seq if c.isalpha())
        L = len(clean)
        if L == 0:
            continue
        pep = peptides.Peptide(clean)
        counts = {a: clean.count(a) for a in set(clean)}
        f = lambda group: sum(counts.get(a, 0) for a in group) / L

        charged_f = f(CHARGED)
        polar_f = f(POLAR_UNCHARGED)
        try:
            instability = pep.instability_index()
        except Exception:
            instability = float("nan")

        rows.append({
            "seq_id": sid,
            "length": L,
            "ivywrel_frac": f(IVYWREL),
            "charged_frac": charged_f,
            "thermolabile_frac": f(THERMOLABILE),
            "polar_uncharged_frac": polar_f,
            # CvP bias: (D+E+K+R) - (N+Q+S+T) per 100 residues. A classic
            # thermal-adaptation discriminator.
            "cvp_bias": 100.0 * (charged_f - polar_f),
            "ek_over_qh": (counts.get("E", 0) + counts.get("K", 0)) /
                          max(1, counts.get("Q", 0) + counts.get("H", 0)),
            "aliphatic_index": pep.aliphatic_index(),
            "gravy": pep.hydrophobicity(scale="KyteDoolittle"),
            "net_charge_at_ph": pep.charge(pH=ph),
            "isoelectric_point": pep.isoelectric_point(),
            "instability_index": instability,
            "boman": pep.boman(),
            "seq": clean,
        })
    return pd.DataFrame(rows)


def t0_score(df, cfg):
    """Composite z-score against a mesophilic background.

    Reference means/sds come from cfg['t0_reference']; when absent, the batch
    itself is used and the score is explicitly relative (documented in the
    report, so nobody mistakes it for an absolute Tm).
    """
    feats = cfg.get("t0_score_features",
                    ["ivywrel_frac", "cvp_bias", "charged_frac", "aliphatic_index"])
    signs = cfg.get("t0_score_signs", {f: 1.0 for f in feats})
    ref = cfg.get("t0_reference", {})
    z = np.zeros(len(df), dtype=float)
    used = 0
    for f in feats:
        if f not in df.columns:
            continue
        col = df[f].astype(float)
        mu = ref.get(f, {}).get("mean", col.mean())
        sd = ref.get(f, {}).get("sd", col.std(ddof=0))
        if not sd or math.isnan(sd) or sd == 0:
            continue
        z = z + float(signs.get(f, 1.0)) * ((col - mu) / sd).to_numpy()
        used += 1
    out = df.copy()
    out["t0_composite_z"] = z / max(1, used)
    out["t0_reference_mode"] = "external" if ref else "batch_relative"
    return out


# ---------------------------------------------------------------- T1
def t1_structure_audit(df, cfg):
    """Static-structure features from a predicted PDB/mmCIF.

    Requires a `structure_path` column. Every geometric feature is gated on
    per-residue confidence: a salt bridge inside a pLDDT<cutoff region is not
    counted, because predicted-coordinate noise there is larger than the
    feature being measured.
    """
    import biotite.structure as struc
    import biotite.structure.io.pdb as pdb

    plddt_min = float(cfg.get("plddt_min", 70.0))
    sb_cut = float(cfg.get("salt_bridge_cutoff_a", 4.0))
    rows = []
    for _, r in df.iterrows():
        path = r.get("structure_path")
        rec = {"seq_id": r["seq_id"]}
        if not path or not isinstance(path, str):
            rows.append(rec)
            continue
        try:
            # b_factor must be requested explicitly or biotite drops it, and
            # for AF2/ESMFold that column IS the pLDDT the gate depends on.
            arr = pdb.PDBFile.read(path).get_structure(
                model=1, extra_fields=["b_factor"])
            arr = arr[struc.filter_amino_acids(arr)]
            ca = arr[arr.atom_name == "CA"]
            if "b_factor" in arr.get_annotation_categories():
                plddt = np.asarray(ca.b_factor, dtype=float)
                plddt_source = "b_factor"
            else:
                plddt = np.full(ca.array_length(), np.nan)
                plddt_source = "absent"
            conf_ok = plddt >= plddt_min
            rec["plddt_source"] = plddt_source

            acid = arr[np.isin(arr.res_name, ["ASP", "GLU"]) &
                       np.isin(arr.atom_name, ["OD1", "OD2", "OE1", "OE2"])]
            base = arr[np.isin(arr.res_name, ["LYS", "ARG"]) &
                       np.isin(arr.atom_name, ["NZ", "NH1", "NH2", "NE"])]
            # Confidence gate: only count an ion pair when BOTH partners sit in
            # well-predicted regions. In a pLDDT<cutoff loop the coordinate
            # error exceeds the 4 A criterion, so such a "salt bridge" is an
            # artifact of the prediction, not a property of the protein.
            conf_res = {int(r) for r, ok in zip(ca.res_id, conf_ok) if ok} \
                if plddt_source == "b_factor" else None
            n_sb = n_sb_ungated = 0
            if acid.array_length() and base.array_length():
                d = np.linalg.norm(
                    acid.coord[:, None, :] - base.coord[None, :, :], axis=-1)
                seen, seen_gated = set(), set()
                for i, j in np.argwhere(d < sb_cut):
                    ri, rj = int(acid.res_id[i]), int(base.res_id[j])
                    if (ri, rj) not in seen:
                        seen.add((ri, rj))
                        n_sb_ungated += 1
                    if conf_res is None or (ri in conf_res and rj in conf_res):
                        if (ri, rj) not in seen_gated:
                            seen_gated.add((ri, rj))
                            n_sb += 1
            sasa = struc.sasa(arr, vdw_radii="Single")
            total_sasa = float(np.nansum(sasa))
            rec.update({
                "n_residues": int(ca.array_length()),
                "mean_plddt": float(np.mean(plddt)),
                "frac_confident": float(np.mean(conf_ok)),
                "n_salt_bridges": int(n_sb),
                "n_salt_bridges_ungated": int(n_sb_ungated),
                "n_salt_bridges_lowconf_discarded": int(n_sb_ungated - n_sb),
                "salt_bridges_per_100aa": 100.0 * n_sb / max(1, ca.array_length()),
                "total_sasa_a2": total_sasa,
                "sasa_per_residue": total_sasa / max(1, ca.array_length()),
            })
            try:
                sse = struc.annotate_sse(arr)
                rec["helix_frac"] = float(np.mean(sse == "a")) if len(sse) else float("nan")
                rec["sheet_frac"] = float(np.mean(sse == "b")) if len(sse) else float("nan")
                rec["coil_frac"] = float(np.mean(sse == "c")) if len(sse) else float("nan")
            except Exception:
                pass
        except Exception as e:  # a bad structure fails this protein, not the run
            rec["t1_error"] = f"{type(e).__name__}: {e}"
        rows.append(rec)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- filters
def apply_filters(df, rules, tier):
    """Apply {feature: {min/max}} rules; return df with pass flag + reason."""
    keep = pd.Series(True, index=df.index)
    reasons = pd.Series("", index=df.index)
    for feat, rule in (rules or {}).items():
        if feat not in df.columns:
            continue
        col = pd.to_numeric(df[feat], errors="coerce")
        if "min" in rule:
            bad = col < float(rule["min"])
            reasons[bad & keep] = f"{feat}<{rule['min']}"
            keep &= ~bad.fillna(False)
        if "max" in rule:
            bad = col > float(rule["max"])
            reasons[bad & keep] = f"{feat}>{rule['max']}"
            keep &= ~bad.fillna(False)
    out = df.copy()
    out[f"{tier}_pass"] = keep.to_numpy()
    out[f"{tier}_reject_reason"] = reasons.to_numpy()
    return out


def top_fraction(df, col, frac, tier):
    """Keep the top `frac` by `col` — the rank-based alternative to hard cuts."""
    out = df.copy()
    n_keep = max(1, int(round(len(df) * float(frac))))
    thresh = out[col].nlargest(n_keep).min()
    passed = out[col] >= thresh
    prev = out.get(f"{tier}_pass", pd.Series(True, index=out.index))
    out[f"{tier}_pass"] = (prev.to_numpy() & passed.to_numpy())
    rr = out.get(f"{tier}_reject_reason", pd.Series("", index=out.index)).to_numpy().copy()
    rr[(~passed.to_numpy()) & (rr == "")] = f"{col} below top-{frac:g} cutoff"
    out[f"{tier}_reject_reason"] = rr
    return out
