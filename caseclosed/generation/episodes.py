"""Generate episode structure with objectives."""

from pydantic import BaseModel

from caseclosed.llm.client import generate_structured
from caseclosed.llm.prompts import episodes_prompt
from caseclosed.models.case import Case
from caseclosed.models.episode import Episode


class EpisodesResponse(BaseModel):
    episodes: list[Episode]


def generate_episodes(
    case: Case,
    *,
    edit_history: list[tuple[str, str]] | None = None,
) -> list[Episode]:
    """Generate the episode structure for the mystery.

    edit_history: list of (assistant_json, user_edit_instruction) tuples
    representing the full conversation history of edits.
    """
    messages = episodes_prompt(case)
    if edit_history:
        for assistant_json, user_edit in edit_history:
            messages.append({"role": "assistant", "content": assistant_json})
            messages.append({"role": "user", "content": f"Edit the above output according to these instructions:\n\n{user_edit}"})
    response = generate_structured(EpisodesResponse, messages)
    return response.episodes
