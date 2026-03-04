"""Resumable state-machine pipeline for case generation.

The pipeline progresses through GenerationPhase steps. After each step,
the case is saved to disk. If interrupted, `resume()` picks up where
it left off by reading `case.generation_state.phase`.
"""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from caseclosed.generation.episodes import generate_episodes
from caseclosed.generation.evidence import (
    edit_evidence_image,
    generate_evidence_content,
    generate_evidence_image,
)
from caseclosed.generation.evidence_plan import generate_evidence_plan
from caseclosed.generation.suspects import generate_suspects
from caseclosed.generation.truth import generate_personnel, generate_truth
from caseclosed.models.case import Case, GenerationPhase
from caseclosed.models.evidence import (
    EvidenceItem,
    Email,
    FacebookPost,
    HandwrittenNote,
    ImageEvidence,
    InstagramPost,
    InterrogationReport,
    Invoice,
    Letter,
    PersonOfInterestForm,
    PhoneLog,
    RawText,
    Receipt,
    SmsLog,
)
from caseclosed.models.suspect import Suspect
from caseclosed.persistence import images_dir, save_case

console = Console()


def _confirm_or_edit(prompt_text: str = "Accept? (y/n/instructions for edit)") -> tuple[str, str | None]:
    """Ask the user to accept, regenerate, or provide edit instructions.

    Special commands (handled in-place, then re-prompts):
        model <name>       — change the text generation model
        image-model <name> — change the image generation model

    Returns:
        ("accept", None) — proceed
        ("regenerate", None) — regenerate from scratch
        ("edit", <instructions>) — regenerate with specific instructions
    """
    from caseclosed.config import settings

    while True:
        console.print()
        console.print(
            f"  [dim]model {settings.default_model} | "
            f"image-model {settings.default_image_model} | "
            f"image-modality {','.join(settings.image_model_modalities)}[/dim]"
        )
        response = console.input(f"[bold yellow]{prompt_text}:[/bold yellow] ").strip()

        # Model change commands
        if response.lower().startswith("model "):
            new_model = response[6:].strip()
            if new_model:
                settings.default_model = new_model
                console.print(f"  [green]Text model changed to:[/green] {new_model}")
            continue
        if response.lower().startswith("image-model "):
            new_model = response[12:].strip()
            if new_model:
                settings.default_image_model = new_model
                console.print(f"  [green]Image model changed to:[/green] {new_model}")
            continue
        if response.lower().startswith("image-modality "):
            raw = response[15:].strip().lower()
            if raw in ("image", "image,text", "image+text"):
                if raw == "image":
                    settings.image_model_modalities = ["image"]
                else:
                    settings.image_model_modalities = ["image", "text"]
                console.print(f"  [green]Image modalities changed to:[/green] {settings.image_model_modalities}")
            else:
                console.print("  [red]Use: image-modality image  OR  image-modality image,text[/red]")
            continue

        if response.lower() in ("y", "yes", ""):
            return ("accept", None)
        if response.lower() in ("n", "no", "regenerate"):
            return ("regenerate", None)
        return ("edit", response)


def _display_truth(case: Case) -> None:
    assert case.truth is not None
    t = case.truth
    table = Table(title="Case Truth (Hidden from players)", show_lines=True)
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="white")
    table.add_row("Victim", f"{t.victim.name}, {t.victim.age}, {t.victim.occupation}")
    table.add_row("Cause of Death", t.victim.cause_of_death)
    table.add_row("Killer", t.killer_name)
    table.add_row("Method", t.method)
    table.add_row("Weapon", t.weapon or "N/A")
    table.add_row("Motive", t.motive)
    table.add_row("Crime Scene", t.crime_scene)
    if t.timeline:
        timeline_str = "\n".join(
            f"  {e.time}: {e.description}" + (f" ({e.actor})" if e.actor else "")
            for e in t.timeline
        )
        table.add_row("Timeline", timeline_str)
    if t.key_evidence_summary:
        table.add_row("Key Evidence", t.key_evidence_summary)
    console.print(table)

    # Display personnel if set
    if case.personnel:
        p = case.personnel
        ptable = Table(title="Case Personnel", show_lines=True)
        ptable.add_column("Role", style="cyan")
        ptable.add_column("Name", style="white")
        ptable.add_row("Lead Detective", p.lead_detective)
        ptable.add_row("Interrogating Detective", p.interrogating_detective)
        ptable.add_row("Coroner", p.coroner)
        if p.forensic_technician:
            ptable.add_row("Forensic Technician", p.forensic_technician)
        console.print(ptable)


