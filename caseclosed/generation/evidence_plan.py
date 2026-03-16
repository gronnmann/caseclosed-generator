"""Plan the evidence graph — what evidence exists and which episodes use it."""

from pydantic import BaseModel

from caseclosed.llm.client import generate_structured
from caseclosed.llm.prompts import evidence_plan_prompt
from caseclosed.models.case import Case
from caseclosed.models.evidence import EvidencePlanItem


class EvidencePlanResponse(BaseModel):
    evidence_plan: list[EvidencePlanItem]


def generate_evidence_plan(
    case: Case,
    *,
    edit_history: list[tuple[str, str]] | None = None,
) -> list[EvidencePlanItem]:
    """Plan all evidence items before generating their content.

    edit_history: list of (assistant_json, user_edit_instruction) tuples
    representing the full conversation history of edits.
    """
    messages = evidence_plan_prompt(case)
    if edit_history:
        for assistant_json, user_edit in edit_history:
            messages.append({"role": "assistant", "content": assistant_json})
            messages.append({"role": "user", "content": f"Edit the above output according to these instructions:\n\n{user_edit}"})
    response = generate_structured(EvidencePlanResponse, messages)
    return response.evidence_plan
