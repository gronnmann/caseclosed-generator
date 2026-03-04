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
    suspect_count_str = str(suspect_count) if suspect_count else "4-6"
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
        f"\nSUSPECT SKETCHES (CRITICAL — generate exactly {suspect_count_str} suspect_sketches):",
        "For EACH suspect (including the killer), provide:",
        "- name: their full name",
        "- role: their role relative to the victim (e.g. 'business partner', 'ex-lover', 'neighbor')",
        "- apparent_motive: why they LOOK guilty (this is the red herring for innocent suspects, real motive for the killer)",
        "- secret: a hidden fact that creates suspicion (can be unrelated to the murder for innocents)",
        "- relationship_to_other_suspects: how they connect to at least 1-2 OTHER suspects (rivalries, affairs, debts, alliances)",
        "- is_killer: true for exactly one suspect",
        "\nIMPORTANT — MULTI-SUSPECT DESIGN:",
        "- Every suspect must have a COMPELLING reason to be considered the killer. The story is not about one suspect —",
        "  it's about a web of interconnected people where ANYONE could be guilty.",
        "- Suspects must be connected to EACH OTHER, not just to the victim. Create a network of relationships:",
        "  affairs between suspects, business deals gone wrong, old grudges, shared secrets, financial dependencies.",
        "- The timeline should involve MULTIPLE suspects' actions, not just the killer's.",
        "- At least 2-3 suspects should have suspicious activity in the timeline that could be mistaken for the murder.",
        "- The killer's guilt should only become clear when multiple pieces of evidence are cross-referenced —",
        "  no single piece of evidence should point definitively at the killer.",
    ]
    if episode_count:
        parts.append(f"Plan for approximately {episode_count} episodes/chapters.")
    if difficulty:
        parts.append(f"Target difficulty: {difficulty}")

    return [_system(language), _user("\n".join(parts))]


def personnel_prompt(
    case: Case,
) -> list[dict[str, str]]:
    """Prompt to generate recurring case personnel names."""
    assert case.truth is not None
    truth = case.truth

    content = f"""\
Generate the names of the recurring personnel involved in this investigation.

CASE CONTEXT:
- Victim: {truth.victim.name}
- Crime scene: {truth.crime_scene}
- Setting/language: {case.language}

Generate realistic, consistent names for:
- lead_detective: The senior detective overseeing the entire case (writes intro/solution letters)
- interrogating_detective: The detective who conducts ALL suspect interrogations (must be the same person across every interrogation)
- coroner: The medical examiner / coroner who handles autopsys and lab work
- forensic_technician: The crime scene / forensic technician (optional, can be empty string)

Names must match the cultural setting of the case. These characters will appear \
consistently across all evidence items.\
"""
    return [_system(case.language), _user(content)]


