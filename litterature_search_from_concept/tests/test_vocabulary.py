import json
from pathlib import Path

import pytest

from litkb import proto, vocabulary

REGISTRY = Path(__file__).resolve().parents[2] / "registry" / "proto_catalog.json"
VOCAB = Path(__file__).resolve().parents[2] / "registry" / "property_vocabulary.json"


def test_every_term_resolves_to_a_real_metric():
    """The invariant that stops the vocabulary rotting as the catalogue moves.

    A term resolving to nothing would silently make an assessable property
    unassessable, which is the failure this whole design removes.
    """
    catalog = proto.load_catalog(REGISTRY)
    assert vocabulary.validate(vocabulary.load(VOCAB), catalog) == []


def test_term_ids_are_unique():
    vocab = vocabulary.load(VOCAB)
    ids = [t["id"] for t in vocab["terms"]]
    assert len(ids) == len(set(ids))


def test_metrics_for_unions_across_terms():
    vocab = {"version": 1, "terms": [
        {"id": "a", "definition": "x", "metrics": ["m1", "m2"]},
        {"id": "b", "definition": "y", "metrics": ["m2", "m3"]},
    ]}
    assert vocabulary.metrics_for(["a", "b"], vocab) == {"m1", "m2", "m3"}


def test_metrics_for_ignores_no_terms():
    vocab = vocabulary.load(VOCAB)
    assert vocabulary.metrics_for([], vocab) == set()


def test_validate_reports_a_term_backed_by_no_metric():
    vocab = {"version": 1, "terms": [
        {"id": "phlogiston", "definition": "not a thing", "metrics": ["nope"]},
    ]}
    catalog = {"schema_version": 2, "tools": [
        {"key": "t", "measures": [{"metric": "avg_plddt"}]}]}
    errors = vocabulary.validate(vocab, catalog)
    assert len(errors) == 1 and "phlogiston" in errors[0]


def test_unknown_term_id_is_rejected():
    vocab = vocabulary.load(VOCAB)
    with pytest.raises(vocabulary.UnknownTerm):
        vocabulary.metrics_for(["not_a_term"], vocab)
