"""Prompt templates for each generation step.

Each function returns a list of message dicts ready for the OpenAI API.
The prompts instruct the LLM to generate content in the target language
and maintain consistency with previously established facts.
"""

from caseclosed.models.case import Case, CaseTruth
from caseclosed.models.evidence import EvidencePlanItem


SYSTEM_PROMPT = """\
You are a Mystery Architect — an expert at designing intricate, fair, and solvable \
murder mystery games in the style of "Case Closed" detective experiences.

You work with a "logic-first" approach: the truth is established first, then layers \
of deception, red herrings, and conflicting alibis are built on top. Every piece of \
evidence must be internally consistent with the established timeline and facts.

IMPORTANT: Generate ALL content in {language}. Every name, dialogue, document, and \
description must be in {language}.

FORMATTING RULES:
- NEVER use em dashes (\u2014), en dashes (\u2013), or other special Unicode dashes. \
Use commas (if possible) or ewrite the sentence instead.
- NEVER use curly/smart quotes (\u201c \u201d \u2018 \u2019). Use straight quotes (" ') only.
- Avoid other fancy Unicode characters. Stick to basic ASCII punctuation.\
"""


def _system(language: str) -> dict[str, str]:
    return {"role": "system", "content": SYSTEM_PROMPT.format(language=language)}


def _user(content: str) -> dict[str, str]:
    return {"role": "user", "content": content}


def truth_prompt(
    premise: str,
    language: str,
    suspect_count: int | None = None,
    episode_count: int | None = None,
    difficulty: str | None = None,
) -> list[dict[str, str]]:
    """Prompt to generate the core truth of the mystery."""
    parts = [
        f"Create the hidden truth for a murder mystery with this premise:\n\n\"{premise}\"",
        "\nDesign the core facts:",
        "- Who is the victim? (name, age, occupation, brief description)",
        "- Who is the killer? (name only — they'll be fleshed out as a suspect later)",
        "- How was the murder committed? (method, weapon if applicable)",
        "- Why? (the real motive)",
        "- Where? (crime scene description)",
        "- Timeline of key events leading up to and including the murder",
        "- What key evidence ultimately proves the killer's guilt?",
    ]
    if suspect_count:
        parts.append(f"\nThe mystery should accommodate roughly {suspect_count} suspects.")
    if episode_count:
        parts.append(f"Plan for approximately {episode_count} episodes/chapters.")
    if difficulty:
        parts.append(f"Target difficulty: {difficulty}")

    return [_system(language), _user("\n".join(parts))]


def suspects_prompt(
    case: Case,
) -> list[dict[str, str]]:
    """Prompt to generate suspects based on the established truth."""
    assert case.truth is not None
    truth = case.truth

    content = f"""\
Based on this established truth, generate the suspects for the mystery.

ESTABLISHED TRUTH:
- Victim: {truth.victim.name}, {truth.victim.age}, {truth.victim.occupation}
- Killer: {truth.killer_name}
- Method: {truth.method}
- Motive: {truth.motive}
- Crime scene: {truth.crime_scene}
- Timeline: {_format_timeline(truth)}

Generate suspects including the killer. For each suspect:
- Give them a believable apparent motive (red herring for innocent ones)
- Create a claimed alibi AND the truth of what they were actually doing
- Add personal secrets that create suspicion but may be unrelated to the murder
- Include full personal details (physical description, contact info, etc.) for their POI forms
- Personality traits that come through in interrogation

The killer ({truth.killer_name}) must have a plausible-sounding alibi that can be \
disproven by careful examination of the evidence.\
"""
    return [_system(case.language), _user(content)]


