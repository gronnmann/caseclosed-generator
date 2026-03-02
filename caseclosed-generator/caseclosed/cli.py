"""Typer CLI for the CaseClosed Generator."""

import uuid
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from caseclosed.generation.pipeline import run_pipeline
from caseclosed.models.case import Case, CaseMetadata, GenerationPhase, GenerationState
from caseclosed.persistence import list_cases, load_case, save_case
from caseclosed.config import settings

app = typer.Typer(
    name="caseclosed",
    help="CaseClosed Generator — a modular murder mystery engine.",
    no_args_is_help=True,
)
console = Console()


def _short_id() -> str:
    return uuid.uuid4().hex[:8]


@app.command()
def new(
    premise: Annotated[str, typer.Option("--premise", "-p", help="The mystery premise")],
    suspects: Annotated[int | None, typer.Option("--suspects", "-s", help="Number of suspects")] = None,
    episodes: Annotated[int | None, typer.Option("--episodes", "-e", help="Number of episodes")] = None,
    difficulty: Annotated[str | None, typer.Option("--difficulty", "-d", help="Difficulty: easy, medium, hard")] = None,
    language: Annotated[str | None, typer.Option("--language", "-l", help="Content language")] = None,
) -> None:
    """Create a new murder mystery case and start generation."""
    case_id = _short_id()
    lang = language or settings.language

    case = Case(
        id=case_id,
        premise=premise,
        language=lang,
        generation_state=GenerationState(phase=GenerationPhase.PREMISE),
        metadata=CaseMetadata(
            model_used=settings.default_model,
            image_model_used=settings.default_image_model,
            difficulty=difficulty,
        ),
    )

    save_case(case)
    console.print(f"[bold green]Created case:[/bold green] {case_id}")
    console.print(f"[dim]Premise: {premise}[/dim]")
    console.print()

    run_pipeline(case, suspect_count=suspects, episode_count=episodes, difficulty=difficulty)


@app.command()
def resume(
    case_id: Annotated[str | None, typer.Argument(help="Case ID to resume")] = None,
) -> None:
    """Resume generating an in-progress case."""
    if case_id is None:
        # Show in-progress cases and let user pick
        cases = [c for c in list_cases() if c.generation_state.phase != GenerationPhase.COMPLETE]
        if not cases:
            console.print("[yellow]No in-progress cases found.[/yellow]")
            raise typer.Exit()

        console.print("[bold]In-progress cases:[/bold]")
        for i, c in enumerate(cases, 1):
            console.print(f"  {i}. [cyan]{c.id}[/cyan] — {c.premise[:60]} [{c.generation_state.phase}]")

        choice = console.input("\n[bold yellow]Select case number:[/bold yellow] ").strip()
        try:
            idx = int(choice) - 1
            case_id = cases[idx].id
        except (ValueError, IndexError):
            console.print("[red]Invalid selection.[/red]")
            raise typer.Exit(code=1)

    case = load_case(case_id)
    console.print(f"[bold green]Resuming case:[/bold green] {case_id} (phase: {case.generation_state.phase})")
    run_pipeline(case)


@app.command(name="list")
def list_cmd() -> None:
    """List all generated cases."""
    cases = list_cases()
    if not cases:
        console.print("[yellow]No cases found.[/yellow]")
        return

    table = Table(title="Cases")
    table.add_column("ID", style="cyan")
    table.add_column("Title")
    table.add_column("Premise")
    table.add_column("Phase", style="magenta")
    table.add_column("Language")

    for c in cases:
        table.add_row(
            c.id,
            c.title or "-",
            c.premise[:50] + ("..." if len(c.premise) > 50 else ""),
            c.generation_state.phase.value,
            c.language,
        )
    console.print(table)