def _display_suspects(case: Case) -> None:
    for s in case.suspects:
        killer_tag = " [bold red](KILLER)[/bold red]" if s.is_killer else ""
        console.print(Panel(
            f"[bold]{s.name}[/bold]{killer_tag}\n"
            f"Age: {s.age} | Occupation: {s.occupation}\n"
            f"Relationship: {s.relationship_to_victim}\n"
            f"Apparent motive: {s.motive}\n"
            f"Claimed alibi: {s.alibi}\n"
            f"[dim]True alibi: {s.alibi_truth}[/dim]\n"
            f"Secrets: {', '.join(s.secrets) if s.secrets else 'None'}",
            title=f"Suspect: {s.name}",
        ))


def _display_episodes(case: Case) -> None:
    for ep in case.episodes:
        hints_str = ""
        if ep.hints:
            hints_str = "\n[bold]Hints:[/bold]\n" + "\n".join(f"  {i}. {h}" for i, h in enumerate(ep.hints, 1))
        solution_str = ""
        if ep.previous_episode_solution:
            solution_str = f"\n[bold]Previous ep solution:[/bold] {ep.previous_episode_solution}"
        console.print(Panel(
            f"[bold]Objective:[/bold] {ep.objective}\n"
            f"[bold]Intro letter:[/bold] {ep.intro_letter}\n"
            f"Evidence IDs: {', '.join(ep.evidence_ids) if ep.evidence_ids else 'TBD'}"
            f"{hints_str}{solution_str}",
            title=f"Episode {ep.number}: {ep.title}",
        ))


def _display_evidence_plan(case: Case) -> None:
    table = Table(title="Evidence Plan", show_lines=True)
    table.add_column("#", style="dim")
    table.add_column("ID", style="cyan")
    table.add_column("Type", style="magenta")
    table.add_column("Title")
    table.add_column("Ep", justify="center")
    table.add_column("Also in", justify="center")
    table.add_column("Reveals")

    for i, item in enumerate(case.evidence_plan, 1):
        also = ", ".join(str(e) for e in item.also_used_in_episodes) if item.also_used_in_episodes else "-"
        table.add_row(
            str(i),
            item.id,
            item.type,
            item.title,
            str(item.introduced_in_episode),
            also,
            item.clue_reveals,
        )
    console.print(table)


