"""
Phase 5: turns accumulated feedback (app/database/repositories -> `feedback`
table) into adaptive per-sender/category importance adjustments (spec section
19). Phase 1 already records feedback (see handlers.py::callback_handler) so
Phase 5 has real data to learn from on day one — it just isn't used to adjust
scoring yet.
"""
from __future__ import annotations


def adjust_score(*args, **kwargs):
    raise NotImplementedError("Adaptive personalization arrives in Phase 5. See IMPLEMENTATION_PLAN.md.")