def suspects_prompt(
    case: Case,
) -> list[dict[str, str]]:
    """Prompt to generate suspects based on the established truth."""
    assert case.truth is not None
    truth = case.truth

    sketches_text = "\n".join(
        f"  - {sk.name} ({sk.role}): motive={sk.apparent_motive}, "
        f"secret={sk.secret}, connections={sk.relationship_to_other_suspects}, "
        f"is_killer={sk.is_killer}"
        for sk in truth.suspect_sketches
    ) if truth.suspect_sketches else "(no sketches — generate suspects from scratch)"

    content = f"""\
Based on this established truth, flesh out the suspects for the mystery.

ESTABLISHED TRUTH:
- Victim: {truth.victim.name}, {truth.victim.age}, {truth.victim.occupation}
- Killer: {truth.killer_name}
- Method: {truth.method}
- Motive: {truth.motive}
- Crime scene: {truth.crime_scene}
- Timeline: {_format_timeline(truth)}

SUSPECT SKETCHES (designed with the truth — use these as the foundation):
{sketches_text}

For each suspect sketch above, flesh them out into a full suspect:
- Keep the name, role, apparent motive, and secret from the sketch
- Create a claimed alibi AND the truth of what they were actually doing
- Add personal secrets that create suspicion but may be unrelated to the murder
- Include full personal details (physical description, contact info, etc.) for their POI forms
- Personality traits that come through in interrogation
- "relationships": a dict mapping other suspect names to a short description of their \
relationship and any tensions, grudges, alliances, or shared secrets. Build on the \
relationship_to_other_suspects from the sketches and expand them.

INTER-CHARACTER INTRIGUES (CRITICAL):
- The suspects should NOT exist in isolation. They must have pre-existing relationships, \
conflicts, alliances, and secrets that involve each other.
- Examples: business rivalries, affairs, debts owed, old grudges, shared alibis that \
contradict, one suspect covering for another, blackmail between suspects, family tensions.
- These intrigues create a web of suspicion: suspects will point fingers at each other \
during interrogations, and evidence about one suspect may implicate another.
- Some relationships should be hidden (only revealed through evidence), while others \
are openly known.
- At least one pair of suspects should have a shared secret or conflicting accounts \
of the same event.

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

    suspects_detail = "\n".join(
        f"  - {s.name} (age {s.age}, {s.occupation})\n"
        f"    Relationship to victim: {s.relationship_to_victim}\n"
        f"    Apparent motive: {s.motive}\n"
        f"    Claimed alibi: {s.alibi}\n"
        f"    Truth behind alibi: {s.alibi_truth}\n"
        f"    Secrets: {'; '.join(s.secrets) if s.secrets else 'none'}\n"
        f"    Personality: {', '.join(s.personality_traits) if s.personality_traits else 'N/A'}\n"
        f"    Relationships with other suspects: {'; '.join(f'{k}: {v}' for k, v in s.relationships.items()) if s.relationships else 'none'}\n"
        f"    Is the killer: {s.is_killer}"
        for s in case.suspects
    )

    content = f"""\
Design the episode structure for this mystery.

ESTABLISHED TRUTH:
- Victim: {truth.victim.name}
- Killer: {truth.killer_name}
- Method: {truth.method}
- Crime scene: {truth.crime_scene}
- Timeline: {_format_timeline(truth)}

SUSPECTS (full dossiers — use these to craft a fair, layered investigation):
{suspects_detail}

Create a sequence of episodes. Each episode:
- Has a title and a specific objective (a question the player must answer to progress)
- Includes an intro_letter — narrative text from the lead investigator setting the scene.
The letter asks the person the question, and states that they can go to the next episode \
once they're sure of the answer.
- For episodes after the first, the intro letter should explain what the player just solved in the previous episode,
and which evidence they used. This only applies to answers to the last episode, and not other uncovered things.
- The first episode should introduce the case broadly
- Each subsequent episode focuses on a specific aspect (alibis, forensics, connections, etc.)
- The final episode's objective should lead the player to identify the killer
- Objectives should be concrete: "Who was lying about being at the restaurant?" not "Find clues"

PACING & SUSPECT FUNNEL (CRITICAL):
- The mystery must follow a "wide-to-narrow" suspect funnel:
  * Early episodes: ALL suspects look equally plausible. Present each suspect's apparent \
motive and surface-level alibi so the player sees everyone as a potential killer.
  * Middle episodes: Evidence begins to clear some suspects (their alibis check out, their \
secrets turn out to be unrelated to the murder). But at least 2-3 suspects should still \
seem viable.
  * Late episodes: Contradictions and forensic details narrow it down. Only the final \
episode should give the player enough to definitively identify the killer.
- Do NOT single out or point at specific suspects in early or middle episodes. Keep early and middle episode \
objectives broad rather than naming suspects. They should instead be done to uncover things, intrigues, lies, etc.
- The first episode should always have some interrogation reports and Person of Interest forms. 
There can be mutiple interrogation reports between suspects between different episodes,
and some of them can be introduced later, but we need atleast som early.
- Use the suspects' secrets and lies strategically: innocent suspects' secrets should \
create suspicion early on but be explained away BY EVIDENCE later, keeping the player guessing.
- Do NOT hint at which specific evidence items the player should look at. The player must \
discover connections on their own.
- NEVER write in the letter that someone is innocent or guilty (till the last letter).
This is up for the player to determine.
- Create intrigues between the characters, we find out people have much to lose etc. More people should have a plausible motive, even if they are innocent.
The player should be kept guessing for as long as possible.
- Do NOT give instructions pointing directly at any specific evidence item.
- VERY IMPORTANT: The episodes should feel like a story progressing. The player should \
feel like they're a detective on the case, not just solving isolated puzzles.
- The killer should not receive more narrative weight than other suspects until late episodes.