def _display_evidence_item(evidence: EvidenceItem) -> None:
    """Display a single generated evidence item."""
    if isinstance(evidence, InterrogationReport):
        lines = "\n".join(f"  [cyan]{d.speaker}:[/cyan] {d.text}" for d in evidence.transcript)
        console.print(Panel(
            f"Suspect: {evidence.suspect_name}\n"
            f"Case #: {evidence.case_number} | Date: {evidence.date}\n"
            f"Interviewer: {evidence.interviewer}\n\n"
            f"{lines}",
            title=f"[magenta]Interrogation:[/magenta] {evidence.plan_id}",
        ))
    elif isinstance(evidence, PersonOfInterestForm):
        console.print(Panel(
            f"{evidence.name} {evidence.last_name}"
            + (f' "{evidence.nickname}"' if evidence.nickname else "")
            + f"\nDOB: {evidence.date_of_birth} | Nationality: {evidence.nationality or 'N/A'}\n"
            f"Occupation: {evidence.occupation or 'N/A'}\n"
            f"Height: {evidence.height_cm or '?'}cm | Weight: {evidence.weight_kg or '?'}kg\n"
            f"Eye: {evidence.eye_color or '?'} | Hair: {evidence.hair_color or '?'}",
            title=f"[magenta]POI Form:[/magenta] {evidence.plan_id}",
        ))
    elif isinstance(evidence, Letter):
        console.print(Panel(
            f"From: {evidence.sender} \u2192 To: {evidence.recipient}\n"
            f"Date: {evidence.date or 'N/A'} | Type: {evidence.letter_type}\n\n"
            f"{evidence.body_text}",
            title=f"[magenta]Letter:[/magenta] {evidence.plan_id}",
        ))
    elif isinstance(evidence, ImageEvidence):
        console.print(Panel(
            f"Caption: {evidence.caption}\n"
            f"Location: {evidence.location_context or 'N/A'}\n\n"
            f"[dim]Prompt: {evidence.image_prompt}[/dim]",
            title=f"[magenta]Image:[/magenta] {evidence.plan_id}",
        ))
    elif isinstance(evidence, RawText):
        console.print(Panel(
            f"Format: {evidence.format_hint}\n\n{evidence.content}",
            title=f"[magenta]Text:[/magenta] {evidence.plan_id}",
        ))
    elif isinstance(evidence, PhoneLog):
        lines = "\n".join(
            f"  {e.timestamp} | {e.direction:>8} | {e.other_party} | {e.duration or '-'}"
            for e in evidence.entries
        )
        console.print(Panel(
            f"Owner: {evidence.owner_name} ({evidence.phone_number})\n\n{lines}",
            title=f"[magenta]Phone Log:[/magenta] {evidence.plan_id}",
        ))
    elif isinstance(evidence, SmsLog):
        lines = "\n".join(
            f"  {m.timestamp} | {m.direction:>8}\n    {m.text}"
            for m in evidence.messages
        )
        console.print(Panel(
            f"Owner: {evidence.owner_name} ({evidence.phone_number})\n"
            f"Conversation with: {evidence.other_party}\n\n{lines}",
            title=f"[magenta]SMS Log:[/magenta] {evidence.plan_id}",
        ))
    elif isinstance(evidence, Email):
        console.print(Panel(
            f"From: {evidence.from_address}\n"
            f"To: {evidence.to_address}\n"
            + (f"CC: {evidence.cc}\n" if evidence.cc else "")
            + f"Subject: {evidence.subject}\n"
            f"Date: {evidence.date}\n\n"
            f"{evidence.body_text}",
            title=f"[magenta]Email:[/magenta] {evidence.plan_id}",
        ))
    elif isinstance(evidence, HandwrittenNote):
        console.print(Panel(
            f"Author: {evidence.author}\n"
            f"Context: {evidence.context or 'N/A'}\n\n"
            f"{evidence.content}",
            title=f"[magenta]Handwritten Note:[/magenta] {evidence.plan_id}",
        ))
    elif isinstance(evidence, InstagramPost):
        console.print(Panel(
            f"@{evidence.username} | {evidence.date}\n"
            f"Likes: {evidence.likes}\n\n"
            f"{evidence.caption}\n\n"
            f"[dim]Image prompt: {evidence.image_prompt or 'N/A'}[/dim]",
            title=f"[magenta]Instagram Post:[/magenta] {evidence.plan_id}",
        ))
    elif isinstance(evidence, FacebookPost):
        comments = "\n".join(f"  {c}" for c in evidence.comments) if evidence.comments else "(no comments)"
        console.print(Panel(
            f"{evidence.author_name} | {evidence.date}\n"
            f"Likes: {evidence.likes}\n\n"
            f"{evidence.content}\n\n"
            f"Comments:\n{comments}",
            title=f"[magenta]Facebook Post:[/magenta] {evidence.plan_id}",
        ))
    elif isinstance(evidence, Invoice):
        items = "\n".join(
            f"  {it.description} x{it.quantity} @ {it.unit_price} = {it.total}"
            for it in evidence.items
        )
        console.print(Panel(
            f"Invoice #{evidence.invoice_number} | {evidence.date}\n"
            f"Seller: {evidence.seller_name}\n"
            f"Buyer: {evidence.buyer_name}\n\n"
            f"{items}\n\n"
            f"Subtotal: {evidence.subtotal}"
            + (f" | Tax: {evidence.tax}" if evidence.tax else "")
            + f" | Total: {evidence.total}",
            title=f"[magenta]Invoice:[/magenta] {evidence.plan_id}",
        ))
    elif isinstance(evidence, Receipt):
        items = "\n".join(
            f"  {it.description} x{it.quantity} @ {it.price}"
            for it in evidence.items
        )
        console.print(Panel(
            f"{evidence.store_name} | {evidence.date}\n\n"
            f"{items}\n\n"
            f"Subtotal: {evidence.subtotal}"
            + (f" | Tax: {evidence.tax}" if evidence.tax else "")
            + f" | Total: {evidence.total}"
            + (f"\nPayment: {evidence.payment_method}" if evidence.payment_method else ""),
            title=f"[magenta]Receipt:[/magenta] {evidence.plan_id}",
        ))
    else:
        # Fallback for any unknown type
        console.print(Panel(
            str(evidence.model_dump()),
            title=f"[magenta]Evidence:[/magenta] {getattr(evidence, 'plan_id', '?')}",
        ))


