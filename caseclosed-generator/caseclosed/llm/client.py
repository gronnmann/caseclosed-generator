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
                print(e.with_traceback)

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
