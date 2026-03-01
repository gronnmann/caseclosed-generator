"""Generate actual evidence content for a single plan item."""

from caseclosed.llm.client import generate_image, generate_structured
from caseclosed.models.case import Case
from caseclosed.models.evidence import (
    EvidenceItem,
    EvidencePlanItem,
    ImageEvidence,
    InterrogationReport,
    Letter,
    PersonOfInterestForm,
    RawText,
)
from caseclosed.llm.prompts import evidence_content_prompt
from caseclosed.persistence import save_image

# Map plan type to the Pydantic model for structured output
_TYPE_MAP: dict[str, type] = {
    "interrogation": InterrogationReport,
    "poi_form": PersonOfInterestForm,
    "letter": Letter,
    "image": ImageEvidence,
    "raw_text": RawText,
}


def generate_evidence_content(
    case: Case,
    plan_item: EvidencePlanItem,
    already_generated_ids: list[str] | None = None,
) -> EvidenceItem:
    """Generate the full content for a single evidence item."""
    already_generated_ids = already_generated_ids or []

    model_class = _TYPE_MAP.get(plan_item.type)
    if model_class is None:
        raise ValueError(f"Unknown evidence type: {plan_item.type}")

    messages = evidence_content_prompt(case, plan_item, already_generated_ids)
    evidence: EvidenceItem = generate_structured(model_class, messages)
    return evidence


def generate_evidence_image(
    case: Case,
    evidence: ImageEvidence,
) -> str:
    """Generate the actual image for an ImageEvidence item. Returns the filename."""
    image_data = generate_image(evidence.image_prompt)
    filename = f"{evidence.plan_id}.png"
    save_image(case.id, filename, image_data)
    return filename