# --- Pipeline Steps ---


def _step_truth(case: Case, suspect_count: int | None, episode_count: int | None, difficulty: str | None) -> None:
    """Generate or regenerate the case truth."""
    edit_instructions: str | None = None
    while True:
        if edit_instructions:
            console.print("\n[bold blue]Editing case truth...[/bold blue]")
        else:
            console.print("\n[bold blue]Generating case truth...[/bold blue]")
        case.truth = generate_truth(
            premise=case.premise,
            language=case.language,
            suspect_count=suspect_count,
            episode_count=episode_count,
            difficulty=difficulty,
            edit_instructions=edit_instructions,
            current_truth=case.truth if edit_instructions else None,
        )
        if case.truth.victim.name and case.title is None:
            case.title = f"The {case.truth.victim.name} Case"

        _display_truth(case)

        action, instructions = _confirm_or_edit()
        if action == "accept":
            # Auto-generate case personnel for consistency
            if not case.personnel:
                console.print("\n[bold blue]Generating case personnel...[/bold blue]")
                case.personnel = generate_personnel(case)
                _display_truth(case)  # re-display to show personnel
            case.generation_state.phase = GenerationPhase.SUSPECTS
            case.generation_state.current_step_detail = None
            save_case(case)
            return
        elif action == "edit":
            edit_instructions = instructions
        else:
            edit_instructions = None


def _step_suspects(case: Case) -> None:
    edit_instructions: str | None = None
    while True:
        if edit_instructions:
            console.print("\n[bold blue]Editing suspects...[/bold blue]")
        else:
            console.print("\n[bold blue]Generating suspects...[/bold blue]")
        case.suspects = generate_suspects(
            case,
            edit_instructions=edit_instructions,
            current_suspects=case.suspects if edit_instructions else None,
        )
        _display_suspects(case)

        action, instructions = _confirm_or_edit()
        if action == "accept":
            case.generation_state.phase = GenerationPhase.SUSPECT_PORTRAITS
            case.generation_state.current_step_detail = None
            save_case(case)
            return
        elif action == "edit":
            edit_instructions = instructions
        else:
            edit_instructions = None


def _portrait_exists(case: Case, suspect: Suspect) -> bool:
    """Check if a suspect's portrait image file actually exists on disk."""
    if not suspect.portrait_filename:
        return False
    from caseclosed.persistence import images_dir
    return (images_dir(case.id) / suspect.portrait_filename).exists()


