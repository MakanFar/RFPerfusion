"""Scaffold-resolution stage (PRD M0). Resolve the real TlpA UniProt accession,
sequence and length via Paperclip's /proteins/ VFS, and record the DBD/coiled-coil
boundary. This turns the provisional hints in config.py into cited facts.
"""

from __future__ import annotations

import json
import re

from .. import config
from ..tools import paperclip
from ..schemas import DesignRecord

_ACC_RE = re.compile(r"\b([OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9]([A-Z][A-Z0-9]{2}[0-9]){1,2})\b")
_CACHE = config.OUTPUTS / "tlpa_resolved.json"


def resolve_scaffold(record: DesignRecord) -> DesignRecord:
    """Resolve TlpA. Prefers a cached resolution file (outputs/tlpa_resolved.json)
    written by the Paperclip resolver; falls back to a live search. On any failure
    keeps the config hints and flags it, so the pipeline never hard-blocks (§9.2)."""
    if _CACHE.exists():
        try:
            return _from_cache(record, json.loads(_CACHE.read_text()))
        except Exception as e:  # noqa: BLE001
            record.human_decisions.append(_note(f"cache read failed ({e}); trying live lookup"))
    query = f"{config.SCAFFOLD_NAME} {config.SCAFFOLD_ORGANISM} coiled-coil thermal repressor"
    try:
        hits = paperclip.search_proteins(query, n=5)
    except Exception as e:  # noqa: BLE001 - resolution is best-effort
        record.scaffold.uniprot = record.scaffold.uniprot or "UNRESOLVED"
        record.human_decisions.append(
            _note(f"scaffold lookup failed ({e}); using config hints"))
        return record

    accs = _ACC_RE.findall(hits)
    acc = accs[0][0] if accs and isinstance(accs[0], tuple) else (accs[0] if accs else None)
    if not acc:
        record.human_decisions.append(_note("no UniProt accession parsed from search; using hints"))
        return record

    try:
        meta = paperclip.protein_meta(acc)
    except Exception:
        meta = {}

    seq = meta.get("sequence") or meta.get("seq")
    length = meta.get("length") or (len(seq) if seq else None)
    record.scaffold.uniprot = acc
    if seq:
        record.scaffold.sequence = seq
    if length:
        record.scaffold.length_aa = int(length)
    record.human_decisions.append(
        _note(f"resolved {config.SCAFFOLD_NAME} -> UniProt {acc}"
              f"{f' ({length} aa)' if length else ''}"))
    return record


def _from_cache(record: DesignRecord, data: dict) -> DesignRecord:
    sc = record.scaffold
    sc.uniprot = data.get("uniprot") or sc.uniprot
    if data.get("sequence"):
        sc.sequence = data["sequence"]
    if data.get("length_aa"):
        sc.length_aa = int(data["length_aa"])
    dbd = data.get("dbd_region")
    if dbd and len(dbd) == 2:
        sc.immutable_regions = [(int(dbd[0]), int(dbd[1]))]
    record.human_decisions.append(_note(
        f"loaded {sc.name} from cache -> UniProt {sc.uniprot} "
        f"({sc.length_aa} aa, DBD {sc.immutable_regions})"))
    return record


def _note(msg: str):
    from ..schemas import HumanDecision
    return HumanDecision(at="scaffold_resolution", decision=msg, by="pipeline")
