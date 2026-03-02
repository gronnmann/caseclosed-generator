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
    edit_instructions: str | None = None,
    current_episodes: list[Episode] | None = None,
) -> list[Episode]:
    """Generate the episode structure for the mystery."""
    messages = episodes_prompt(case)
    if current_episodes and edit_instructions:
        wrapper = EpisodesResponse(episodes=current_episodes)
        messages.extend([
            {"role": "assistant", "content": wrapper.model_dump_json(indent=2)},
            {"role": "user", "content": f"Edit the above output according to these instructions:\n\n{edit_instructions}"},
        ])
    response = generate_structured(EpisodesResponse, messages)
    return response.episodes
