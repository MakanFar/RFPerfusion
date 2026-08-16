from litkb import proto

ESMFOLD_OUT = """Output: ESMFoldOutput

  structures                list[Structure]                 (required)

Metrics (per structures item):
  avg_plddt                 float, range [0.0, 1.0], always, better=higher  *primary
  ptm                       float, range [0.0, 1.0], depends on model output, better=higher
  avg_pae                   float, range [0.0, inf], depends on model output, better=lower
  pae                       list[list[float]], range [0.0, inf], when include_pae_matrix=True, better=lower
"""

# Captured verbatim from `proto-tools output bindcraft-design`. Note the bare
# `Metrics:` header, the uppercase metric names, the non-ASCII unit, and
# `context-dependent` rather than `context`.
BINDCRAFT_OUT = """Output: BindCraftOutput

Metrics:
  dG                        float, range [-inf, inf], REU, better=lower
  dSASA                     float, range [0.0, inf], Å^2, better=context-dependent
  dG_per_dSASA              float, range [-inf, inf], REU/Å^2, better=lower
  interface_sasa_pct        float, range [0.0, 100.0], percent, better=context-dependent
"""

# From `proto-tools output dssp-secondary-structure`: a unit AND an
# availability between the range and better=.
DSSP_OUT = """Output: DSSPOutput

Metrics (per structures item):
  helix_pct                 float, range [0.0, 100.0], %, always, better=higher
"""

ABLANG_OUT = """Output: AbLangScoreOutput

Metrics (per sequences item):
  log_likelihood            float, range [-inf, 0.0], always, better=higher
      Sum over all positions. Grows with sequence length, so compare only at
      equal length.
  perplexity                float, range [1.0, inf], always, better=lower
"""

NO_METRICS_OUT = """Output: UniProtFetchOutput

  records                   list[Record]                    (required)
"""


def test_parses_primary_flag_and_bounded_range():
    m = proto.parse_metrics_doc(ESMFOLD_OUT)["measures"]
    first = m[0]
    assert first["metric"] == "avg_plddt"
    assert first["range"] == [0.0, 1.0]
    assert first["better"] == "higher"
    assert first["primary"] is True
    assert first["availability"] == "always"


def test_infinite_bound_becomes_null():
    m = {d["metric"]: d for d in proto.parse_metrics_doc(ESMFOLD_OUT)["measures"]}
    assert m["avg_pae"]["range"] == [0.0, None]
    assert m["pae"]["type"] == "list[list[float]]"


def test_only_one_metric_is_primary():
    m = proto.parse_metrics_doc(ESMFOLD_OUT)["measures"]
    assert [d["metric"] for d in m if d["primary"]] == ["avg_plddt"]


def test_bare_metrics_header_is_recognised():
    # bindcraft-design uses `Metrics:` with no `(per X item)` suffix.
    assert len(proto.parse_metrics_doc(BINDCRAFT_OUT)["measures"]) == 4


def test_uppercase_metric_names_are_parsed():
    # `dG` and `dG_per_dSASA` are real names; a lowercase-only pattern drops them.
    m = {d["metric"]: d for d in proto.parse_metrics_doc(BINDCRAFT_OUT)["measures"]}
    assert "dG" in m and "dG_per_dSASA" in m


def test_single_annotation_is_read_as_a_unit():
    m = {d["metric"]: d for d in proto.parse_metrics_doc(BINDCRAFT_OUT)["measures"]}
    assert m["dG"]["unit"] == "REU"
    assert m["dG"]["availability"] == ""
    assert m["dG"]["range"] == [None, None]


def test_unit_and_availability_together_are_split():
    m = {d["metric"]: d for d in proto.parse_metrics_doc(DSSP_OUT)["measures"]}
    assert m["helix_pct"]["unit"] == "%"
    assert m["helix_pct"]["availability"] == "always"


def test_availability_only_row_has_no_unit():
    m = {d["metric"]: d for d in proto.parse_metrics_doc(ESMFOLD_OUT)["measures"]}
    assert m["avg_plddt"]["availability"] == "always"
    assert m["avg_plddt"]["unit"] == ""


def test_better_context_dependent_is_the_literal_spelling():
    m = {d["metric"]: d for d in proto.parse_metrics_doc(BINDCRAFT_OUT)["measures"]}
    assert m["dSASA"]["better"] == "context-dependent"


def test_non_ascii_unit_survives():
    m = {d["metric"]: d for d in proto.parse_metrics_doc(BINDCRAFT_OUT)["measures"]}
    assert m["dSASA"]["unit"] == "Å^2"


def test_indented_continuation_lines_are_not_metrics():
    parsed = proto.parse_metrics_doc(ABLANG_OUT)
    assert [d["metric"] for d in parsed["measures"]] == ["log_likelihood", "perplexity"]
    assert parsed["failures"] == []


def test_tool_without_a_metrics_block_measures_nothing():
    parsed = proto.parse_metrics_doc(NO_METRICS_OUT)
    assert parsed["measures"] == []
    assert parsed["failures"] == []


def test_unparseable_row_is_recorded_not_dropped():
    doc = "Metrics (per structures item):\n  weird_metric  float, no range given\n"
    parsed = proto.parse_metrics_doc(doc)
    assert parsed["measures"] == []
    assert "weird_metric" in parsed["failures"][0]