@app.command()
def show(
    case_id: Annotated[str, typer.Argument(help="Case ID to display")],
    truth: Annotated[bool, typer.Option("--truth", "-t", help="Show hidden truth")] = False,
) -> None:
    """Display a generated case."""
    case = load_case(case_id)

    console.print(Panel(
        f"[bold]{case.title or 'Untitled'}[/bold]\n"
        f"Premise: {case.premise}\n"
        f"Language: {case.language}\n"
        f"Phase: {case.generation_state.phase}",
        title=f"Case: {case.id}",
    ))

    if truth and case.truth:
        from caseclosed.generation.pipeline import _display_truth
        _display_truth(case)

    if case.suspects:
        console.print(f"\n[bold]Suspects ({len(case.suspects)}):[/bold]")
        for s in case.suspects:
            tag = " [red](KILLER)[/red]" if truth and s.is_killer else ""
            console.print(f"  • {s.name} — {s.occupation}{tag}")

    if case.episodes:
        console.print(f"\n[bold]Episodes ({len(case.episodes)}):[/bold]")
        for ep in case.episodes:
            console.print(f"  {ep.number}. {ep.title} — {ep.objective}")

    if case.evidence_plan:
        console.print(f"\n[bold]Evidence plan ({len(case.evidence_plan)} items):[/bold]")
        for item in case.evidence_plan:
            console.print(f"  • [{item.type}] {item.title} (ep {item.introduced_in_episode})")

    if case.evidence:
        console.print(f"\n[bold]Evidence content ({len(case.evidence)} items generated):[/bold]")


@app.command()
def edit(
    case_id: Annotated[str, typer.Argument(help="Case ID to edit")],
    target: Annotated[str, typer.Argument(help="What to edit: truth, personnel, suspect, episode, evidence, evidence-plan")],
    name_or_id: Annotated[str | None, typer.Argument(help="Suspect name or evidence ID (when applicable)")] = None,
) -> None:
    """Edit a specific part of a case using LLM assistance."""
    case = load_case(case_id)

    if target == "truth":
        _edit_truth(case)
    elif target == "personnel":
        _edit_personnel(case)
    elif target == "suspect":
        if not name_or_id:
            console.print("[red]Please specify a suspect name.[/red]")
            raise typer.Exit(code=1)
        _edit_suspect(case, name_or_id)
    elif target == "episode":
        if not name_or_id:
            console.print("[red]Please specify an episode number.[/red]")
            raise typer.Exit(code=1)
        _edit_episode(case, int(name_or_id))
    elif target == "evidence":
        if not name_or_id:
            console.print("[red]Please specify an evidence ID.[/red]")
            raise typer.Exit(code=1)
        _edit_evidence(case, name_or_id)
    elif target == "evidence-plan":
        _edit_evidence_plan(case)
    else:
        console.print(f"[red]Unknown target: {target}[/red]")
        console.print("Valid targets: truth, personnel, suspect, episode, evidence, evidence-plan")
        raise typer.Exit(code=1)


def _edit_truth(case: Case) -> None:
    from caseclosed.generation.pipeline import _display_truth
    if case.truth:
        _display_truth(case)

    instructions = console.input("[bold yellow]Edit instructions:[/bold yellow] ").strip()
    if not instructions:
        console.print("[dim]No instructions provided, skipping.[/dim]")
        return

    from caseclosed.llm.client import generate_structured
    from caseclosed.models.case import CaseTruth

    messages = [
        {"role": "system", "content": f"You are editing a murder mystery case truth. Generate in {case.language}."},
        {"role": "user", "content": (
            f"Current truth:\n{case.truth.model_dump_json(indent=2) if case.truth else 'None'}\n\n"
            f"Edit instructions: {instructions}\n\n"
            "Generate the updated truth, applying the requested changes while keeping "
            "everything else consistent."
        )},
    ]
    case.truth = generate_structured(CaseTruth, messages)
    save_case(case)
    _display_truth(case)
    _suggest_reconciliation(case, "truth")


def _edit_personnel(case: Case) -> None:
    if case.personnel:
        from caseclosed.generation.pipeline import _display_truth
        _display_truth(case)

    instructions = console.input("[bold yellow]Edit instructions:[/bold yellow] ").strip()
    if not instructions:
        console.print("[dim]No instructions provided, skipping.[/dim]")
        return

    from caseclosed.llm.client import generate_structured
    from caseclosed.models.case import CasePersonnel

    messages = [
        {"role": "system", "content": f"You are editing case personnel names. Generate in {case.language}."},
        {"role": "user", "content": (
            f"Current personnel:\n{case.personnel.model_dump_json(indent=2) if case.personnel else 'None'}\n\n"
            f"Edit instructions: {instructions}\n\n"
            "Generate the updated personnel."
        )},
    ]
    case.personnel = generate_structured(CasePersonnel, messages)
    save_case(case)
    from caseclosed.generation.pipeline import _display_truth
    _display_truth(case)
    console.print("[green]\u2713 Personnel updated.[/green]")


