"""Proto-tools allowlist and cost model.

This exists for one reason: a model asked to design a computational fitness
cascade will happily invent a tool that does exactly what the design needs.
`validate.py` rejects any gate naming a key that is not here, so a hallucinated
capability fails the run instead of reaching the Modal agent as an instruction.

IMPORTANT — this list is a *hallucination guard*, not ground truth. It was
transcribed from the proto-tools catalogue and will drift. The downstream Proto
agent must confirm every key with `search_tools` / `list_tools` before running
anything, per `.claude/skills/proto-tools/SKILL.md`. A key being present here
does not mean it is deployed on the user's Modal workspace, and deployment is
billable.
"""

from __future__ import annotations

# --------------------------------------------------------------------------
# tool keys, grouped by what they are for
# --------------------------------------------------------------------------

STRUCTURE_PREDICTION = {
    "alphafold2",
    "alphafold3",
    "boltz2",
    "chai1",
    "esmfold",
    "esmfold2",
    "opendde",
    "protenix",
    "rf3",
}

SEQUENCE_DESIGN = {"esm_if1", "fampnn", "ligandmpnn", "proteinmpnn"}

BINDER_DESIGN = {"bindcraft", "freebindcraft", "germinal"}

LANGUAGE_MODELS = {
    "ablang",
    "codonfm",
    "esm2",
    "esm3",
    "esmc",
    "evo1",
    "evo2",
    "progen2",
    "progen3",
}

SCORING = {
    "dssp",
    "ipsae",
    "metal3d",
    "pdockq2",
    "pyrosetta",
    "structure_metrics",
}

DYNAMICS = {"bioemu"}

DOCKING = {"vina"}

ALIGNMENT = {
    "blast",
    "foldmason",
    "foldseek",
    "mafft",
    "mmseqs2",
    "tmalign",
    "usalign",
}

RETRIEVAL = {
    "alphafold_db",
    "alphamissense_db",
    "ensembl",
    "ncbi",
    "pdb",
    "sequence_fetch",
    "uniprot",
}

NUCLEIC_ACID = {
    "alphagenome",
    "borzoi",
    "crispr_tracr_rna",
    "enformer",
    "meme",
    "minced",
    "miranda",
    "orfipy",
    "pangolin",
    "parade",
    "primer3",
    "prodigal",
    "promoter_calculator",
    "pyhmmer",
    "spliceai",
    "splice_transformer",
    "viennarna",
    "x3dna",
}

PROTO_TOOL_KEYS: frozenset[str] = frozenset(
    STRUCTURE_PREDICTION
    | SEQUENCE_DESIGN
    | BINDER_DESIGN
    | LANGUAGE_MODELS
    | SCORING
    | DYNAMICS
    | DOCKING
    | ALIGNMENT
    | RETRIEVAL
    | NUCLEIC_ACID
)


# --------------------------------------------------------------------------
# cost tiers
# --------------------------------------------------------------------------
# Ordering the cascade cheap-first is the single highest-leverage decision in
# the design loop: the expensive tools should only ever see candidates that
# already survived the cheap ones. `validate.py` enforces non-decreasing cost.

CHEAP = (
    LANGUAGE_MODELS
    | ALIGNMENT
    | RETRIEVAL
    | {"dssp", "structure_metrics", "esmfold", "esmfold2", "proteinmpnn", "esm_if1"}
)
MODERATE = {
    "boltz2",
    "chai1",
    "protenix",
    "ligandmpnn",
    "fampnn",
    "metal3d",
    "pdockq2",
    "ipsae",
    "vina",
    "pyrosetta",
    "opendde",
}
EXPENSIVE = {"alphafold2", "alphafold3", "rf3", "bioemu"} | BINDER_DESIGN

COST_TIERS = ("cheap", "moderate", "expensive")
_COST_RANK = {tier: i for i, tier in enumerate(COST_TIERS)}


def cost_tier(tool_key: str) -> str:
    """Best-known cost tier for a tool key; unknown keys are treated as costly."""
    if tool_key in CHEAP:
        return "cheap"
    if tool_key in MODERATE:
        return "moderate"
    return "expensive"


def cost_rank(tier: str) -> int:
    return _COST_RANK.get(tier, len(COST_TIERS))


def gate_cost_tier(tool_keys: list[str]) -> str:
    """A gate costs what its most expensive tool costs."""
    if not tool_keys:
        return "cheap"
    return max((cost_tier(k) for k in tool_keys), key=cost_rank)


# --------------------------------------------------------------------------
# metrics a gate may threshold on
# --------------------------------------------------------------------------
# Restricting the vocabulary stops "high confidence" and "good binding" from
# being written down as if they were measurements.

PROTO_METRICS: frozenset[str] = frozenset(
    {
        # per-structure confidence
        "plddt",
        "mean_plddt",
        "ptm",
        "iptm",
        "pae",
        "pde",
        "ipsae",
        "pdockq2",
        # geometry / comparison
        "tm_score",
        "rmsd",
        "backbone_rmsd",
        "sasa",
        "contact_count",
        "helix_fraction",
        "radius_of_gyration",
        # energetics
        "ddg",
        "dg_fold",
        "binding_affinity",
        "vina_score",
        # ensembles
        "population_fraction",
        "cluster_count",
        "ensemble_rmsf",
        # sequence-level
        "sequence_recovery",
        "pseudo_perplexity",
        "log_likelihood",
        "sequence_identity",
        # sites
        "metal_site_probability",
    }
)

# Metrics that are only meaningful for a complex — a gate using one of these
# must declare that it is scoring an assembly, not a lone chain.
INTERFACE_METRICS: frozenset[str] = frozenset(
    {"iptm", "ipsae", "pdockq2", "binding_affinity", "vina_score"}
)


def unknown_tools(keys: list[str]) -> list[str]:
    return sorted({k for k in keys if k not in PROTO_TOOL_KEYS})


def catalogue_digest() -> str:
    """Compact tool listing for a prompt. Grouped so selection is informed."""
    groups = [
        ("structure prediction", STRUCTURE_PREDICTION),
        ("sequence design / inverse folding", SEQUENCE_DESIGN),
        ("binder design", BINDER_DESIGN),
        ("protein + nucleotide language models", LANGUAGE_MODELS),
        ("structure scoring", SCORING),
        ("conformational dynamics", DYNAMICS),
        ("docking", DOCKING),
        ("alignment / structure search", ALIGNMENT),
        ("database retrieval", RETRIEVAL),
        ("nucleic acid", NUCLEIC_ACID),
    ]
    lines = []
    for name, keys in groups:
        lines.append(f"  {name}: {', '.join(sorted(keys))}")
    return "\n".join(lines)
