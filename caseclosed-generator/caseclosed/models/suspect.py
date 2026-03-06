from pydantic import BaseModel, Field


HANDWRITING_FONTS = [
    "Nanum Pen Script",
    "Just Another Hand",
    "Caveat",
    "Gochi Hand",
    "Neucha",
    "Shadows Into Light Two",
    "Homemade Apple",
]

class SuspectRelationship(BaseModel):
    person: str
    description: str


class Suspect(BaseModel):
    name: str
    age: int
    occupation: str
    relationship_to_victim: str
    motive: str
    alibi: str
    alibi_truth: str

    secrets: list[str] = Field(default_factory=list)
    personality_traits: list[str] = Field(default_factory=list)
    relationships: list[SuspectRelationship] = Field(default_factory=list)

    is_killer: bool = False

    handwriting_font: str | None = None
    portrait_prompt: str | None = None
    portrait_filename: str | None = None

    height_cm: int | None = None
    weight_kg: int | None = None
    eye_color: str | None = None
    hair_color: str | None = None
    shoe_size_eu: float | None = None

    phone_number: str | None = None
    address: str | None = None
    nationality: str | None = None
    id_number: str | None = None
    date_of_birth: str | None = None
    employer: str | None = None

    vehicle_plates: list[str] = Field(default_factory=list)

    prior_arrests: bool = False
    prior_convictions: bool = False