def _step_suspect_portraits(case: Case) -> None:
    """Generate portrait images for each suspect and the victim (resumable)."""
    from caseclosed.generation.suspects import generate_suspect_portrait_prompt, generate_victim_portrait_prompt
    from caseclosed.llm.client import generate_image
    from caseclosed.persistence import save_image

    # --- Victim portrait ---
    assert case.truth is not None
    victim = case.truth.victim
    victim_exists = (
        victim.portrait_filename
        and (images_dir(case.id) / victim.portrait_filename).exists()
    )
    if not victim_exists:
        console.print(f"\n[bold blue]Generating victim portrait: {victim.name}[/bold blue]")
        if not victim.portrait_prompt:
            victim.portrait_prompt = generate_victim_portrait_prompt(
                victim.name, victim.age, victim.occupation, victim.description, case.language
            )
            save_case(case)

        try:
            image_data = generate_image(victim.portrait_prompt, aspect_ratio="1:1")
            filename = f"portrait-victim-{victim.name.lower().replace(' ', '-')}.png"
            save_image(case.id, filename, image_data)
            victim.portrait_filename = filename
            console.print(f"  [green]\u2713[/green] Saved: {filename}")
        except Exception as e:
            console.print(f"  [red]\u2717 Victim portrait generation failed: {e}[/red]")
        save_case(case)
    else:
        console.print(f"[dim]Victim portrait already generated: {victim.portrait_filename}[/dim]")

    # --- Suspect portraits ---
    remaining = [s for s in case.suspects if not _portrait_exists(case, s)]
    total = len(case.suspects)
    done = total - len(remaining)

    if not remaining:
        console.print("[dim]All suspect portraits already generated.[/dim]")
    else:
        for i, suspect in enumerate(remaining, start=done + 1):
            console.print(f"\n[bold blue]Generating portrait [{i}/{total}]: {suspect.name}[/bold blue]")
            case.generation_state.current_step_detail = f"portrait:{i}/{total}"

            # Generate portrait prompt if not already set
            if not suspect.portrait_prompt:
                suspect.portrait_prompt = generate_suspect_portrait_prompt(suspect, case.language)
                save_case(case)

            try:
                image_data = generate_image(suspect.portrait_prompt, aspect_ratio="1:1")
                filename = f"portrait-{suspect.name.lower().replace(' ', '-')}.png"
                save_image(case.id, filename, image_data)
                suspect.portrait_filename = filename
                console.print(f"  [green]\u2713[/green] Saved: {filename}")
            except Exception as e:
                console.print(f"  [red]\u2717 Portrait generation failed: {e}[/red]")
                console.print("  [dim]Skipping \u2014 you can regenerate later with 'edit'[/dim]")

            save_case(case)

    case.generation_state.phase = GenerationPhase.EPISODES
    case.generation_state.current_step_detail = None
    save_case(case)
    console.print("\n[bold green]Suspect portraits done![/bold green]")


def _step_episodes(case: Case) -> None:
    edit_instructions: str | None = None
    while True:
        if edit_instructions:
            console.print("\n[bold blue]Editing episodes...[/bold blue]")
        else:
            console.print("\n[bold blue]Generating episodes...[/bold blue]")
        case.episodes = generate_episodes(
            case,
            edit_instructions=edit_instructions,
            current_episodes=case.episodes if edit_instructions else None,
        )
        _display_episodes(case)

        action, instructions = _confirm_or_edit()
        if action == "accept":
            case.generation_state.phase = GenerationPhase.EVIDENCE_PLAN
            case.generation_state.current_step_detail = None
            save_case(case)
            return
        elif action == "edit":
            edit_instructions = instructions
        else:
            edit_instructions = None


def _step_evidence_plan(case: Case) -> None:
    edit_instructions: str | None = None
    while True:
        if edit_instructions:
            console.print("\n[bold blue]Editing evidence plan...[/bold blue]")
        else:
            console.print("\n[bold blue]Planning evidence graph...[/bold blue]")
        case.evidence_plan = generate_evidence_plan(
            case,
            edit_instructions=edit_instructions,
            current_plan=case.evidence_plan if edit_instructions else None,
        )

        # Wire evidence IDs into episodes
        for ep in case.episodes:
            ep.evidence_ids = [
                item.id for item in case.evidence_plan
                if item.introduced_in_episode == ep.number
                or ep.number in item.also_used_in_episodes
            ]

        _display_evidence_plan(case)

        action, instructions = _confirm_or_edit()
        if action == "accept":
            case.generation_state.phase = GenerationPhase.EVIDENCE_CONTENT
            case.generation_state.current_step_detail = None
            save_case(case)
            return
        elif action == "edit":
            edit_instructions = instructions
        else:
            edit_instructions = None


