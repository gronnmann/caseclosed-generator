from typing import Annotated, Literal

from pydantic import BaseModel, Field


# --- Evidence Plan (designed before content generation) ---


class EvidencePlanItem(BaseModel):
    """A planned piece of evidence — designed before actual content is generated.

    This forms the 'evidence graph' that maps what evidence exists,
    which episodes introduce it, and where it gets reused.
    """

    id: str
    type: Literal[
        "interrogation", "poi_form", "letter", "image", "raw_text"
    ]
    title: str
    brief_description: str  # What this evidence contains/reveals
    introduced_in_episode: int  # First appears in this episode
    also_used_in_episodes: list[int] = []  # Cross-episode reuse
    suspect_name: str | None = None  # If tied to a specific suspect
    clue_reveals: str  # What the player learns from this evidence


# --- Evidence Content Types (discriminated union) ---


class DialogueLine(BaseModel):
    speaker: str
    text: str


class InterrogationReport(BaseModel):
    """A police interrogation transcript."""

    type: Literal["interrogation"] = "interrogation"
    plan_id: str  # Links to EvidencePlanItem.id
    suspect_name: str
    case_number: str
    date: str
    interviewer: str
    transcript: list[DialogueLine]


class PersonOfInterestForm(BaseModel):
    """A structured form with suspect personal details."""

    type: Literal["poi_form"] = "poi_form"
    plan_id: str

    # Personal info
    name: str
    middle_name: str | None = None
    last_name: str
    nickname: str | None = None
    date_of_birth: str
    country_of_birth: str | None = None
    nationality: str | None = None
    id_number: str | None = None
    occupation: str | None = None

    # Contact info
    phone_country_code: str | None = None
    phone_number: str | None = None
    street_address: str | None = None
    city: str | None = None
    postal_code: str | None = None
    country: str | None = None

    # Physical description
    height_cm: int | None = None
    weight_kg: int | None = None
    eye_color: str | None = None
    hair_color: str | None = None
    shoe_size_eu: str | None = None

    # Additional
    vehicle_plates: str | None = None
    employer: str | None = None
    prior_arrests: bool = False
    prior_convictions: bool = False
    signature: str | None = None


class Letter(BaseModel):
    """A letter — introduction, solution, or narrative."""

    type: Literal["letter"] = "letter"
    plan_id: str
    sender: str
    recipient: str
    date: str | None = None
    body_text: str
    letter_type: Literal["intro", "solution", "narrative"]


class ImageEvidence(BaseModel):
    """An image evidence item — stores the AI generation prompt and metadata."""

    type: Literal["image"] = "image"
    plan_id: str
    image_prompt: str  # Detailed prompt for AI image generation
    caption: str
    location_context: str | None = None
    image_filename: str | None = None  # Set after generation, e.g. "crime-scene.png"


class RawText(BaseModel):
    """Free-form text evidence — newspaper articles, lab reports, notes, etc."""

    type: Literal["raw_text"] = "raw_text"
    plan_id: str
    content: str
    format_hint: Literal[
        "newspaper_article",
        "lab_report",
        "autopsy_report",
        "drug_guide",
        "phone_message",
        "note",
        "other",
    ]


# Discriminated union of all evidence content types
EvidenceItem = Annotated[
    InterrogationReport
    | PersonOfInterestForm
    | Letter
    | ImageEvidence
    | RawText,
    Field(discriminator="type"),
]
