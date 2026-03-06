"""Save/load case state to disk.

Cases are stored as:
    cases/<case-id>/case.json     — single JSON file with entire case state
    cases/<case-id>/images/       — generated images
"""

from pathlib import Path

from caseclosed.config import settings
from caseclosed.models.case import Case


def _case_dir(case_id: str) -> Path:
    return settings.cases_dir / case_id


def _case_file(case_id: str) -> Path:
    return _case_dir(case_id) / "case.json"


def images_dir(case_id: str) -> Path:
    path = _case_dir(case_id) / "images"
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_case(case: Case) -> Path:
    """Save a case to disk. Creates directories as needed."""
    case_dir = _case_dir(case.id)
    case_dir.mkdir(parents=True, exist_ok=True)

    case_file = _case_file(case.id)
    case_file.write_text(
        case.model_dump_json(indent=2),
        encoding="utf-8",
    )
    return case_file


def load_case(case_id: str) -> Case:
    """Load a case from disk."""
    case_file = _case_file(case_id)
    if not case_file.exists():
        raise FileNotFoundError(f"Case not found: {case_file}")
    return Case.model_validate_json(case_file.read_text(encoding="utf-8"))


def list_cases() -> list[Case]:
    """List all cases in the cases directory."""
    cases_dir = settings.cases_dir
    if not cases_dir.exists():
        return []

    cases: list[Case] = []
    for case_dir in sorted(cases_dir.iterdir()):
        case_file = case_dir / "case.json"
        if case_file.exists():
            try:
                cases.append(
                    Case.model_validate_json(case_file.read_text(encoding="utf-8"))
                )
            except Exception:
                pass  # Skip malformed case files
    return cases


def save_image(case_id: str, filename: str, data: bytes) -> Path:
    """Save an image file for a case."""
    img_dir = images_dir(case_id)
    img_path = img_dir / filename
    img_path.write_bytes(data)
    return img_path
