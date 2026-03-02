"""Generate suspects based on the established truth."""

from pydantic import BaseModel

from caseclosed.llm.client import generate_structured
from caseclosed.llm.prompts import suspects_prompt
from caseclosed.models.case import Case
from caseclosed.models.suspect import Suspect


class SuspectsResponse(BaseModel):
    suspects: list[Suspect]


def generate_suspects(
    case: Case,
    *,
    edit_instructions: str | None = None,
    current_suspects: list[Suspect] | None = None,
) -> list[Suspect]:
    """Generate suspects for the mystery."""
    messages = suspects_prompt(case)
    if current_suspects and edit_instructions:
        wrapper = SuspectsResponse(suspects=current_suspects)
        messages.extend([
            {"role": "assistant", "content": wrapper.model_dump_json(indent=2)},
            {"role": "user", "content": f"Edit the above output according to these instructions:\n\n{edit_instructions}"},
        ])
    response = generate_structured(SuspectsResponse, messages)
    # Strip portrait fields — the LLM may hallucinate values for these,
    # but they should only be set by actual image generation.
    for s in response.suspects:
        s.portrait_prompt = None
        s.portrait_filename = None
    return response.suspects


def generate_suspect_portrait_prompt(suspect: Suspect, language: str) -> str:
    """Generate a detailed portrait prompt for a suspect's photo."""
    from caseclosed.llm.client import generate_text

    messages = [
        {
            "role": "system",
            "content": (
                "You are an expert at writing detailed image generation prompts for "
                "realistic portrait photographs. Generate ONLY the prompt text, nothing else. "
                "NEVER include any text overlays, watermarks, badges, police markings, mugshot "
                "placards, or identification text in the image."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Generate a detailed AI image generation prompt for a realistic portrait "
                f"photo of this person:\n\n"
                f"Name: {suspect.name}\n"
                f"Age: {suspect.age}\n"
                f"Occupation: {suspect.occupation}\n"
                f"Height: {suspect.height_cm or 'unknown'} cm\n"
                f"Weight: {suspect.weight_kg or 'unknown'} kg\n"
                f"Eye color: {suspect.eye_color or 'unknown'}\n"
                f"Hair color: {suspect.hair_color or 'unknown'}\n"
                f"Personality: {', '.join(suspect.personality_traits) if suspect.personality_traits else 'unknown'}\n\n"
                f"The photo should look like an official ID/mugshot-style portrait: "
                f"head-and-shoulders, neutral background, front-facing, good lighting. "
                f"The person should look like a real human being with natural features."
                f"Do NOT include any text or ID overlays."
            ),
        },
    ]
    return generate_text(messages)


def generate_victim_portrait_prompt(victim_name: str, victim_age: int, victim_occupation: str, victim_description: str | None, language: str) -> str:
    """Generate a detailed portrait prompt for the deceased victim."""
    from caseclosed.llm.client import generate_text

    messages = [
        {
            "role": "system",
            "content": (
                "You are an expert at writing detailed image generation prompts for "
                "realistic portrait photographs. Generate ONLY the prompt text, nothing else. "
                "NEVER include any text overlays, watermarks, badges, police markings, or "
                "identification text in the image."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Generate a detailed AI image generation prompt for a realistic portrait "
                f"photo of this person (now deceased, but the photo should show them alive):\n\n"
                f"Name: {victim_name}\n"
                f"Age: {victim_age}\n"
                f"Occupation: {victim_occupation}\n"
                f"Description: {victim_description or 'not provided'}\n\n"
                f"The photo should be a clean head-and-shoulders portrait: "
                f"neutral background, front-facing, good lighting. "
                f"The person should look like a real, living human being with natural features. "
                f"Do NOT include any text, police elements, or ID overlays. "
                f"Do NOT depict them as dead or injured."
            ),
        },
    ]
    return generate_text(messages)
