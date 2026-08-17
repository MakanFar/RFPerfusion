"""The bridge between what a paper measured and what a tool can measure.

Evidence properties arrive as free text in the language of the experiment
("time-resolved EPR", "reorganization energy"); tools emit metric names
("avg_plddt", "iptm"). The two share no namespace, so intersecting them
directly can never match -- which is why `resolve_properties` returned
`requires_new_evaluator: true` for 45/45 items in the committed RF run
regardless of input.

This module holds the closed set of properties the catalogue can actually
address. Assigning NO term is the correct way to say "nothing measures
this"; inventing a term with no backing metric is not.
"""

import json


class UnknownTerm(ValueError):
    pass


def load(path):
    with open(path) as fh:
        return json.load(fh)


def metrics_for(ids, vocab):
    by_id = {t["id"]: t for t in vocab["terms"]}
    unknown = sorted(set(ids) - by_id.keys())
    if unknown:
        raise UnknownTerm(f"unknown vocabulary term(s): {', '.join(unknown)}")
    return {m for i in ids for m in by_id[i]["metrics"]}


def validate(vocab, catalog):
    """Every term must resolve to at least one metric the catalogue emits."""
    known = {m["metric"] for t in catalog["tools"] for m in t.get("measures", [])}
    errors = []
    for term in vocab["terms"]:
        if not set(term["metrics"]) & known:
            errors.append(
                f"vocabulary term '{term['id']}' resolves to no metric in the "
                f"registry; its metrics {term['metrics']} are all absent"
            )
    return errors
