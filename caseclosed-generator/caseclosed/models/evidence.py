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
        "interrogation", "poi_form", "letter", "image", "raw_text",
        "phone_log", "sms_log", "email",
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
    middle_name: str = ""
    last_name: str
    nickname: str = ""
    date_of_birth: str
    country_of_birth: str = ""
    nationality: str = ""
    id_number: str = ""
    occupation: str = ""

    # Contact info
    phone_country_code: str = ""
    phone_number: str = ""
    street_address: str = ""
    city: str = ""
    postal_code: str = ""
    country: str = ""

    # Physical description
    height_cm: str = ""
    weight_kg: str = ""
    eye_color: str = ""
    hair_color: str = ""
    shoe_size_eu: str = ""

    # Additional
    vehicle_plates: str = ""
    employer: str = ""
    prior_arrests: bool = False
    prior_convictions: bool = False
    signature: str = ""


class Letter(BaseModel):
    """A letter — introduction, solution, or narrative."""

    type: Literal["letter"] = "letter"
    plan_id: str
    sender: str
    recipient: str
    date: str | None = None
    body_text: str
    letter_type: Literal["intro", "solution", "narrative"]
    text_typst: str = ""  # Typst-formatted body (two newlines = newline, *bold*, _italic_)


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
    text_html: str = ""  # HTML-formatted version of the content
    text_latex: str = ""  # LaTeX-formatted version of the content
    text_typst: str = ""  # Typst-formatted version of the content


class PhoneLogEntry(BaseModel):
    timestamp: str  # e.g. "2024-03-15 14:32"
    direction: Literal["incoming", "outgoing", "missed"]
    other_party: str  # Name or phone number
    duration: str = ""  # e.g. "2m 34s", empty for missed


class PhoneLog(BaseModel):
    """A phone call log for a person."""

    type: Literal["phone_log"] = "phone_log"
    plan_id: str
    owner_name: str
    phone_number: str
    entries: list[PhoneLogEntry]


class SmsMessage(BaseModel):
    timestamp: str  # e.g. "2024-03-15 14:32"
    direction: Literal["incoming", "outgoing"]
    other_party: str  # Name or phone number
    text: str


class SmsLog(BaseModel):
    """An SMS / text message log for a person."""

    type: Literal["sms_log"] = "sms_log"
    plan_id: str
    owner_name: str
    phone_number: str
    messages: list[SmsMessage]


class Email(BaseModel):
    """An email message."""

    type: Literal["email"] = "email"
    plan_id: str
    from_address: str
    to_address: str
    cc: str = ""
    subject: str
    date: str
    body_text: str
    text_typst: str = ""
    text_html: str = ""


# Discriminated union of all evidence content types
EvidenceItem = Annotated[
    InterrogationReport
    | PersonOfInterestForm
    | Letter
    | ImageEvidence
    | RawText
    | PhoneLog
    | SmsLog
    | Email,
    Field(discriminator="type"),
]