def _edit_suspect(case: Case, name: str) -> None:
    suspect = next((s for s in case.suspects if s.name.lower() == name.lower()), None)
    if not suspect:
        console.print(f"[red]Suspect not found: {name}[/red]")
        console.print(f"Available: {', '.join(s.name for s in case.suspects)}")
        return

    console.print(Panel(f"{suspect.model_dump_json(indent=2)}", title=f"Suspect: {suspect.name}"))
    instructions = console.input("[bold yellow]Edit instructions:[/bold yellow] ").strip()
    if not instructions:
        return

    from caseclosed.llm.client import generate_structured
    from caseclosed.models.suspect import Suspect

    messages = [
        {"role": "system", "content": f"You are editing a suspect in a murder mystery. Generate in {case.language}."},
        {"role": "user", "content": (
            f"Current suspect:\n{suspect.model_dump_json(indent=2)}\n\n"
            f"Case truth:\n{case.truth.model_dump_json(indent=2) if case.truth else 'N/A'}\n\n"
            f"Edit instructions: {instructions}\n\n"
            "Generate the updated suspect."
        )},
    ]
    updated = generate_structured(Suspect, messages)
    idx = case.suspects.index(suspect)
    case.suspects[idx] = updated
    save_case(case)
    console.print(f"[green]✓ Updated suspect: {updated.name}[/green]")
    _suggest_reconciliation(case, f"suspect:{name}")


def _edit_episode(case: Case, number: int) -> None:
    episode = next((e for e in case.episodes if e.number == number), None)
    if not episode:
        console.print(f"[red]Episode {number} not found.[/red]")
        return

    console.print(Panel(f"{episode.model_dump_json(indent=2)}", title=f"Episode {number}"))
    instructions = console.input("[bold yellow]Edit instructions:[/bold yellow] ").strip()
    if not instructions:
        return

    from caseclosed.llm.client import generate_structured
    from caseclosed.models.episode import Episode

    messages = [
        {"role": "system", "content": f"You are editing an episode. Generate in {case.language}."},
        {"role": "user", "content": (
            f"Current episode:\n{episode.model_dump_json(indent=2)}\n\n"
            f"Edit instructions: {instructions}\n\n"
            "Generate the updated episode."
        )},
    ]
    updated = generate_structured(Episode, messages)
    idx = case.episodes.index(episode)
    case.episodes[idx] = updated
    save_case(case)
    console.print(f"[green]✓ Updated episode {number}[/green]")


def _edit_evidence(case: Case, evidence_id: str) -> None:
    evidence_item = next((e for e in case.evidence if getattr(e, "plan_id", None) == evidence_id), None)
    if not evidence_item:
        console.print(f"[red]Evidence not found: {evidence_id}[/red]")
        ids = [getattr(e, "plan_id", "?") for e in case.evidence]
        console.print(f"Available: {', '.join(ids)}")
        return

    console.print(Panel(f"{evidence_item.model_dump_json(indent=2)}", title=f"Evidence: {evidence_id}"))
    instructions = console.input("[bold yellow]Edit instructions:[/bold yellow] ").strip()
    if not instructions:
        return

    from caseclosed.llm.client import generate_structured

    # Determine the evidence type model
    from caseclosed.generation.evidence import _TYPE_MAP
    plan_item = next((p for p in case.evidence_plan if p.id == evidence_id), None)
    if not plan_item:
        console.print("[red]Plan item not found for this evidence.[/red]")
        return

    model_class = _TYPE_MAP[plan_item.type]
    messages = [
        {"role": "system", "content": f"You are editing evidence in a murder mystery. Generate in {case.language}."},
        {"role": "user", "content": (
            f"Current evidence:\n{evidence_item.model_dump_json(indent=2)}\n\n"
            f"Case truth:\n{case.truth.model_dump_json(indent=2) if case.truth else 'N/A'}\n\n"
            f"Edit instructions: {instructions}\n\n"
            "Generate the updated evidence, keeping it consistent with the case truth."
        )},
    ]
    updated = generate_structured(model_class, messages)
    idx = case.evidence.index(evidence_item)
    case.evidence[idx] = updated
    save_case(case)
    console.print(f"[green]✓ Updated evidence: {evidence_id}[/green]")