HINTS:
- Write exactly 2-3 hints for EACH episode, stored in the "hints" field.
- Hints should help stuck players without outright spoiling the answer. They should refer \
to evidence items, first maybe only hinting at what to look, but getting more direct with \
each hint.
- Progress from a gentle nudge (hint 1) to a stronger pointer (hint 3). Follow a structure like:
Hint 1: Indirect — suggests category of evidence
Hint 2: Directs attention to a specific type of document
Hint 3: Points clearly to the contradiction, but does not state the answer

LOOSE EXAMPLES OF EPISODE OBJECTIVES (for inspiration only — do NOT copy these):

Example 1:
- Objective 1: What is Harper not telling us? (uncovers a secret relationship or a secret. does not have to be the killer)
- Objective 2: What is the password to Liam's phone? (uncovers some sketchy messages, but not the full truth)
- Objective 3: Who is lying about their alibi? (narrows down suspects, but can be multiple people)
- Objective 4: What hidden secrets can you uncover? (uncovers key secrets that point towards the killer, but still not definitive)
- Objective 5: Who is the killer? What is your reasoning? (the final reveal, but the player must connect the dots on their own based on all the evidence)

Example 2:
- Objective 1: What was the cause of death?
- Objective 2: Who didnt have a chance to be at all the band's concerts? (removes some suspects)
- Objective 3: Who owns the blog that posted about the victim's affair? (uncovers a key piece of evidence, doesnt have to do with the killer)
- Objective 4: Oscar was found to own the blog. What do the blog posts tell us about the victims wereabouts on the day? (uncovers more of the victims timeline, can be used later)
- Objective 5: Who is the killer? (the final reveal, but the player must connect the dots on their own based on all the evidence)


PREVIOUS EPISODE SOLUTIONS:
- For episode 1, leave "previous_episode_solution" empty (there is no prior episode).
- For every subsequent episode, write a short "previous_episode_solution" that explains \
the answer to the PREVIOUS episode's objective. This is shown to the player when they \
advance, so they understand what they solved before moving on.

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
        f"  - {s.name}: {s.occupation}, motive: {s.motive}, "
        f"relationships: {'; '.join(f'{k}: {v}' for k, v in s.relationships.items()) if s.relationships else 'none'}"
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
- type: one of "interrogation", "poi_form", "letter", "image", "raw_text", "phone_log", "sms_log", "email", "handwritten_note", "instagram_post", "facebook_post", "invoice", "receipt"
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
become meaningful in later episodes. This is crucial for the "breadcrumb trail" effect.

SUSPECT BALANCE (CRITICAL — even distribution of evidence):
- Evidence must be spread across ALL suspects, not concentrated on the killer.
- At least 2-3 evidence items should make each innocent suspect look suspicious (document \
their lies, suspicious behavior, concealed motives — even if ultimately unrelated to the murder).
- No more than ~30% of non-form, non-letter evidence should directly relate to the killer.
- Many evidence items should implicate MULTIPLE suspects at once (e.g., a phone log showing \
calls between two suspects, an SMS where one suspect gossips about another, a receipt that \
contradicts two alibis).
- Plan "red herring" evidence that points strongly at innocent suspects — these will keep \
the player guessing.
- The killer should NOT receive noticeably more evidence than other suspects in early/middle episodes.

