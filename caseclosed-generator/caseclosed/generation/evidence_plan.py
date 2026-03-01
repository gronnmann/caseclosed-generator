"""Plan the evidence graph — what evidence exists and which episodes use it."""

from pydantic import BaseModel

from caseclosed.llm.client import generate_structured
from caseclosed.llm.prompts import evidence_plan_prompt
from caseclosed.models.case import Case
from caseclosed.models.evidence import EvidencePlanItem


class EvidencePlanResponse(BaseModel):
    evidence_plan: list[EvidencePlanItem]


def generate_evidence_plan(case: Case) -> list[EvidencePlanItem]:
    """Plan all evidence items before generating their content."""
    messages = evidence_plan_prompt(case)
    response = generate_structured(EvidencePlanResponse, messages)
    return response.evidence_plan
