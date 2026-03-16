"""Generate the core truth of the mystery and case personnel."""

from caseclosed.llm.client import generate_structured
from caseclosed.llm.prompts import personnel_prompt, truth_prompt
from caseclosed.models.case import Case, CasePersonnel, CaseTruth


def generate_truth(
    premise: str,
    language: str,
    suspect_count: int | None = None,
    episode_count: int | None = None,
    difficulty: str | None = None,
    *,
    edit_history: list[tuple[str, str]] | None = None,
) -> CaseTruth:
    """Generate the hidden ground truth for a mystery.

    edit_history: list of (assistant_json, user_edit_instruction) tuples
    representing the full conversation history of edits.
    """
    messages = truth_prompt(
        premise=premise,
        language=language,
        suspect_count=suspect_count,
        episode_count=episode_count,
        difficulty=difficulty,
    )
    if edit_history:
        for assistant_json, user_edit in edit_history:
            messages.append({"role": "assistant", "content": assistant_json})
            messages.append({"role": "user", "content": f"Edit the above output according to these instructions:\n\n{user_edit}"})
    return generate_structured(CaseTruth, messages)


def generate_personnel(case: Case) -> CasePersonnel:
    """Generate recurring case personnel names."""
    messages = personnel_prompt(case)
    return generate_structured(CasePersonnel, messages)
