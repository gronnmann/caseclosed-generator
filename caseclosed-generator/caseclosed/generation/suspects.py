"""Generate suspects based on the established truth."""

from pydantic import BaseModel

from caseclosed.llm.client import generate_structured
from caseclosed.llm.prompts import suspects_prompt
from caseclosed.models.case import Case
from caseclosed.models.suspect import Suspect


class SuspectsResponse(BaseModel):
    suspects: list[Suspect]


def generate_suspects(case: Case) -> list[Suspect]:
    """Generate suspects for the mystery."""
    messages = suspects_prompt(case)
    response = generate_structured(SuspectsResponse, messages)
    return response.suspects


def generate_suspect_portrait_prompt(suspect: Suspect, language: str) -> str:
    """Generate a detailed portrait prompt for a suspect's photo."""
    from caseclosed.llm.client import generate_text

    messages = [
        {
            "role": "system",
            "content": (
                "You are an expert at writing detailed image generation prompts for "
                "realistic portrait photographs. Generate ONLY the prompt text, nothing else."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Generate a detailed AI image generation prompt for a realistic portrait "
                f"photo of this person (for use on an official police Person of Interest form):\n\n"
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
            ),
        },
    ]
    return generate_text(messages)
