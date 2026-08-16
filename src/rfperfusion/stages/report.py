"""Reporting stage (PRD §8 demo narrative). Console output for the 4 beats +
writes the judged artifact (candidates.json) and the full Design Record."""

from __future__ import annotations

import json

from ..config import OUTPUTS
from ..schemas import DesignRecord, ScoredCandidate


def report(record: DesignRecord, top: list[ScoredCandidate], funnel: dict) -> None:
    print("\n" + "=" * 72)
    print("RFPerfusion — SWIR-actuated protein thermal switch")
    print("=" * 72)

    # Beat 1 — the wall (L1 negative result)
    print("\n[1] THE QUESTION AND THE WALL")
    print(f"    goal: {record.goal}")
    if record.mechanism and record.mechanism.rejected_alternatives:
        r = record.mechanism.rejected_alternatives[0]
        print(f"    ✗ rejected '{r.id}': {r.reason}")

    # Beat 2 — the redirect
    print("\n[2] THE REDIRECT")
    if record.mechanism:
        print(f"    mechanism [{record.mechanism.status}]: " + " → ".join(record.mechanism.chain))
    sc = record.scaffold
    print(f"    scaffold: {sc.name} "
          f"(UniProt {sc.uniprot or '?'}, {sc.length_aa or '?'} aa, "
          f"DBD immutable {sc.immutable_regions})")

    # Beat 3 — generation under constraint
    print("\n[3] GENERATION UNDER CONSTRAINT")
    print(f"    funnel: {funnel['generated']} generated "
          f"→ {funnel['passing_hard_constraints']} pass hard constraints "
          f"→ {funnel['novel']} novel")
    hard = [c.id for c in record.constraints if c.hard]
    print(f"    hard constraints: {', '.join(hard)}")

    # Beat 4 — the artifact + error bars
    print("\n[4] THE ARTIFACT AND ITS ERROR BARS")
    if not top:
        print("    (no eligible candidates — check scaffold sequence resolution)")
    for s in top:
        tm = s.scores.get("c_tm_target")
        nov = s.scores.get("c_novelty")
        tm_str = f"Tm {tm.value}°C (conf {tm.confidence})" if tm else "Tm pending_modal"
        nov_str = f"novelty {nov.value}" if nov else "novelty n/a"
        print(f"    {s.id}  {','.join(s.mutations) or '(no muts)':<28}  {tm_str:<26}  {nov_str}")
    pending = sorted({f.split(':')[0] for s in top for f in s.flags if f.endswith('pending_modal')})
    if pending:
        print(f"    ⚠ pending Modal scoring (not fabricated): {', '.join(pending)}")
    print("    ⚠ all values are computational predictions; no candidate expressed.")

    _write_artifacts(record, top)


def _write_artifacts(record: DesignRecord, top: list[ScoredCandidate]) -> None:
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    (OUTPUTS / "design_record.json").write_text(record.model_dump_json(indent=2))
    (OUTPUTS / "candidates.json").write_text(
        json.dumps([s.model_dump() for s in top], indent=2))
    print(f"\n    wrote {OUTPUTS/'design_record.json'}")
    print(f"    wrote {OUTPUTS/'candidates.json'}  (the judged artifact)")
