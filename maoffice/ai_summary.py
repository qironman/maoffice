"""AI summarization via local OpenAI-compatible server."""

import os
from openai import OpenAI

SYSTEM_PROMPT = (
    "You are a helpful assistant for a dental practice. "
    "Summarize the day's activity concisely in 3–5 sentences, "
    "highlighting key metrics, any notable patient situations, and any action items for tomorrow. "
    "Keep the tone professional and friendly."
)


def get_client() -> OpenAI:
    """Return an OpenAI client pointed at the local AI server."""
    base_url = os.environ.get("AI_BASE_URL", "http://localhost:4141/v1")
    # Local server typically doesn't need a real key, but the library requires one
    api_key = os.environ.get("AI_API_KEY", "local")
    return OpenAI(base_url=base_url, api_key=api_key)


def summarize(raw_text: str) -> str:
    """Summarize raw daily data using the local AI model.

    Args:
        raw_text: Raw text describing the day's activity (appointments, notes, etc.).

    Returns:
        A concise AI-generated summary string.

    Raises:
        Exception: If the AI server is unreachable or returns an error.
    """
    model = os.environ.get("AI_MODEL", "llama3")
    client = get_client()

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": raw_text},
        ],
        temperature=0.4,
        max_tokens=300,
    )

    return response.choices[0].message.content.strip()