def _edit_evidence_plan(case: Case) -> None:
    from caseclosed.generation.pipeline import _display_evidence_plan
    _display_evidence_plan(case)

    instructions = console.input("[bold yellow]Edit instructions:[/bold yellow] ").strip()
    if not instructions:
        return

    from caseclosed.llm.client import generate_structured
    from caseclosed.generation.evidence_plan import EvidencePlanResponse

    messages = [
        {"role": "system", "content": f"You are editing an evidence plan. Generate in {case.language}."},
        {"role": "user", "content": (
            "Current evidence plan:\n"
            + "\n".join(item.model_dump_json() for item in case.evidence_plan)
            + f"\n\nEdit instructions: {instructions}\n\n"
            "Generate the updated evidence plan."
        )},
    ]
    response = generate_structured(EvidencePlanResponse, messages)
    case.evidence_plan = response.evidence_plan
    save_case(case)
    console.print("[green]✓ Updated evidence plan[/green]")
    _suggest_reconciliation(case, "evidence-plan")


def _suggest_reconciliation(case: Case, edited_target: str) -> None:
    """Suggest downstream items that might need updating after an edit."""
    suggestions: list[str] = []

    if edited_target == "truth":
        if case.suspects:
            suggestions.append(f"  • {len(case.suspects)} suspects (alibis may need updating)")
        if case.episodes:
            suggestions.append(f"  • {len(case.episodes)} episodes")
        if case.evidence:
            suggestions.append(f"  • {len(case.evidence)} evidence items")
    elif edited_target.startswith("suspect:"):
        name = edited_target.split(":", 1)[1]
        related_evidence = [
            e for e in case.evidence_plan if e.suspect_name and e.suspect_name.lower() == name.lower()
        ]
        if related_evidence:
            suggestions.append(f"  • {len(related_evidence)} evidence items linked to {name}")

    if suggestions:
        console.print("\n[bold yellow]Potentially affected items:[/bold yellow]")
        for s in suggestions:
            console.print(s)
        console.print("[dim]Use 'caseclosed edit' to update these if needed. Or edit case.json directly.[/dim]")


# --- Redo Command ---

_REDO_TARGETS = [
    "truth", "personnel", "suspects", "portraits", "portrait",
    "episodes", "evidence-plan", "evidence", "image", "images",
]


@app.command()
def redo(
    case_id: Annotated[str, typer.Argument(help="Case ID")],
    target: Annotated[str, typer.Argument(help="What to redo: truth, personnel, suspects, portraits, portrait, episodes, evidence-plan, evidence, image, images")],
    name_or_id: Annotated[str | None, typer.Argument(help="Suspect name (for portrait) or evidence ID (for evidence/image)")] = None,
) -> None:
    """Regenerate a specific part of a case from scratch."""
    case = load_case(case_id)

    if target not in _REDO_TARGETS:
        console.print(f"[red]Unknown target: {target}[/red]")
        console.print(f"Valid targets: {', '.join(_REDO_TARGETS)}")
        raise typer.Exit(code=1)

    if target == "truth":
        _redo_truth(case)
    elif target == "personnel":
        _redo_personnel(case)
    elif target == "suspects":
        _redo_suspects(case)
    elif target == "portraits":
        _redo_portraits(case)
    elif target == "portrait":
        if not name_or_id:
            console.print("[red]Please specify a suspect name.[/red]")
            raise typer.Exit(code=1)
        _redo_portrait(case, name_or_id)
    elif target == "episodes":
        _redo_episodes(case)
    elif target == "evidence-plan":
        _redo_evidence_plan(case)
    elif target == "evidence":
        if not name_or_id:
            console.print("[red]Please specify an evidence ID.[/red]")
            raise typer.Exit(code=1)
        _redo_evidence(case, name_or_id)
    elif target == "image":
        if not name_or_id:
            console.print("[red]Please specify an evidence ID.[/red]")
            raise typer.Exit(code=1)
        _redo_image(case, name_or_id)
    elif target == "images":
        _redo_images(case)


