"""Generate the core truth of the mystery."""

from caseclosed.llm.client import generate_structured
from caseclosed.llm.prompts import truth_prompt
from caseclosed.models.case import CaseTruth


def generate_truth(
    premise: str,
    language: str,
    suspect_count: int | None = None,
    episode_count: int | None = None,
    difficulty: str | None = None,
) -> CaseTruth:
    """Generate the hidden ground truth for a mystery."""
    messages = truth_prompt(
        premise=premise,
        language=language,
        suspect_count=suspect_count,
        episode_count=episode_count,
        difficulty=difficulty,
    )
    return generate_structured(CaseTruth, messages)
