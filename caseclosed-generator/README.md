# CaseClosed Generator

A modular murder mystery engine that generates "Case Closed" style detective games — where players step into the role of a lead investigator, sift through physical evidence, and catch a killer.

## How It Works

The engine uses a **logic-first approach** powered by LLM (via OpenRouter):

1. **Core Truth** — Establishes the unshakeable facts: who died, how, who killed them, and why
2. **Suspects** — Generates suspects with secrets, conflicting alibis, and red-herring motives. Portrait images are generated for each suspect.
3. **Episodes** — Builds progressive chapters with objectives that unlock the next stage
4. **Evidence Plan** — Designs the full evidence graph with cross-episode reuse before generating content
5. **Evidence Content** — Generates authentic documents: interrogation transcripts, POI forms, letters, photos, lab reports, etc.
6. **Images** — Generates AI images for crime scenes, physical evidence, and other visual clues (suspect portraits are used for visual consistency)

Generation is **resumable** — every step saves to disk. Stop anytime, pick up later with `resume`.

Everything is **editable** at any point — via CLI/LLM or by editing `case.json` directly.

## Setup

```bash
# Install dependencies
uv sync

# Configure (copy and fill in your OpenRouter API key)
cp .env.example .env
```

### Configuration (`.env`)

```
CASECLOSED_OPENROUTER_API_KEY=your-key-here
CASECLOSED_DEFAULT_MODEL=google/gemini-2.5-flash
CASECLOSED_DEFAULT_IMAGE_MODEL=openai/dall-e-3
CASECLOSED_LANGUAGE=en
CASECLOSED_CASES_DIR=./cases
```

## Usage

### Create a new case

```bash
uv run python main.py new --premise "A murder at a remote fjord cabin during a winter retreat"
```

Options:
- `--premise` / `-p` — The mystery premise (required)
- `--suspects` / `-s` — Number of suspects
- `--episodes` / `-e` — Number of episodes
- `--difficulty` / `-d` — Difficulty: easy, medium, hard
- `--language` / `-l` — Content language (default: from config)

### Resume an interrupted generation

```bash
uv run python main.py resume           # Pick from in-progress cases
uv run python main.py resume abc123    # Resume specific case
```

### List cases

```bash
uv run python main.py list
```

### Show a case

```bash
uv run python main.py show abc123          # Player-safe view
uv run python main.py show abc123 --truth  # Director's view with hidden truth
```

### Edit any part of a case

```bash
uv run python main.py edit abc123 truth
uv run python main.py edit abc123 suspect "Ingrid Solheim"
uv run python main.py edit abc123 episode 2
uv run python main.py edit abc123 evidence crime-scene-photo
uv run python main.py edit abc123 evidence-plan
```

You can also edit `case.json` directly — it's the single source of truth.

## Output Structure

```
cases/
└── abc123/
    ├── case.json       # Full case: truth, suspects, episodes, evidence plan & content, state
    └── images/
        ├── portrait-ingrid.png
        ├── portrait-lars.png
        ├── crime-scene-photo.png
        └── ...
```

## Evidence Types

- **Interrogation Report** — Police interview transcripts
- **Person of Interest Form** — Structured suspect details with portrait photo
- **Letter** — Introduction, solution, or narrative letters
- **Image** — AI-generated crime scene photos, physical evidence, etc.
- **Raw Text** — Newspaper articles, lab reports, autopsy reports, phone messages, notes. Will be later created manually, or compiled through typst, latex or HTML.

## Development

```bash
# Run linter
uv tool run ruff check

# Run tests
uv run pytest tests/
```