def _redo_truth(case: Case) -> None:
    from caseclosed.generation.truth import generate_truth
    from caseclosed.generation.pipeline import _display_truth

    console.print("[bold blue]Regenerating case truth...[/bold blue]")
    case.truth = generate_truth(
        premise=case.premise,
        language=case.language,
        difficulty=case.metadata.difficulty if case.metadata else None,
    )
    save_case(case)
    _display_truth(case)
    console.print("[green]✓ Truth regenerated.[/green]")
    _suggest_reconciliation(case, "truth")


def _redo_personnel(case: Case) -> None:
    from caseclosed.generation.truth import generate_personnel
    from caseclosed.generation.pipeline import _display_truth

    console.print("[bold blue]Regenerating case personnel...[/bold blue]")
    case.personnel = generate_personnel(case)
    save_case(case)
    _display_truth(case)
    console.print("[green]\u2713 Personnel regenerated.[/green]")


def _redo_suspects(case: Case) -> None:
    from caseclosed.generation.suspects import generate_suspects
    from caseclosed.generation.pipeline import _display_suspects

    console.print("[bold blue]Regenerating suspects...[/bold blue]")
    case.suspects = generate_suspects(case)
    save_case(case)
    _display_suspects(case)
    console.print("[green]✓ Suspects regenerated (portraits cleared).[/green]")


def _redo_portraits(case: Case) -> None:
    """Regenerate portrait images for ALL suspects."""
    from caseclosed.generation.suspects import generate_suspect_portrait_prompt
    from caseclosed.llm.client import generate_image
    from caseclosed.persistence import save_image

    if not case.suspects:
        console.print("[yellow]No suspects to generate portraits for.[/yellow]")
        return

    for i, suspect in enumerate(case.suspects, 1):
        console.print(f"\n[bold blue]Generating portrait [{i}/{len(case.suspects)}]: {suspect.name}[/bold blue]")
        suspect.portrait_prompt = generate_suspect_portrait_prompt(suspect, case.language)
        save_case(case)

        try:
            image_data = generate_image(suspect.portrait_prompt, aspect_ratio="1:1")
            filename = f"portrait-{suspect.name.lower().replace(' ', '-')}.png"
            save_image(case.id, filename, image_data)
            suspect.portrait_filename = filename
            console.print(f"  [green]✓[/green] Saved: {filename}")
        except Exception as e:
            console.print(f"  [red]✗ Portrait generation failed: {e}[/red]")

        save_case(case)

    console.print("\n[green]✓ All portraits regenerated.[/green]")


def _redo_portrait(case: Case, name: str) -> None:
    """Regenerate portrait for a single suspect."""
    from caseclosed.generation.suspects import generate_suspect_portrait_prompt
    from caseclosed.llm.client import generate_image
    from caseclosed.persistence import save_image

    suspect = next((s for s in case.suspects if s.name.lower() == name.lower()), None)
    if not suspect:
        console.print(f"[red]Suspect not found: {name}[/red]")
        console.print(f"Available: {', '.join(s.name for s in case.suspects)}")
        return

    console.print(f"[bold blue]Regenerating portrait: {suspect.name}[/bold blue]")
    suspect.portrait_prompt = generate_suspect_portrait_prompt(suspect, case.language)
    save_case(case)

    try:
        image_data = generate_image(suspect.portrait_prompt, aspect_ratio="1:1")
        filename = f"portrait-{suspect.name.lower().replace(' ', '-')}.png"
        save_image(case.id, filename, image_data)
        suspect.portrait_filename = filename
        save_case(case)
        console.print(f"[green]✓ Portrait saved: {filename}[/green]")
    except Exception as e:
        console.print(f"[red]✗ Portrait generation failed: {e}[/red]")


