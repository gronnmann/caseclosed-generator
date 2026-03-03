"""Generate actual evidence content for a single plan item."""

from caseclosed.llm.client import generate_image, generate_structured
from caseclosed.models.case import Case
from caseclosed.models.evidence import (
    EvidenceItem,
    EvidencePlanItem,
    Email,
    FacebookPost,
    HandwrittenNote,
    ImageEvidence,
    InstagramPost,
    InterrogationReport,
    Invoice,
    Letter,
    PersonOfInterestForm,
    PhoneLog,
    RawText,
    Receipt,
    SmsLog,
)
from caseclosed.llm.prompts import evidence_content_prompt
from caseclosed.persistence import images_dir, save_image

# Map plan type to the Pydantic model for structured output
_TYPE_MAP: dict[str, type] = {
    "interrogation": InterrogationReport,
    "poi_form": PersonOfInterestForm,
    "letter": Letter,
    "image": ImageEvidence,
    "raw_text": RawText,
    "phone_log": PhoneLog,
    "sms_log": SmsLog,
    "email": Email,
    "handwritten_note": HandwrittenNote,
    "instagram_post": InstagramPost,
    "facebook_post": FacebookPost,
    "invoice": Invoice,
    "receipt": Receipt,
}


def generate_evidence_content(
    case: Case,
    plan_item: EvidencePlanItem,
    already_generated_ids: list[str] | None = None,
    *,
    edit_instructions: str | None = None,
    current_evidence: EvidenceItem | None = None,
) -> EvidenceItem:
    """Generate the full content for a single evidence item."""
    already_generated_ids = already_generated_ids or []

    model_class = _TYPE_MAP.get(plan_item.type)
    if model_class is None:
        raise ValueError(f"Unknown evidence type: {plan_item.type}")

    messages = evidence_content_prompt(case, plan_item, already_generated_ids)
    if current_evidence and edit_instructions:
        messages.extend([
            {"role": "assistant", "content": current_evidence.model_dump_json(indent=2)},
            {"role": "user", "content": f"Edit the above output according to these instructions:\n\n{edit_instructions}"},
        ])
    evidence: EvidenceItem = generate_structured(model_class, messages)
    return evidence


def generate_evidence_image(
    case: Case,
    evidence: ImageEvidence,
) -> str:
    """Generate the actual image for an ImageEvidence item. Returns the filename."""
    reference_images = _collect_reference_images(case, evidence)
    image_data = generate_image(evidence.image_prompt, reference_images=reference_images or None)
    filename = f"{evidence.plan_id}.png"
    save_image(case.id, filename, image_data)
    return filename


def edit_evidence_image(
    case: Case,
    evidence: ImageEvidence,
    edit_instructions: str,
) -> str:
    """Edit an existing generated image with instructions. Returns the filename."""
    from caseclosed.llm.client import edit_image

    img_path = images_dir(case.id) / f"{evidence.plan_id}.png"
    original_bytes = img_path.read_bytes()
    edited_data = edit_image(original_bytes, edit_instructions)
    filename = f"{evidence.plan_id}.png"
    save_image(case.id, filename, edited_data)
    return filename


def _collect_reference_images(case: Case, evidence: ImageEvidence) -> list[bytes]:
    """Load portrait images for suspects/victim mentioned in this evidence item."""
    refs: list[bytes] = []
    img_dir = images_dir(case.id)

    # Check suspects
    for suspect in case.suspects:
        if not suspect.portrait_filename:
            continue
        name_lower = suspect.name.lower()
        prompt_lower = evidence.image_prompt.lower()
        caption_lower = evidence.caption.lower()
        if name_lower in prompt_lower or name_lower in caption_lower:
            portrait_path = img_dir / suspect.portrait_filename
            if portrait_path.exists():
                refs.append(portrait_path.read_bytes())

    # Check victim
    if case.truth and case.truth.victim.portrait_filename:
        victim = case.truth.victim
        name_lower = victim.name.lower()
        prompt_lower = evidence.image_prompt.lower()
        caption_lower = evidence.caption.lower()
        if name_lower in prompt_lower or name_lower in caption_lower:
            portrait_path = img_dir / victim.portrait_filename
            if portrait_path.exists():
                refs.append(portrait_path.read_bytes())

    return refs
