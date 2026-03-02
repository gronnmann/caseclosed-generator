from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from caseclosed.models.episode import Episode
from caseclosed.models.evidence import EvidenceItem, EvidencePlanItem
from caseclosed.models.suspect import Suspect


class GenerationPhase(StrEnum):
    PREMISE = "premise"
    TRUTH = "truth"
    SUSPECTS = "suspects"
    SUSPECT_PORTRAITS = "suspect_portraits"
    EPISODES = "episodes"
    EVIDENCE_PLAN = "evidence_plan"
    EVIDENCE_CONTENT = "evidence_content"
    IMAGES = "images"
    COMPLETE = "complete"


class GenerationState(BaseModel):
    """Tracks where we are in the generation pipeline — enables resume."""

    phase: GenerationPhase = GenerationPhase.PREMISE
    current_step_detail: str | None = None  # e.g. "evidence:3/7"


class TimelineEvent(BaseModel):
    time: str  # e.g. "21:30" or "afternoon"
    description: str
    actor: str | None = None  # Who is involved


class Victim(BaseModel):
    name: str
    age: int
    occupation: str
    cause_of_death: str
    description: str | None = None
    portrait_prompt: str | None = None
    portrait_filename: str | None = None


class CaseTruth(BaseModel):
    """The hidden ground truth of the mystery — only the 'director' sees this."""

    victim: Victim
    killer_name: str  # References a Suspect.name
    method: str  # How the murder was committed
    weapon: str | None = None
    motive: str  # Why the killer did it
    timeline: list[TimelineEvent] = []
    crime_scene: str  # Location description
    key_evidence_summary: str | None = None  # Brief note on what proves the killer


class CasePersonnel(BaseModel):
    """Recurring named characters that stay consistent across all evidence."""

    lead_detective: str  # Oversees the case, writes intro/solution letters
    interrogating_detective: str  # Conducts all interrogations
    coroner: str  # Medical examiner who writes autopsy/lab reports
    forensic_technician: str = ""  # Crime scene technician (optional)


class CaseMetadata(BaseModel):
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    model_used: str | None = None
    image_model_used: str | None = None
    difficulty: str | None = None


class Case(BaseModel):
    """The central case object — grows as generation progresses.

    Serialized to case.json after every pipeline step.
    """

    id: str
    title: str | None = None
    premise: str
    language: str = "en"

    generation_state: GenerationState = Field(default_factory=GenerationState)
    metadata: CaseMetadata = Field(default_factory=CaseMetadata)

    # Populated during generation (in order)
    truth: CaseTruth | None = None
    personnel: CasePersonnel | None = None
    suspects: list[Suspect] = []
    episodes: list[Episode] = []
    evidence_plan: list[EvidencePlanItem] = []
    evidence: list[EvidenceItem] = []
