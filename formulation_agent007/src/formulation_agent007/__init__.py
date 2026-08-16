"""formulation_agent007 — design-brief generator for protein engineering.

Sibling of `formulation_agent`. Where that one asks *which direction is
grounded*, this one asks *what do we actually build, what do we go read, and
what number decides whether a design survives*.

Input:  one generic protein design question.
Output: a build plan — shard decomposition, a Paperclip mining concept + plan
        that drops straight into `litterature_search_from_concept/paperclip_kb.py`,
        a sequence-harvest contract, a stitching recipe, and an ordered
        proto-tools fitness cascade with numeric kill thresholds.
"""

from .models import DesignBrief

__all__ = ["DesignBrief"]