def _edit_image_prompt(current_prompt: str, edit_instructions: str) -> str:
    """Refine an image prompt via LLM based on edit instructions."""
    from caseclosed.llm.client import generate_text

    messages = [
        {"role": "system", "content": "You are an expert at writing detailed image generation prompts. Edit the given prompt according to the user's instructions. Return ONLY the revised prompt text, nothing else."},
        {"role": "user", "content": f"Current image prompt:\n\n{current_prompt}\n\nEdit instructions: {edit_instructions}"},
    ]
    return generate_text(messages)


def _confirm_image_action(
    prompt_text: str = "Accept image? (y/n/p <prompt edit>/e <image edit>)",
) -> tuple[str, str | None]:
    """Ask the user to accept, regenerate, edit prompt, or edit image directly.

    Returns:
        ("accept", None)
        ("regenerate", None)
        ("edit_prompt", <instructions>)  — modify the text prompt, then regen
        ("edit_image", <instructions>)   — send the image + instructions for direct editing
    """
    from caseclosed.config import settings

    while True:
        console.print()
        console.print(
            f"  [dim]model {settings.default_model} | "
            f"image-model {settings.default_image_model} | "
            f"image-modality {','.join(settings.image_model_modalities)}[/dim]"
        )
        response = console.input(f"[bold yellow]{prompt_text}:[/bold yellow] ").strip()

        # Model change commands (same as _confirm_or_edit)
        if response.lower().startswith("model "):
            new_model = response[6:].strip()
            if new_model:
                settings.default_model = new_model
                console.print(f"  [green]Text model changed to:[/green] {new_model}")
            continue
        if response.lower().startswith("image-model "):
            new_model = response[12:].strip()
            if new_model:
                settings.default_image_model = new_model
                console.print(f"  [green]Image model changed to:[/green] {new_model}")
            continue

        if response.lower() in ("y", "yes", ""):
            return ("accept", None)
        if response.lower() in ("n", "no"):
            return ("regenerate", None)
        if response.lower().startswith("p "):
            return ("edit_prompt", response[2:].strip())
        if response.lower().startswith("e "):
            return ("edit_image", response[2:].strip())
        # Bare text defaults to prompt edit for backwards compat
        return ("edit_prompt", response)


def _generate_image_inline(case: Case, evidence: ImageEvidence | InstagramPost) -> None:
    """Generate the actual image for an evidence item with image_prompt.

    Shows the prompt for approval/editing, generates, then confirms.
    """
    while True:
        console.print(Panel(
            f"[bold]Prompt:[/bold]\n{evidence.image_prompt}",
            title=f"Image prompt: {evidence.plan_id}",
        ))

        action, instructions = _confirm_or_edit("Approve image prompt? (y/n/edit instructions)")
        if action == "edit" and instructions:
            console.print("  [bold blue]Editing prompt...[/bold blue]")
            evidence.image_prompt = _edit_image_prompt(evidence.image_prompt, instructions)
            console.print("[dim]Prompt updated. Showing again...[/dim]")
            continue
        if action == "regenerate":
            console.print("[dim]Skipping image generation for now.[/dim]")
            return

        console.print("  [bold blue]Generating image...[/bold blue]")
        try:
            filename = generate_evidence_image(case, evidence)
            evidence.image_filename = filename
            console.print(f"  [green]\u2713[/green] Saved: {filename}")
        except Exception as e:
            console.print(f"  [red]\u2717 Image generation failed: {e}[/red]")
            retry_action, _ = _confirm_or_edit("Retry? (y to retry / n to skip)")
            if retry_action == "accept":
                continue
            return

        img_action, img_instructions = _confirm_image_action()
        if img_action == "accept":
            save_case(case)
            console.print(f"  [green]\u2713[/green] Image accepted: {evidence.plan_id}")
            return
        elif img_action == "edit_prompt" and img_instructions:
            console.print("  [bold blue]Editing prompt...[/bold blue]")
            evidence.image_prompt = _edit_image_prompt(evidence.image_prompt, img_instructions)
            evidence.image_filename = None
            console.print("[dim]Prompt updated. Regenerating...[/dim]")
        elif img_action == "edit_image" and img_instructions:
            console.print("  [bold blue]Editing image directly...[/bold blue]")
            try:
                filename = edit_evidence_image(case, evidence, img_instructions)
                evidence.image_filename = filename
                console.print(f"  [green]\u2713[/green] Edited image saved: {filename}")
            except Exception as e:
                console.print(f"  [red]\u2717 Image edit failed: {e}[/red]")
        else:
            evidence.image_filename = None
            console.print("[dim]Regenerating...[/dim]")


