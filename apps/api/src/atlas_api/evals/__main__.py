"""Live agent-quality eval: ``python -m atlas_api.evals`` (needs ANTHROPIC_API_KEY)."""

import asyncio
import sys

from atlas_api.agents.models import build_chat_model
from atlas_api.agents.runner import default_provider
from atlas_api.config import get_settings
from atlas_api.evals.harness import run_eval, summarize
from atlas_api.evals.questions import EVAL_QUESTIONS


async def _main() -> int:
    settings = get_settings()
    if not settings.anthropic_api_key:
        print("ANTHROPIC_API_KEY not set — skipping live eval.")
        return 0
    model = build_chat_model(settings)
    provider = default_provider(settings)
    cases = await run_eval(EVAL_QUESTIONS, model=model, provider=provider, settings=settings)
    summary = summarize(cases, require_citations=True)

    print(f"\n{'question':<48} {'src':>4} {'claims':>7} {'uncited':>8} {'domains':>8} {'cited':>6}")
    print("-" * 86)
    for c in summary.cases:
        print(
            f"{c.question[:46]:<48} {c.n_sources:>4} {c.n_claims:>7} "
            f"{c.uncited_claims:>8} {c.unique_domains:>8} {str(c.has_citation):>6}"
        )
    print("-" * 86)
    if summary.passed:
        print("\nPASS — all quality thresholds met.")
        return 0
    print("\nFAIL:")
    for f in summary.failures:
        print(f"  - {f}")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
