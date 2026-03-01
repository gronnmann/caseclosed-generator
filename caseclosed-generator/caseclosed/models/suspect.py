from pydantic import BaseModel


class Suspect(BaseModel):
    """A person of interest in the case."""

    name: str
    age: int
    occupation: str
    relationship_to_victim: str
    motive: str  # Apparent motive (may be a red herring for innocent suspects)
    alibi: str  # What they claim
    alibi_truth: str  # What actually happened (hidden from player)
    secrets: list[str] = []
    is_killer: bool = False
    personality_traits: list[str] = []

    # Portrait image (generated after suspect creation)
    portrait_prompt: str | None = None  # Detailed prompt for AI portrait generation
    portrait_filename: str | None = None  # e.g. "portrait-ingrid.png"

    # Physical description (for POI forms)
    height_cm: int | None = None
    weight_kg: int | None = None
    eye_color: str | None = None
    hair_color: str | None = None
    shoe_size_eu: float | None = None

    # Additional info for POI forms
    phone_number: str | None = None
    address: str | None = None
    nationality: str | None = None
    id_number: str | None = None
    date_of_birth: str | None = None
    employer: str | None = None
    vehicle_plates: list[str] = []
    prior_arrests: bool = False
    prior_convictions: bool = False
