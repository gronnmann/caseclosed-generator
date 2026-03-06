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
    edit_instructions: str | None = None,
    current_plan: list[EvidencePlanItem] | None = None,
) -> list[EvidencePlanItem]:
    """Plan all evidence items before generating their content."""
    messages = evidence_plan_prompt(case)
    if current_plan and edit_instructions:
        wrapper = EvidencePlanResponse(evidence_plan=current_plan)
        messages.extend([
            {"role": "assistant", "content": wrapper.model_dump_json(indent=2)},
            {"role": "user", "content": f"Edit the above output according to these instructions:\n\n{edit_instructions}"},
        ])
    response = generate_structured(EvidencePlanResponse, messages)
    return response.evidence_plan
