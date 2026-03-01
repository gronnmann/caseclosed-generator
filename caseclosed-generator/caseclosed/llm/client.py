import time

from openai import OpenAI
from pydantic import BaseModel
from rich.console import Console

from caseclosed.config import settings

console = Console()

MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 2

_client: OpenAI | None = None


def get_client() -> OpenAI:
    """Get or create the OpenRouter-backed OpenAI client."""
    global _client
    if _client is None:
        _client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=settings.openrouter_api_key,
        )
    return _client


def generate_structured[T: BaseModel](
    response_model: type[T],
    messages: list[dict[str, str]],
    model: str | None = None,
) -> T:
    """Generate a structured response parsed into a Pydantic model.

    Uses OpenRouter's structured output support via the openai SDK.
    Retries up to MAX_RETRIES times on transient failures.
    """
    client = get_client()
    model = model or settings.default_model

    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            completion = client.chat.completions.parse(
                model=model,
                messages=messages,  # type: ignore[arg-type]
                response_format=response_model,
            )

            message = completion.choices[0].message
            if message.parsed is None:
                refusal = getattr(message, "refusal", None)
                raise RuntimeError(
                    f"LLM did not return structured output. Refusal: {refusal}"
                )
            return message.parsed
        except Exception as e:
            last_error = e
            if attempt < MAX_RETRIES:
                console.print(
                    f"  [yellow]Attempt {attempt}/{MAX_RETRIES} failed: {e}[/yellow]"
                )
                console.print(
                    f"  [dim]Retrying in {RETRY_DELAY_SECONDS}s...[/dim]"
                )
                time.sleep(RETRY_DELAY_SECONDS)
            else:
                console.print(
                    f"  [red]Attempt {attempt}/{MAX_RETRIES} failed: {e}[/red]"
                )

    raise last_error  # type: ignore[misc]


def generate_text(
    messages: list[dict[str, str]],
    model: str | None = None,
) -> str:
    """Generate a plain text response. Retries up to MAX_RETRIES times."""
    client = get_client()
    model = model or settings.default_model

    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            completion = client.chat.completions.create(
                model=model,
                messages=messages,  # type: ignore[arg-type]
            )
            content = completion.choices[0].message.content
            if content is None:
                raise RuntimeError("LLM returned empty response")
            return content
        except Exception as e:
            last_error = e
            if attempt < MAX_RETRIES:
                console.print(
                    f"  [yellow]Attempt {attempt}/{MAX_RETRIES} failed: {e}[/yellow]"
                )
                console.print(
                    f"  [dim]Retrying in {RETRY_DELAY_SECONDS}s...[/dim]"
                )
                time.sleep(RETRY_DELAY_SECONDS)
            else:
                console.print(
                    f"  [red]Attempt {attempt}/{MAX_RETRIES} failed: {e}[/red]"
                )

    raise last_error  # type: ignore[misc]


def generate_image(
    prompt: str,
    model: str | None = None,
) -> bytes:
    """Generate an image via OpenRouter image model. Returns raw image bytes.

    Retries up to MAX_RETRIES times on transient failures.
    """
    import base64

    client = get_client()
    model = model or settings.default_image_model

    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.images.generate(
                model=model,
                prompt=prompt,
                n=1,
                size="1024x1024",
                response_format="b64_json",
            )

            b64_data = response.data[0].b64_json
            if b64_data is None:
                raise RuntimeError("Image generation returned no data")
            return base64.b64decode(b64_data)
        except Exception as e:
            last_error = e
            if attempt < MAX_RETRIES:
                console.print(
                    f"  [yellow]Attempt {attempt}/{MAX_RETRIES} failed: {e}[/yellow]"
                )
                console.print(
                    f"  [dim]Retrying in {RETRY_DELAY_SECONDS}s...[/dim]"
                )
                time.sleep(RETRY_DELAY_SECONDS)
            else:
                console.print(
                    f"  [red]Attempt {attempt}/{MAX_RETRIES} failed: {e}[/red]"
                )

    raise last_error  # type: ignore[misc]
