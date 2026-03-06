import time
from datetime import datetime
from pathlib import Path

from openai import OpenAI
from pydantic import BaseModel
from rich.console import Console

from caseclosed.config import settings

ERROR_LOG_DIR = Path("./logs/llm_errors")

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
    last_raw_content: str | None = None
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
            # Try to extract raw LLM response content for debugging
            raw = _extract_raw_content(e)
            if raw:
                last_raw_content = raw
            _log_llm_error(response_model.__name__, attempt, messages, e, last_raw_content)
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


def _extract_raw_content(error: Exception) -> str | None:
    """Try to extract the raw LLM response string from a validation error."""
    # Pydantic ValidationError stores the original input
    if hasattr(error, "errors"):
        for err in error.errors():
            inp = err.get("input")
            if isinstance(inp, str) and len(inp) > 50:
                return inp
    # Check string representation for input_value
    err_str = str(error)
    if "input_value=" in err_str:
        start = err_str.find("input_value='")
        if start != -1:
            start += len("input_value='")
            end = err_str.find("', input_type=", start)
            if end != -1:
                return err_str[start:end]
    return None


def _log_llm_error(
    model_name: str,
    attempt: int,
    messages: list[dict[str, str]],
    error: Exception,
    raw_content: str | None = None,
) -> None:
    """Write a failed LLM response to a log file for debugging."""
    try:
        ERROR_LOG_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{ts}_{model_name}_attempt{attempt}.txt"
        path = ERROR_LOG_DIR / filename

        error_detail = ""
        if hasattr(error, "__cause__") and error.__cause__:
            error_detail += f"Cause: {error.__cause__}\n"
        for attr in ("response", "body"):
            if hasattr(error, attr):
                error_detail += f"{attr}: {getattr(error, attr)}\n"

        content = (
            f"Model: {model_name}\n"
            f"Attempt: {attempt}/{MAX_RETRIES}\n"
            f"Time: {ts}\n"
            f"Error type: {type(error).__name__}\n"
            f"Error: {error}\n"
            f"\n{'='*60}\n"
            f"ERROR DETAILS:\n{error_detail}\n"
        )
        if raw_content:
            content += (
                f"\n{'='*60}\n"
                f"RAW LLM RESPONSE (full):\n{raw_content}\n"
            )
        content += f"\n{'='*60}\nMESSAGES SENT:\n"
        for msg in messages:
            role = msg.get("role", "?")
            text = msg.get("content", "")[:5000]
            content += f"\n--- {role} ---\n{text}\n"

        path.write_text(content, encoding="utf-8")
        console.print(f"  [dim]Error logged to {path}[/dim]")
    except Exception:
        pass  # Don't fail on logging failures


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
    aspect_ratio: str | None = None,
    reference_images: list[bytes] | None = None,
) -> bytes:
    """Generate an image via OpenRouter's chat completions endpoint.

    OpenRouter uses the /chat/completions endpoint with modalities=["image","text"]
    instead of a dedicated /images/generations endpoint.
    Returns raw image bytes. Retries up to MAX_RETRIES times.

    If reference_images is provided, they are included as base64-encoded image_url
    content blocks alongside the text prompt for visual consistency.
    """
    import base64

    import httpx

    model = model or settings.default_image_model

    # Build multimodal content if reference images provided
    if reference_images:
        content: list[dict] = []
        for ref_bytes in reference_images:
            b64 = base64.b64encode(ref_bytes).decode("ascii")
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64}"},
            })
        content.append({"type": "text", "text": prompt})
        messages = [{"role": "user", "content": content}]
    else:
        messages = [{"role": "user", "content": prompt}]

    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            # OpenRouter image generation goes through chat completions
            response = httpx.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.openrouter_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": messages,
                    "modalities": settings.image_model_modalities,
                    **({
                        "image_config": {"aspect_ratio": aspect_ratio}
                    } if aspect_ratio else {}),
                },
                timeout=120.0,
            )
            response.raise_for_status()
            result = response.json()

            # Extract image from response
            message = result["choices"][0]["message"]
            images = message.get("images")
            if not images:
                raise RuntimeError(
                    f"No images in response. Content: {str(message.get('content', ''))[:200]}"
                )

            image_url: str = images[0]["image_url"]["url"]

            # Handle base64 data URLs
            if image_url.startswith("data:"):
                # Format: data:image/png;base64,<data>
                b64_part = image_url.split(",", 1)[1]
                return base64.b64decode(b64_part)

            # Handle regular URLs — download the image
            img_response = httpx.get(image_url, timeout=60.0)
            img_response.raise_for_status()
            return img_response.content
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


def edit_image(
    image_bytes: bytes,
    edit_instructions: str,
    model: str | None = None,
) -> bytes:
    """Edit an existing image by sending it with edit instructions.

    Attaches the original image as a reference and asks the model to modify it.
    Returns raw image bytes of the edited result.
    """
    import base64

    import httpx

    model = model or settings.default_image_model
    b64 = base64.b64encode(image_bytes).decode("ascii")

    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{b64}"},
                },
                {
                    "type": "text",
                    "text": f"Edit this image according to these instructions: {edit_instructions}",
                },
            ],
        }
    ]

    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = httpx.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.openrouter_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": messages,
                    "modalities": settings.image_model_modalities,
                },
                timeout=120.0,
            )
            response.raise_for_status()
            result = response.json()

            message = result["choices"][0]["message"]
            images = message.get("images")
            if not images:
                raise RuntimeError(
                    f"No images in response. Content: {str(message.get('content', ''))[:200]}"
                )

            image_url: str = images[0]["image_url"]["url"]

            if image_url.startswith("data:"):
                b64_part = image_url.split(",", 1)[1]
                return base64.b64decode(b64_part)

            img_response = httpx.get(image_url, timeout=60.0)
            img_response.raise_for_status()
            return img_response.content
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