def episodes_prompt(
    case: Case,
) -> list[dict[str, str]]:
    """Prompt to generate episode structure with objectives."""
    assert case.truth is not None
    truth = case.truth

    suspect_names = [s.name for s in case.suspects]
    content = f"""\
Design the episode structure for this mystery.

ESTABLISHED TRUTH:
- Victim: {truth.victim.name}
- Killer: {truth.killer_name}
- Method: {truth.method}
- Crime scene: {truth.crime_scene}
- Timeline: {_format_timeline(truth)}

SUSPECTS: {', '.join(suspect_names)}

Create a sequence of episodes. Each episode:
- Has a title and a specific objective (a question the player must answer to progress)
- Includes an intro_letter — narrative text from the lead investigator setting the scene
- The first episode should introduce the case broadly
- Each subsequent episode focuses on a specific aspect (alibis, forensics, connections, etc.)
- The final episode's objective should lead the player to identify the killer
- Objectives should be concrete: "Who was lying about being at the restaurant?" not "Find clues"

The breadcrumb trail should make information from early episodes become meaningful later. \
Players should feel like a genius when they connect the dots.\
"""
    return [_system(case.language), _user(content)]


def evidence_plan_prompt(
    case: Case,
) -> list[dict[str, str]]:
    """Prompt to plan the entire evidence graph before generating content."""
    assert case.truth is not None
    truth = case.truth

    episodes_summary = "\n".join(
        f"  Episode {e.number}: \"{e.title}\" — Objective: {e.objective}"
        for e in case.episodes
    )
    suspects_summary = "\n".join(
        f"  - {s.name}: {s.occupation}, motive: {s.motive}"
        for s in case.suspects
    )

    content = f"""\
Plan ALL evidence items for this mystery. Do NOT generate the actual content yet — \
just plan what each piece of evidence is, what it reveals, and which episodes use it.

TRUTH:
- Victim: {truth.victim.name} ({truth.victim.cause_of_death})
- Killer: {truth.killer_name}
- Method: {truth.method}, Weapon: {truth.weapon or 'N/A'}
- Motive: {truth.motive}
- Timeline: {_format_timeline(truth)}

SUSPECTS:
{suspects_summary}

EPISODES:
{episodes_summary}

For each evidence item, specify:
- id: a short slug (e.g., "interrogation-ingrid", "newspaper-article", "crime-scene-photo")
- type: one of "interrogation", "poi_form", "letter", "image", "raw_text"
- title: display title
- brief_description: what this evidence contains
- introduced_in_episode: which episode first presents this evidence
- also_used_in_episodes: list of OTHER episode numbers where this evidence is relevant \
(cross-episode reuse — a key detail noticed later)
- suspect_name: if tied to a specific suspect (null otherwise)
- clue_reveals: what the player should learn from this evidence

IMPORTANT:
- Each suspect should have an interrogation report AND a person of interest form
- Include at least one intro letter (episode 1) and one solution letter (final)
- Include at least 2-3 image evidence items (crime scene, key physical evidence, etc.)
- Include supporting documents (newspaper articles, lab reports, phone messages, etc.)
- CROSS-EPISODE REUSE: Some evidence introduced early should contain details that only \
become meaningful in later episodes. This is crucial for the "breadcrumb trail" effect.\
"""
    return [_system(case.language), _user(content)]


