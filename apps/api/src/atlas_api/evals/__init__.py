"""Offline agent-quality evaluation harness.

Distinct from the determinism tests in ``tests/``: this scores the research
agent on quality dimensions — no uncited claims, source coverage, source
diversity, and (on live runs) citation presence — over a fixed question set.
Runs live with Claude on a schedule in CI; runs structurally under a fake model
per-PR via ``tests/test_evals.py``.
"""

from atlas_api.evals.harness import CaseResult, EvalSummary, run_eval, summarize
from atlas_api.evals.questions import EVAL_QUESTIONS

__all__ = ["run_eval", "summarize", "CaseResult", "EvalSummary", "EVAL_QUESTIONS"]
