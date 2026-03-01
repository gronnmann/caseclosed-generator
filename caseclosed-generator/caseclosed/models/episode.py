from pydantic import BaseModel


class Episode(BaseModel):
    """A chapter/episode of the mystery that players work through sequentially."""

    number: int
    title: str
    objective: str  # The question/task the player must solve to progress
    intro_letter: str  # Narrative text from the detective introducing this episode
    evidence_ids: list[str] = []  # IDs of evidence items available in this episode
    unlock_condition: str | None = None  # What must be solved to reach this episode
