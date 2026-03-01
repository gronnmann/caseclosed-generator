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
    generate_evidence_content,
    generate_evidence_image,
)
from caseclosed.generation.evidence_plan import generate_evidence_plan
from caseclosed.generation.suspects import generate_suspects
from caseclosed.generation.truth import generate_truth
from caseclosed.models.case import Case, GenerationPhase
from caseclosed.models.evidence import ImageEvidence
from caseclosed.persistence import save_case

console = Console()


def _confirm_or_edit(prompt_text: str = "Accept? (y/n/instructions for edit)") -> tuple[str, str | None]:
    """Ask the user to accept, regenerate, or provide edit instructions.

    Returns:
        ("accept", None) — proceed
        ("regenerate", None) — regenerate from scratch
        ("edit", <instructions>) — regenerate with specific instructions
    """
    console.print()
    response = console.input(f"[bold yellow]{prompt_text}:[/bold yellow] ").strip()
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
        console.print(Panel(
            f"[bold]Objective:[/bold] {ep.objective}\n"
            f"[bold]Intro letter excerpt:[/bold] {ep.intro_letter[:200]}...\n"
            f"Evidence IDs: {', '.join(ep.evidence_ids) if ep.evidence_ids else 'TBD'}",
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
            item.clue_reveals[:60] + "..." if len(item.clue_reveals) > 60 else item.clue_reveals,
        )
    console.print(table)


# --- Pipeline Steps ---


def _step_truth(case: Case, suspect_count: int | None, episode_count: int | None, difficulty: str | None) -> None:
    """Generate or regenerate the case truth."""
    while True:
        console.print("\n[bold blue]Generating case truth...[/bold blue]")
        case.truth = generate_truth(
            premise=case.premise,
            language=case.language,
            suspect_count=suspect_count,
            episode_count=episode_count,
            difficulty=difficulty,
        )
        if case.truth.victim.name and case.title is None:
            case.title = f"The {case.truth.victim.name} Case"

        _display_truth(case)

        action, instructions = _confirm_or_edit()
        if action == "accept":
            case.generation_state.phase = GenerationPhase.SUSPECTS
            case.generation_state.current_step_detail = None
            save_case(case)
            return
        # For both "regenerate" and "edit", we loop again
        # (edit instructions would be used in a future refinement)


def _step_suspects(case: Case) -> None:
    while True:
        console.print("\n[bold blue]Generating suspects...[/bold blue]")
        case.suspects = generate_suspects(case)
        _display_suspects(case)

        action, instructions = _confirm_or_edit()
        if action == "accept":
            case.generation_state.phase = GenerationPhase.SUSPECT_PORTRAITS
            case.generation_state.current_step_detail = None
            save_case(case)
            return


def _step_suspect_portraits(case: Case) -> None:
    """Generate portrait images for each suspect (resumable)."""
    from caseclosed.generation.suspects import generate_suspect_portrait_prompt
    from caseclosed.llm.client import generate_image
    from caseclosed.persistence import save_image

    remaining = [s for s in case.suspects if s.portrait_filename is None]
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
                image_data = generate_image(suspect.portrait_prompt)
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
    while True:
        console.print("\n[bold blue]Generating episodes...[/bold blue]")
        case.episodes = generate_episodes(case)
        _display_episodes(case)

        action, instructions = _confirm_or_edit()
        if action == "accept":
            case.generation_state.phase = GenerationPhase.EVIDENCE_PLAN
            case.generation_state.current_step_detail = None
            save_case(case)
            return


def _step_evidence_plan(case: Case) -> None:
    while True:
        console.print("\n[bold blue]Planning evidence graph...[/bold blue]")
        case.evidence_plan = generate_evidence_plan(case)

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


def _step_evidence_content(case: Case) -> None:
    """Generate evidence content one item at a time (resumable)."""
    already_generated_ids = [e.plan_id for e in case.evidence if hasattr(e, "plan_id")]
    remaining = [
        item for item in case.evidence_plan
        if item.id not in already_generated_ids
    ]

    total = len(case.evidence_plan)
    done = total - len(remaining)

    for i, plan_item in enumerate(remaining, start=done + 1):
        console.print(f"\n[bold blue]Generating evidence [{i}/{total}]: {plan_item.title}[/bold blue]")
        case.generation_state.current_step_detail = f"evidence:{i}/{total}"

        evidence = generate_evidence_content(
            case, plan_item, already_generated_ids
        )
        case.evidence.append(evidence)
        already_generated_ids.append(plan_item.id)
        save_case(case)  # Save after each item for resumability

        console.print(f"  [green]✓[/green] Generated: {plan_item.title} ({plan_item.type})")

    case.generation_state.phase = GenerationPhase.IMAGES
    case.generation_state.current_step_detail = None
    save_case(case)
    console.print("\n[bold green]All evidence content generated![/bold green]")


def _step_images(case: Case) -> None:
    """Generate images for ImageEvidence items (resumable)."""
    image_items = [
        e for e in case.evidence
        if isinstance(e, ImageEvidence) and e.image_filename is None
    ]

    if not image_items:
        console.print("[dim]No images to generate.[/dim]")
        case.generation_state.phase = GenerationPhase.COMPLETE
        save_case(case)
        return

    total = len([e for e in case.evidence if isinstance(e, ImageEvidence)])
    done = total - len(image_items)

    for i, img_evidence in enumerate(image_items, start=done + 1):
        console.print(f"\n[bold blue]Generating image [{i}/{total}]: {img_evidence.caption}[/bold blue]")
        case.generation_state.current_step_detail = f"image:{i}/{total}"

        try:
            filename = generate_evidence_image(case, img_evidence)
            img_evidence.image_filename = filename
            console.print(f"  [green]✓[/green] Saved: {filename}")
        except Exception as e:
            console.print(f"  [red]✗ Image generation failed: {e}[/red]")
            console.print("  [dim]Skipping — you can regenerate later with 'edit'[/dim]")

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