EVIDENCE ANONYMIZATION (CRITICAL):
- The evidence plan (id, title, brief_description, clue_reveals) is internal and can \
reference suspect names freely for planning purposes.
- However, the ACTUAL evidence content (generated later) must NOT put suspect names in \
titles or headers of phone records, SMS logs, emails, or other documents. Instead, use \
identifiers the player must cross-reference with POI forms: phone numbers, license plates, \
email addresses, etc. However, if its natural in that context, names can be included too.
- For example: a phone log title should be "Phone Records: +48 555 1234" (not \
"Phone Records: John Smith"). The player figures out whose number it is from the POI form.
- The clue_reveals field should describe what the player learns, using the actual names.
- This creates investigative depth: players must study POI forms to connect documents \
to suspects, rather than having it handed to them.\
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
            relationships_str = "; ".join(
                f"{k}: {v}" for k, v in suspect.relationships.items()
            ) if suspect.relationships else "none"
            suspect_info = f"""
SUSPECT DETAILS (for consistency):
- Name: {suspect.name}, Age: {suspect.age}, Occupation: {suspect.occupation}
- Claimed alibi: {suspect.alibi}
- True alibi: {suspect.alibi_truth}
- Personality: {', '.join(suspect.personality_traits)}
- Secrets: {', '.join(suspect.secrets)}
- Relationships with other suspects: {relationships_str}
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
- If this is the killer, their answers should be plausible but contain subtle inconsistencies
- IMPORTANT: Use the interrogating detective from CASE PERSONNEL as the "interviewer" field
- FINGER-POINTING: Some of the suspect should mention, accuse, or cast suspicion on OTHER suspects \
during the interrogation. They might say things like "You should talk to X, they had a \
real grudge" or "I saw Y near the scene" or deflect blame. This creates inter-character \
intrigue and gives the player leads to cross-reference between interrogations.
- KEEP IT SHORT: Maximum 15-20 dialogue exchanges total.""",
        "poi_form": """\
Generate a filled-out Person of Interest form with all personal details. \
Use the suspect's established physical description and personal information.""",
        "letter": """\
Generate a letter. Match the tone to the letter_type:
- "intro": Professional investigator tone, setting up the episode's focus. Use the lead detective from CASE PERSONNEL as the sender.
- "solution": Revealing the truth, explaining how the evidence fits together. Use the lead detective as sender.
- "narrative": In-character from someone involved in the case

TYPST FORMATTING:
Also fill the "text_typst" field with a Typst-formatted version of the letter body.
Typst syntax rules:
- Use two newlines to create a new line/paragraph
- Use *text* for bold, _text_ for italic
- Do NOT include the letter title, sender, recipient, or date in text_typst \
-- only the body text itself""",
        "image": _build_image_type_instructions(case, plan_item),
        "raw_text": """\
Generate the document content matching the format_hint. Make it feel authentic:
- newspaper_article: journalistic tone, include byline and date
- lab_report / autopsy_report: clinical, precise, technical. Use the coroner from CASE PERSONNEL as the author.
- drug_guide: informational, medical reference style
- phone_message: casual text message format
- note: handwritten feel, possibly informal
- other: match the brief_description style

FORMATTED VERSIONS:
Also fill these three additional fields with formatted versions of the content:
- "text_html": HTML-formatted version (use semantic tags: <h1>, <p>, <strong>, <em>, <table>, etc.)
- "text_latex": LaTeX-formatted version (use \\section, \\textbf, \\textit, \\begin{tabular}, etc.)
- "text_typst": Typst-formatted version (use = heading, *bold*, _italic_, two newlines for paragraph breaks)
Each formatted version should faithfully reproduce the "content" field's text with \
appropriate markup for that format.""",
        "phone_log": """\
Generate a realistic phone call log. Include:
- owner_name: who this phone belongs to
- phone_number: their phone number
- entries: a list of call log entries, each with:
  - timestamp: date and time (e.g. "2024-03-15 14:32")
  - direction: "incoming", "outgoing", or "missed"
  - other_party: name or phone number of the other person
  - duration: call length (e.g. "2m 34s"), empty for missed calls
Make the timestamps realistic and consistent with the case timeline. Include calls \
that are relevant to the investigation mixed with mundane everyday calls.""",
        "sms_log": """\
Generate a realistic SMS conversation thread between two people. This represents \
a single chat thread (like opening a conversation with one contact). Include:
- owner_name: who this phone belongs to
- phone_number: the owner's phone number
- other_party: name or phone number of the person they're texting
- messages: a list of text messages in the conversation, each with:
  - timestamp: date and time (e.g. "2024-03-15 14:32")
  - direction: "incoming" or "outgoing"
  - text: the actual message content
Make the timestamps realistic and consistent with the case timeline. Include messages \
that are relevant to the investigation mixed with mundane everyday texts. Messages should \
feel natural and casual, like a real text conversation between two people.""",
        "email": """\
Generate a realistic email message. Include:
- from_address: sender's email
- to_address: recipient's email
- cc: CC field (empty string if none)
- subject: email subject line
- date: when it was sent
- body_text: the email body
- text_typst: Typst-formatted version of body (two newlines for paragraphs, *bold*, _italic_)
- text_html: HTML-formatted version of body
Make it feel like a real email with appropriate tone for the sender.""",
        "handwritten_note": """\
Generate a handwritten note. Include:
- author: the name of the person who wrote it (must match a suspect or known character)
- content: the text of the note (keep it short and natural, like a real handwritten note -- \
a few sentences to a short paragraph)
- context: where/how the note was found (e.g. "Found in the victim's desk drawer")
The tone should be casual and personal, with informal language.""",
        "instagram_post": """\
Generate an Instagram post. Include:
- username: the poster's Instagram handle (realistic, not their full name)
- caption: the post caption (with hashtags if appropriate)
- likes: number of likes (realistic number)
- date: when it was posted
- image_prompt: a detailed prompt for AI image generation describing what the photo shows
Make it feel like a real Instagram post.""",
        "facebook_post": """\
Generate a Facebook post. Include:
- author_name: the poster's display name
- content: the post text
- date: when it was posted
- likes: number of reactions (realistic)
- comments: a list of 0-3 comment strings from other people (format: "Name: comment text")
Make it feel like a real Facebook post with casual social media tone.""",
        "invoice": """\
Generate a realistic business invoice. Include:
- invoice_number: a realistic invoice number (e.g. "INV-2024-0847")
- date: the invoice date
- seller_name: business or individual issuing the invoice
- seller_address: their address
- buyer_name: the person or business being invoiced
- buyer_address: their address
- items: a list of line items, each with description, quantity, unit_price, and total
- subtotal: sum before tax
- tax: tax amount (can be empty if not applicable)
- total: final total
- payment_terms: e.g. "Net 30", "Due on receipt" (optional)
- notes: any additional notes (optional)
Make it feel like an authentic business document. The items and amounts should be \
realistic and consistent with the case context.""",
        "receipt": """\
Generate a realistic store receipt. Include:
- store_name: the store or business name
- store_address: the store's address
- date: date and time of purchase
- items: a list of purchased items, each with description, quantity, and price
- subtotal: sum before tax
- tax: tax amount (can be empty if not applicable)
- total: final total
- payment_method: e.g. "VISA ****4832", "Cash" (optional)
- transaction_id: receipt/transaction number (optional)
Make it feel like a real receipt. Include items that are relevant to the investigation \
mixed with mundane purchases for realism.""",
    }

    # Build the full evidence plan summary so the LLM knows what every other
    # item is responsible for and can avoid duplicating or leaking their clues.
    other_plan_items = [p for p in case.evidence_plan if p.id != plan_item.id]
    evidence_plan_summary = "\n".join(
        f"  - [{p.id}] ({p.type}) \"{p.title}\" — reveals: {p.clue_reveals}"
        for p in other_plan_items
    )

    # Build personnel context
    personnel_info = ""
    if case.personnel:
        p = case.personnel
        personnel_info = f"""
CASE PERSONNEL (use these EXACT names for consistency across all evidence):
- Lead detective: {p.lead_detective}
- Interrogating detective: {p.interrogating_detective} (use as the "interviewer" in ALL interrogations)
- Coroner / Medical examiner: {p.coroner}"""
        if p.forensic_technician:
            personnel_info += f"\n- Forensic technician: {p.forensic_technician}"
        personnel_info += "\n"

    content = f"""\
Generate the full content for this evidence item.

THIS EVIDENCE ITEM:
- ID: {plan_item.id}
- Type: {plan_item.type}
- Title: {plan_item.title}
- Description: {plan_item.brief_description}
- Clue it reveals: {plan_item.clue_reveals}
- Introduced in episode: {plan_item.introduced_in_episode}
- Also used in episodes: {plan_item.also_used_in_episodes}
{suspect_info}{personnel_info}
ALL OTHER EVIDENCE ITEMS IN THE CASE (for reference — do NOT include their clues here):
{evidence_plan_summary}

^^^ Each of the items above is responsible for revealing its own clue. Do NOT let this \
evidence item reveal, hint at, or duplicate information that belongs to another item. \
Stick strictly to what THIS item is supposed to convey.

CASE TRUTH (for consistency only — do NOT leak extra facts from this section):
- Victim: {truth.victim.name}, died at crime scene: {truth.crime_scene}
- Cause of death: {truth.victim.cause_of_death}
- Killer: {truth.killer_name}
- Method: {truth.method}
- Timeline: {_format_timeline(truth)}

CONTENT SCOPE (CRITICAL):
- This evidence must ONLY convey what is described in "Description" and "clue_reveals" field above.
- Do NOT include additional facts, revelations, or connections from the case truth \
that go beyond what this specific evidence item is designed to show.
- The case truth above is provided ONLY to ensure consistency (no contradictions). \
It is NOT a source of additional content to include.
- If a suspect is the killer, their evidence may hint at subtle inconsistencies \
(only if that is part of this evidence's purpose), but must NOT reveal information \
beyond this item's designated scope.

SUSPECT BALANCE (CRITICAL):
- This evidence item should NOT single out the killer unless it is explicitly designed \
to do so in its clue_reveals.
- Where possible, reference or implicate MULTIPLE suspects — mention other names, \
show interactions between suspects, or include details that cast suspicion broadly.
- Innocent suspects should appear just as suspicious as the killer in early/middle-episode evidence.
- Phone logs, SMS logs, and emails should show conversations with MULTIPLE suspects, \
not only killer-related contacts.

LENGTH GUIDELINES (important — keep evidence concise):
- Interrogation transcripts: 15-20 exchanges maximum (1-2 printed pages).
- Letters: 1 page maximum.
- Raw text documents (reports, articles, notes): 1 page maximum.
- Emails: half a page to 1 page.
- Phone/SMS logs: only relevant entries plus optionally a few mundane ones for realism.
- All evidence should be brief and factual like real investigation documents.

SPECIFIC INSTRUCTIONS FOR THIS TYPE:
{type_instructions.get(plan_item.type, "Generate appropriate content.")}

EVIDENCE ANONYMIZATION (CRITICAL):
- Do NOT put suspect names in document titles, headers, or metadata fields of \
phone logs, SMS logs, emails, raw_text documents, etc.
- Instead, use identifiers the player must cross-reference: phone numbers (from POI forms), \
email addresses, license plate numbers, ID numbers, etc.
- For phone_log/sms_log: use the phone number from the suspect's POI form as owner_name \
identifier. The "other_party" field should use phone numbers too (not names), unless \
the contact is saved in the phone (then a first name or nickname is OK).
- For email: use realistic email addresses, not "suspect_name@example.com".
- For raw_text: if it's official records (phone records, bank statements, etc.), \
identify people by ID numbers, phone numbers, or account numbers -- not full names.
- The goal: the player must connect documents to suspects by cross-referencing details \
from POI forms. This creates investigative depth.

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
            "\n\nIMPORTANT -- VISUAL CONSISTENCY: The following suspects appear in this image. "
            "Their actual portrait photos will be attached as reference images during generation. "
            "Use these portrait descriptions to ensure they look the same:\n"
            + "\n".join(portrait_refs)
        )

    # Check if the victim appears in this image
    if case.truth and case.truth.victim.portrait_prompt:
        victim = case.truth.victim
        name_lower = victim.name.lower()
        if (
            name_lower in plan_item.brief_description.lower()
            or name_lower in plan_item.title.lower()
        ):
            base += (
                f"\n\nVICTIM REFERENCE: The victim {victim.name} appears in this image. "
                f"Their portrait photo will be attached as a reference image. "
                f"Portrait description: {victim.portrait_prompt}"
            )

    return base


def _format_timeline(truth: CaseTruth) -> str:
    if not truth.timeline:
        return "Not yet established"
    return "; ".join(
        f"{e.time}: {e.description}" + (f" ({e.actor})" if e.actor else "")
        for e in truth.timeline
    )
