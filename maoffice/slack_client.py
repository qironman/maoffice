"""Slack client wrapper for maoffice."""

import os
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError


def get_client() -> WebClient:
    """Return a Slack WebClient authenticated with SLACK_BOT_TOKEN."""
    token = os.environ.get("SLACK_BOT_TOKEN")
    if not token:
        raise ValueError("SLACK_BOT_TOKEN is not set in environment")
    return WebClient(token=token)


def send_message(channel: str, text: str, blocks: list | None = None) -> dict:
    """Send a message to a Slack channel.

    Args:
        channel: Slack channel ID (e.g. "C012AB3CD").
        text: Plain-text fallback (also shown in notifications).
        blocks: Optional Block Kit blocks list for rich formatting.

    Returns:
        The Slack API response dict.

    Raises:
        SlackApiError: If the Slack API returns an error.
        ValueError: If SLACK_BOT_TOKEN is not set.
    """
    client = get_client()
    kwargs = {"channel": channel, "text": text}
    if blocks:
        kwargs["blocks"] = blocks

    try:
        response = client.chat_postMessage(**kwargs)
        return response.data
    except SlackApiError as e:
        raise SlackApiError(
            f"Failed to send message to {channel}: {e.response['error']}",
            e.response,
        ) from e
