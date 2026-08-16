#!/usr/bin/env python3
"""RFPerfusion pipeline entrypoint.

    python design.py                       # full run, real Paperclip, free eval
    python design.py --offline             # skip live Paperclip searches
    python design.py --goal "..."          # override the design goal

Billable paths (off by default): --gen proto_esm2 and --modal-eval require
approved proto-tools Modal deploys.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from rfperfusion.orchestrator import RunConfig, run  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description="RFPerfusion — SWIR-actuated TlpA thermal switch design")
    p.add_argument("--goal", default=None, help="override the design goal")
    p.add_argument("--offline", action="store_true", help="skip live Paperclip searches")
    p.add_argument("--gen", default="heuristic", choices=["heuristic", "proto_esm2"])
    p.add_argument("--modal-eval", action="store_true", help="run billable ESMFold/PyRosetta scoring")
    p.add_argument("-n", "--n-candidates", type=int, default=120)
    p.add_argument("-k", "--top-k", type=int, default=5)
    args = p.parse_args()

    cfg = RunConfig(
        goal=args.goal,
        live_literature=not args.offline,
        gen_method=args.gen,
        n_candidates=args.n_candidates,
        use_modal_eval=args.modal_eval,
        top_k=args.top_k,
    )
    run(cfg)


if __name__ == "__main__":
    main()
