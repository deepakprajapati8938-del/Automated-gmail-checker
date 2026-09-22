"""
Phase 3: a narrower agent/helper focused purely on turning a natural-language
question into a sequence of retrieval-tool calls (spec section 15's hybrid
retrieval flow), separate from EmailAgent's answer-composition responsibility.
Not implemented in Phase 1.
"""
from __future__ import annotations


class RetrievalAgent:
    def __init__(self, *args, **kwargs):
        raise NotImplementedError("RetrievalAgent arrives in Phase 3. See IMPLEMENTATION_PLAN.md.")
