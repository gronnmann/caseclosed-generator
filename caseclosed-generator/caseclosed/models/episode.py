from pydantic import BaseModel


class Episode(BaseModel):
    """A chapter/episode of the mystery that players work through sequentially."""

    number: int
    title: str
    objective: str  # The question/task the player must solve to progress
    intro_letter: str  # Narrative text from the detective introducing this episode
    evidence_ids: list[str] = []  # IDs of evidence items available in this episode
    unlock_condition: str | None = None  # What must be solved to reach this episode
    hints: list[str] = []  # 2-3 hints to help players if stuck
    previous_episode_solution: str = ""  # Solution to the PREVIOUS episode (empty for ep 1)
