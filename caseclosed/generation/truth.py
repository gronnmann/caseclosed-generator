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
    edit_instructions: str | None = None,
    current_truth: CaseTruth | None = None,
) -> CaseTruth:
    """Generate the hidden ground truth for a mystery."""
    messages = truth_prompt(
        premise=premise,
        language=language,
        suspect_count=suspect_count,
        episode_count=episode_count,
        difficulty=difficulty,
    )
    if current_truth and edit_instructions:
        messages.extend([
            {"role": "assistant", "content": current_truth.model_dump_json(indent=2)},
            {"role": "user", "content": f"Edit the above output according to these instructions:\n\n{edit_instructions}"},
        ])
    return generate_structured(CaseTruth, messages)


def generate_personnel(case: Case) -> CasePersonnel:
    """Generate recurring case personnel names."""
    messages = personnel_prompt(case)
    return generate_structured(CasePersonnel, messages)