def _step_evidence_content(case: Case) -> None:
    """Generate evidence content one item at a time (resumable, with approval)."""
    already_generated_ids = [e.plan_id for e in case.evidence if hasattr(e, "plan_id")]
    remaining = [
        item for item in case.evidence_plan
        if item.id not in already_generated_ids
    ]

    total = len(case.evidence_plan)
    done = total - len(remaining)

    for i, plan_item in enumerate(remaining, start=done + 1):
        edit_instructions: str | None = None
        current_evidence: EvidenceItem | None = None
        while True:
            if edit_instructions:
                console.print(f"\n[bold blue]Editing evidence [{i}/{total}]: {plan_item.title}[/bold blue]")
            else:
                console.print(f"\n[bold blue]Generating evidence [{i}/{total}]: {plan_item.title}[/bold blue]")
            case.generation_state.current_step_detail = f"evidence:{i}/{total}"

            evidence = generate_evidence_content(
                case, plan_item, already_generated_ids,
                edit_instructions=edit_instructions,
                current_evidence=current_evidence if edit_instructions else None,
            )
            _display_evidence_item(evidence)

            action, instructions = _confirm_or_edit()
            if action == "accept":
                case.evidence.append(evidence)
                already_generated_ids.append(plan_item.id)
                save_case(case)
                console.print(f"  [green]✓[/green] Accepted: {plan_item.title} ({plan_item.type})")

                # For evidence with images, generate the actual image immediately
                if isinstance(evidence, (ImageEvidence, InstagramPost)) and evidence.image_prompt:
                    _generate_image_inline(case, evidence)

                break
            elif action == "edit":
                edit_instructions = instructions
                current_evidence = evidence
            else:
                edit_instructions = None
                current_evidence = None

    case.generation_state.phase = GenerationPhase.IMAGES
    case.generation_state.current_step_detail = None
    save_case(case)
    console.print("\n[bold green]All evidence content generated![/bold green]")


