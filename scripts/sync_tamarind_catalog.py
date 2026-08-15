"""
Refresh registry/tamarind_catalog.json from Tamarind's live tool catalog.

This is a raw discovery snapshot only — every tool Tamarind exposes to this
account, with its name/description/settings schema. It is NOT the framework's
Evaluator Registry (see registry/evaluators.json / docs/PRD-framework.md).
An entry here is a candidate; it becomes a real evaluator only after someone
curates measures/applicable_to/known_reliability for it.

Usage:
    export TAMARIND_API_KEY=...   # or put it in .env and use python-dotenv
    python scripts/sync_tamarind_catalog.py
"""

import json
import os
import sys
from pathlib import Path

import requests

BASE = "https://app.tamarind.bio/api/"
OUT_PATH = Path(__file__).parent.parent / "registry" / "tamarind_catalog.json"


def main() -> None:
    api_key = os.environ.get("TAMARIND_API_KEY")
    if not api_key:
        sys.exit("TAMARIND_API_KEY is not set. Copy .env.example to .env and fill it in.")

    resp = requests.get(BASE + "tools", headers={"x-api-key": api_key}, timeout=30)
    resp.raise_for_status()
    tools = resp.json()

    catalog = [
        {
            "name": t["name"],
            "displayName": t.get("displayName"),
            "description": t.get("description"),
            "required_settings": [
                p["name"] for p in t.get("settings", []) if p.get("required")
            ],
            "all_settings": [p["name"] for p in t.get("settings", [])],
        }
        for t in tools
    ]

    OUT_PATH.parent.mkdir(exist_ok=True)
    OUT_PATH.write_text(json.dumps(catalog, indent=2, sort_keys=False) + "\n")
    print(f"Wrote {len(catalog)} tools to {OUT_PATH}")
    print("Reminder: this is a cached snapshot. Treat GET /tools (live) as ground truth "
          "when actually submitting a job — schemas change.")


if __name__ == "__main__":
    main()
