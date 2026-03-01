"""Generate episode structure with objectives."""

from pydantic import BaseModel

from caseclosed.llm.client import generate_structured
from caseclosed.llm.prompts import episodes_prompt
from caseclosed.models.case import Case
from caseclosed.models.episode import Episode


class EpisodesResponse(BaseModel):
    episodes: list[Episode]


def generate_episodes(case: Case) -> list[Episode]:
    """Generate the episode structure for the mystery."""
    messages = episodes_prompt(case)
    response = generate_structured(EpisodesResponse, messages)
    return response.episodes