def _redo_episodes(case: Case) -> None:
    from caseclosed.generation.episodes import generate_episodes
    from caseclosed.generation.pipeline import _display_episodes

    console.print("[bold blue]Regenerating episodes...[/bold blue]")
    case.episodes = generate_episodes(case)
    save_case(case)
    _display_episodes(case)
    console.print("[green]✓ Episodes regenerated.[/green]")


def _redo_evidence_plan(case: Case) -> None:
    from caseclosed.generation.evidence_plan import generate_evidence_plan
    from caseclosed.generation.pipeline import _display_evidence_plan

    console.print("[bold blue]Regenerating evidence plan...[/bold blue]")
    case.evidence_plan = generate_evidence_plan(case)

    for ep in case.episodes:
        ep.evidence_ids = [
            item.id for item in case.evidence_plan
            if item.introduced_in_episode == ep.number
            or ep.number in item.also_used_in_episodes
        ]

    save_case(case)
    _display_evidence_plan(case)
    console.print("[green]✓ Evidence plan regenerated.[/green]")


def _redo_evidence(case: Case, evidence_id: str) -> None:
    from caseclosed.generation.evidence import generate_evidence_content

    plan_item = next((p for p in case.evidence_plan if p.id == evidence_id), None)
    if not plan_item:
        console.print(f"[red]Evidence plan item not found: {evidence_id}[/red]")
        ids = [p.id for p in case.evidence_plan]
        console.print(f"Available: {', '.join(ids)}")
        return

    console.print(f"[bold blue]Regenerating evidence: {plan_item.title}[/bold blue]")
    already_generated_ids = [
        getattr(e, "plan_id", None) for e in case.evidence
        if getattr(e, "plan_id", None) != evidence_id
    ]

    new_evidence = generate_evidence_content(case, plan_item, already_generated_ids)

    # Replace existing or append
    idx = next(
        (i for i, e in enumerate(case.evidence) if getattr(e, "plan_id", None) == evidence_id),
        None,
    )
    if idx is not None:
        case.evidence[idx] = new_evidence
    else:
        case.evidence.append(new_evidence)

    save_case(case)
    console.print(f"[green]✓ Evidence regenerated: {plan_item.title} ({plan_item.type})[/green]")


def _redo_image(case: Case, evidence_id: str) -> None:
    from caseclosed.generation.evidence import generate_evidence_image
    from caseclosed.models.evidence import ImageEvidence

    evidence_item = next(
        (e for e in case.evidence if getattr(e, "plan_id", None) == evidence_id),
        None,
    )
    if not evidence_item:
        console.print(f"[red]Evidence not found: {evidence_id}[/red]")
        return
    if not isinstance(evidence_item, ImageEvidence):
        console.print(f"[red]Evidence '{evidence_id}' is not an image type (it's {evidence_item.type}).[/red]")
        return

    console.print(f"[bold blue]Regenerating image: {evidence_item.caption}[/bold blue]")
    try:
        filename = generate_evidence_image(case, evidence_item)
        evidence_item.image_filename = filename
        save_case(case)
        console.print(f"[green]✓ Image saved: {filename}[/green]")
    except Exception as e:
        console.print(f"[red]✗ Image generation failed: {e}[/red]")


def _redo_images(case: Case) -> None:
    from caseclosed.generation.evidence import generate_evidence_image
    from caseclosed.models.evidence import ImageEvidence

    image_items = [e for e in case.evidence if isinstance(e, ImageEvidence)]
    if not image_items:
        console.print("[yellow]No image evidence items found.[/yellow]")
        return

    for i, img in enumerate(image_items, 1):
        console.print(f"\n[bold blue]Regenerating image [{i}/{len(image_items)}]: {img.caption}[/bold blue]")
        try:
            filename = generate_evidence_image(case, img)
            img.image_filename = filename
            console.print(f"  [green]✓[/green] Saved: {filename}")
        except Exception as e:
            console.print(f"  [red]✗ Image generation failed: {e}[/red]")
        save_case(case)

    console.print(f"\n[green]✓ All {len(image_items)} images regenerated.[/green]")
