"""The design-brief plan contract, in exactly one place.

`design-brief-007` emits a FLAT plan with three keys. Both consumers here --
`paperclip_kb.py` and `litkb` -- must accept precisely the same set, and they
used to enforce it with two hand-mirrored copies. This module imports
nothing, so sharing it does not give litkb an import dependency on the
sibling script, which is the reason the mirror existed.

`check()` returns a list of (kind, message) pairs rather than plain strings.
`kind` is either "type" or "value", naming which exception paperclip_kb.py's
`validate_plan` should raise for that problem -- a non-dict plan or a
non-string `notes` are TYPE problems (TypeError, matching the pre-refactor
behaviour), everything else is a VALUE problem (ValueError). Carrying the
kind structurally means a caller never has to sniff a message's wording
(e.g. for the substring "must be a string") to recover which exception type
to raise -- rewording a message can't silently change that anymore. litkb
only wants the messages, so `contracts.validate_brief_plan` unwraps them.

See .claude/skills/design-brief-007/references/handoff-contract.md.
"""

BRIEF_PLAN_KEYS = ("search_phrases", "mechanism_patterns", "notes")


def check(plan):
    """Return a list of (kind, message) problems; empty means the plan is
    acceptable. `kind` is "type" or "value" -- see the module docstring."""
    if not isinstance(plan, dict):
        return [("type", "brief plan must be a JSON object")]

    missing = [k for k in BRIEF_PLAN_KEYS if k not in plan]
    if missing:
        return [("value", f"brief plan is missing required key(s): {', '.join(missing)}")]

    errors = []
    for key in ("search_phrases", "mechanism_patterns"):
        values = plan[key]
        if not isinstance(values, list) or not values:
            errors.append(("value", f"brief plan.{key} must be a non-empty list"))
        elif not all(isinstance(v, str) and v.strip() for v in values):
            errors.append(("value", f"brief plan.{key} must contain non-empty strings"))
    if not isinstance(plan.get("notes"), str):
        errors.append(("type", "brief plan.notes must be a string"))
    return errors
