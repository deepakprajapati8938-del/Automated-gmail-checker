"""
Phase 4: scheduled daily digest generation (spec section 20), built on top of
Phase 2's stored analyses rather than Phase 1's in-memory-only run log. Phase
1's /digest command (app/telegram/commands.py::digest_text) is the interim
version this will replace/extend, not duplicate.
"""
from __future__ import annotations


def build_digest(*args, **kwargs):
    raise NotImplementedError("Scheduled digest generation arrives in Phase 4. See IMPLEMENTATION_PLAN.md.")
