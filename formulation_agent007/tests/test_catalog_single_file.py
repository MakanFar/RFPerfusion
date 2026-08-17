"""Finding 1 (fix round 1): `catalog.py` used to read TWO registry files --
the snapshot AND the full `proto_catalog.json` it was distilled from, just to
get the `primary` flag. That defeated the point of having a snapshot: 007
would hard-fail on import if `proto_catalog.json` were ever pruned while the
snapshot remained. `primary` now lives in the snapshot itself
(`litkb proto-sync`'s `_snapshot_from_catalog`), so `catalog.py` should read
exactly ONE registry file. These are real guards, not comments: one inspects
the source for the offending path, the other actually hides
`proto_catalog.json` on disk and proves the module still imports and works.
"""

from __future__ import annotations

import importlib
import inspect
import os

from formulation_agent007 import catalog as catalog_module


def test_catalog_source_never_names_proto_catalog_json():
    source = inspect.getsource(catalog_module)
    assert "proto_catalog.json" not in source
    # the snapshot path must still be there -- this isn't "reads nothing"
    assert "proto_metrics.json" in source


def test_catalog_works_with_proto_catalog_json_absent(tmp_path):
    """Hide the real proto_catalog.json, reload catalog.py fresh, and prove
    it still imports and metric_digest() still runs. If catalog.py secretly
    needed a second file, this reload would raise FileNotFoundError -- the
    exact failure mode Finding 1 described."""
    registry_dir = catalog_module._SNAPSHOT_PATH.parent
    catalog_json = registry_dir / "proto_catalog.json"
    assert catalog_json.exists(), (
        "fixture assumption: proto_catalog.json exists in this checkout"
    )
    hidden = tmp_path / "proto_catalog.json.hidden"
    os.rename(catalog_json, hidden)
    try:
        reloaded = importlib.reload(catalog_module)
        digest = reloaded.metric_digest()
        assert digest
        assert "better=higher" in digest
        assert reloaded.PROTO_METRICS
        assert reloaded.PROTO_TOOL_KEYS
    finally:
        os.rename(hidden, catalog_json)
        importlib.reload(catalog_module)  # restore normal state for other tests
