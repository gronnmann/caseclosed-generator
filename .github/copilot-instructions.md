# GitHub Copilot Instructions for CaseClosed Generator

## Overview
A modular murder mystery engine that generates "Case Closed" style detective games.
Uses LLM (via OpenRouter) to generate multi-episode mysteries with a logic-first approach.

## Backend

### Packages used
- Typer (CLI framework)
- Pydantic
- pydantic-settings for configuration management
- uv (for package management)
- openai package with OpenRouter for LLM interactions
- rich for terminal display
- httpx for HTTP requests

### Running the code
`uv` is used as the package manager. This means that:
- To run the CLI: `uv run python main.py`
- To run tests: `uv run pytest tests/`
- To run ruff, do `uv tool run ruff check`

### Installing, changing dependencies etc
- NEVER edit `pyproject.toml` or `uv.lock` directly.
- Use `uv add <package>` to add a new dependency.
- Use `uv remove <package>` to remove a dependency.

### Code Style & Standards

#### Syntax
- Use modern type hints syntax:
  - `str | None` instead of `Optional[str]`
  - `dict[str, Any]` instead of `Dict[str, Any]`
  - `list[int]` instead of `List[int]`
  - Use `type` instead of `Type` for type annotations

#### Type Hints
- ALL functions must have complete type hints (parameters and return types)
- Prefer explicit types over `Any` when possible
- Use `Any` from `typing` module when truly dynamic types are needed

#### LLM interactions
When interacting with LLMs, use the OpenRouter API via the `openai` package.
The client is configured with `base_url="https://openrouter.ai/api/v1"`.

When generating structured outputs, USE structured outputs via `client.chat.completions.parse()`:
```python
from openai import OpenAI
from pydantic import BaseModel

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=settings.openrouter_api_key,
)

class CalendarEvent(BaseModel):
    name: str
    date: str
    participants: list[str]

completion = client.chat.completions.parse(
    model="google/gemini-2.5-flash",
    messages=[
        {"role": "system", "content": "Extract the event information."},
        {"role": "user", "content": "Alice and Bob are going to a science fair on Friday."},
    ],
    response_format=CalendarEvent,
)

event = completion.choices[0].message.parsed
```

### Project Structure
```
caseclosed/
├── __init__.py
├── cli.py              # Typer CLI entry point
├── config.py           # pydantic-settings configuration
├── models/             # Pydantic domain models
├── generation/         # LLM generation pipeline & generators
├── llm/                # OpenRouter client & prompts
└── persistence.py      # Save/load case state to disk
```