def evidence_content_prompt(
    case: Case,
    plan_item: EvidencePlanItem,
    already_generated_ids: list[str],
) -> list[dict[str, str]]:
    """Prompt to generate the actual content for a single evidence item."""
    assert case.truth is not None
    truth = case.truth

    suspect_info = ""
    if plan_item.suspect_name:
        suspect = next(
            (s for s in case.suspects if s.name == plan_item.suspect_name), None
        )
        if suspect:
            suspect_info = f"""
SUSPECT DETAILS (for consistency):
- Name: {suspect.name}, Age: {suspect.age}, Occupation: {suspect.occupation}
- Claimed alibi: {suspect.alibi}
- True alibi: {suspect.alibi_truth}
- Personality: {', '.join(suspect.personality_traits)}
- Secrets: {', '.join(suspect.secrets)}
- Is killer: {suspect.is_killer}
"""

    # Map type to specific instructions
    type_instructions = {
        "interrogation": """\
Generate a realistic police interrogation transcript. Include:
- Opening identification
- Questions about relationship to victim
- Questions about alibi and whereabouts
- Probing questions that create tension
- The suspect's personality should come through in their responses
- If this is the killer, their answers should be plausible but contain subtle inconsistencies""",
        "poi_form": """\
Generate a filled-out Person of Interest form with all personal details. \
Use the suspect's established physical description and personal information.""",
        "letter": """\
Generate a letter. Match the tone to the letter_type:
- "intro": Professional investigator tone, setting up the episode's focus
- "solution": Revealing the truth, explaining how the evidence fits together
- "narrative": In-character from someone involved in the case""",
        "image": _build_image_type_instructions(case, plan_item),
        "raw_text": """\
Generate the document content matching the format_hint. Make it feel authentic:
- newspaper_article: journalistic tone, include byline and date
- lab_report / autopsy_report: clinical, precise, technical
- drug_guide: informational, medical reference style
- phone_message: casual text message format
- note: handwritten feel, possibly informal
- other: match the brief_description style""",
    }

    content = f"""\
Generate the full content for this evidence item.

EVIDENCE PLAN:
- ID: {plan_item.id}
- Type: {plan_item.type}
- Title: {plan_item.title}
- Description: {plan_item.brief_description}
- Clue it reveals: {plan_item.clue_reveals}
- Introduced in episode: {plan_item.introduced_in_episode}
- Also used in episodes: {plan_item.also_used_in_episodes}
{suspect_info}
CASE TRUTH (for consistency — the content must NOT contradict these facts):
- Victim: {truth.victim.name}, died at crime scene: {truth.crime_scene}
- Cause of death: {truth.victim.cause_of_death}
- Killer: {truth.killer_name}
- Method: {truth.method}
- Timeline: {_format_timeline(truth)}

SPECIFIC INSTRUCTIONS FOR THIS TYPE:
{type_instructions.get(plan_item.type, "Generate appropriate content.")}

Generate content in the case language. Make it feel like an authentic document/evidence \
from a real investigation.\
"""
    return [_system(case.language), _user(content)]


def _build_image_type_instructions(case: Case, plan_item: EvidencePlanItem) -> str:
    """Build image-type-specific instructions, including suspect portrait references."""
    base = (
        "Generate a highly detailed image prompt suitable for AI image generation. "
        "Describe the scene, lighting, perspective, important details visible in the image, "
        "and any evidence elements that should be recognizable. Also provide a caption "
        "and context for how this image relates to the case."
    )

    # Find suspects who appear in this evidence and have portrait prompts
    portrait_refs: list[str] = []
    for suspect in case.suspects:
        if not suspect.portrait_prompt:
            continue
        # Include portrait if suspect is directly linked OR mentioned in description
        name_lower = suspect.name.lower()
        linked = (
            (plan_item.suspect_name and plan_item.suspect_name.lower() == name_lower)
            or name_lower in plan_item.brief_description.lower()
            or name_lower in plan_item.title.lower()
        )
        if linked:
            portrait_refs.append(
                f"- {suspect.name}: {suspect.portrait_prompt}\n"
                f"  (Portrait file: {suspect.portrait_filename or 'not yet generated'})"
            )

    if portrait_refs:
        base += (
            "\n\nIMPORTANT — VISUAL CONSISTENCY: The following suspects appear in this image. "
            "Use their portrait descriptions to ensure they look the same as in their "
            "portrait photos:\n"
            + "\n".join(portrait_refs)
        )

    return base


def _format_timeline(truth: CaseTruth) -> str:
    if not truth.timeline:
        return "Not yet established"
    return "; ".join(
        f"{e.time}: {e.description}" + (f" ({e.actor})" if e.actor else "")
        for e in truth.timeline
    )
