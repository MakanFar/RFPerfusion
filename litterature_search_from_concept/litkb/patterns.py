"""Structural patterns -- concept-independent, so they are fixed here rather
than planned per objective.

These feed the DesignSpec side of the framework (scaffold, mutable_space),
not the Route side. paperclip's engine supports lookaround, verified against
0.7.36, which is what lets the accession patterns exclude DOI context.

`ignore_case` is per-category on purpose: the amino-acid classes are
case-significant, and -i would let [ACDEFGHIKLMNPQRSTVWY]{25,} match ordinary
lowercase prose.
"""

# Accessions appear inside DOIs and catalogue numbers far more often than as
# real accessions -- 10.1039/C5CP06731F reads as "P06731", 10.1113/JP272718 as
# "P27271". Anchor both sides to reject those.
_L = r"(?<![A-Za-z0-9./])"
_R = r"(?![A-Za-z0-9])"

STRUCTURAL = {
    "sequence": {
        "ignore_case": False,
        "patterns": [
            r"[ACDEFGHIKLMNPQRSTVWY]{25,}",
            "amino acid sequence",
            "sequence is available",
            "Supplementary Sequence",
            "codon-optimized",
            "synthesized as a gBlock",
        ],
    },
    "database_id": {
        "ignore_case": False,
        "patterns": [
            _L + r"[OPQ][0-9][A-Z0-9]{3}[0-9]" + _R,
            _L + r"[A-NR-Z][0-9][A-Z][A-Z0-9]{2}[0-9]" + _R,
            _L + r"[NX][MPR]_[0-9]{6,}" + _R,
            r"PDB[ :]?[0-9][A-Za-z0-9]{3}",
            r"EC [0-9]+\.[0-9]+\.[0-9]+\.[0-9]+",
            "Addgene",
            "deposited in the Protein Data Bank",
        ],
    },
    "mutation": {
        "ignore_case": False,
        "patterns": [
            r"\b[ACDEFGHIKLMNPQRSTVWY][0-9]{1,4}[ACDEFGHIKLMNPQRSTVWY]\b",
            "site-directed mutagenesis",
            "saturation mutagenesis",
            "single point mutation",
        ],
    },
    "quantitative": {
        "ignore_case": True,
        "patterns": [
            "quantum yield",
            "extinction coefficient",
            "dissociation constant",
            "catalytic efficiency",
            "melting temperature",
            r"[Kk]cat",
            r"K[dDmM] of",
        ],
    },
}