def _step_images(case: Case) -> None:
    """Generate images for evidence items that need them (resumable, with approval)."""
    image_items: list[ImageEvidence | InstagramPost] = [
        e for e in case.evidence
        if isinstance(e, (ImageEvidence, InstagramPost))
        and e.image_filename is None
        and e.image_prompt
    ]

    if not image_items:
        console.print("[dim]No images to generate.[/dim]")
        case.generation_state.phase = GenerationPhase.COMPLETE
        save_case(case)
        return

    total = len([
        e for e in case.evidence
        if isinstance(e, (ImageEvidence, InstagramPost)) and e.image_prompt
    ])
    done = total - len(image_items)

    for i, img_evidence in enumerate(image_items, start=done + 1):
        while True:
            label = (
                img_evidence.caption
                if isinstance(img_evidence, ImageEvidence)
                else f"@{img_evidence.username}"
            )
            console.print(f"\n[bold blue]Image [{i}/{total}]: {label}[/bold blue]")
            console.print(Panel(
                f"[bold]Prompt:[/bold]\n{img_evidence.image_prompt}",
                title=f"Image prompt: {img_evidence.plan_id}",
            ))

            case.generation_state.current_step_detail = f"image:{i}/{total}"

            action, instructions = _confirm_or_edit("Approve prompt? (y/n/edit instructions)")
            if action == "edit" and instructions:
                console.print("  [bold blue]Editing prompt...[/bold blue]")
                img_evidence.image_prompt = _edit_image_prompt(img_evidence.image_prompt, instructions)
                console.print("[dim]Prompt updated. Showing again...[/dim]")
                continue
            if action == "regenerate":
                console.print("[dim]Skipping this image.[/dim]")
                break

            # Generate the actual image
            console.print("  [bold blue]Generating image...[/bold blue]")
            try:
                filename = generate_evidence_image(case, img_evidence)
                img_evidence.image_filename = filename
                console.print(f"  [green]\u2713[/green] Saved: {filename}")
            except Exception as e:
                console.print(f"  [red]\u2717 Image generation failed: {e}[/red]")
                console.print("  [dim]You can retry or skip.[/dim]")
                retry_action, _ = _confirm_or_edit("Retry? (y to retry / n to skip)")
                if retry_action == "accept":
                    continue
                break

            # Ask if the generated image is acceptable
            img_action, img_instructions = _confirm_image_action()
            if img_action == "accept":
                save_case(case)
                console.print(f"  [green]\u2713[/green] Accepted: {img_evidence.plan_id}")
                break
            elif img_action == "edit_prompt" and img_instructions:
                console.print("  [bold blue]Editing prompt...[/bold blue]")
                img_evidence.image_prompt = _edit_image_prompt(img_evidence.image_prompt, img_instructions)
                img_evidence.image_filename = None
                console.print("[dim]Prompt updated. Regenerating...[/dim]")
            elif img_action == "edit_image" and img_instructions:
                console.print("  [bold blue]Editing image directly...[/bold blue]")
                try:
                    filename = edit_evidence_image(case, img_evidence, img_instructions)
                    img_evidence.image_filename = filename
                    console.print(f"  [green]\u2713[/green] Edited image saved: {filename}")
                except Exception as e:
                    console.print(f"  [red]\u2717 Image edit failed: {e}[/red]")
            else:
                # Reset filename so it regenerates
                img_evidence.image_filename = None
                console.print("[dim]Regenerating...[/dim]")

        save_case(case)

    case.generation_state.phase = GenerationPhase.COMPLETE
    case.generation_state.current_step_detail = None
    save_case(case)
    console.print("\n[bold green]Case generation complete![/bold green]")


# --- Main Pipeline Entry Points ---


def run_pipeline(
    case: Case,
    suspect_count: int | None = None,
    episode_count: int | None = None,
    difficulty: str | None = None,
) -> Case:
    """Run the full generation pipeline from the current phase.

    This is the main entry point for both new cases and resumed ones.
    """
    phase = case.generation_state.phase

    if phase == GenerationPhase.PREMISE or phase == GenerationPhase.TRUTH:
        _step_truth(case, suspect_count, episode_count, difficulty)
        phase = case.generation_state.phase

    if phase == GenerationPhase.SUSPECTS:
        _step_suspects(case)
        phase = case.generation_state.phase

    if phase == GenerationPhase.SUSPECT_PORTRAITS:
        _step_suspect_portraits(case)
        phase = case.generation_state.phase

    if phase == GenerationPhase.EPISODES:
        _step_episodes(case)
        phase = case.generation_state.phase

    if phase == GenerationPhase.EVIDENCE_PLAN:
        _step_evidence_plan(case)
        phase = case.generation_state.phase

    if phase == GenerationPhase.EVIDENCE_CONTENT:
        _step_evidence_content(case)
        phase = case.generation_state.phase

    if phase == GenerationPhase.IMAGES:
        _step_images(case)

    return case
