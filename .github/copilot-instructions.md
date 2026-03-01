# GitHub Copilot Instructions for Syncly

## Backend

### Packages used
- Click
- Pydantic
- pydantic-settings for configuration management
- uv (for package management)

### Running the code
`uv` is used as the package manager. This means that:
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
- Use generic types for flexibility: `BaseOTPUserTable[ID]`, `OTPDatabase[UserType]`
- Prefer explicit types over `Any` when possible
- Use `Any` from `typing` module when truly dynamic types are needed