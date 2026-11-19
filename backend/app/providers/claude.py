"""Anthropic Claude client: structured JSON outputs, cost tracking, refusal handling."""
import base64
from typing import TypeVar

import anthropic
from pydantic import BaseModel

from ..store import get_secret, get_setting, log_event
from ..util import StageError

T = TypeVar("T", bound=BaseModel)

# USD per million tokens (input, output)
PRICES = {
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-fable-5-2": (8.0, 40.0),
}


def configured():
    return bool(get_secret("ANTHROPIC_API_KEY"))


def client():
    key = get_secret("ANTHROPIC_API_KEY")
    if not key:
        raise StageError("Claude is not configured. Add ANTHROPIC_API_KEY in Integrations.")
    return anthropic.Anthropic(api_key=key, max_retries=3, timeout=600)


def _cost(model, usage):
    pin, pout = PRICES.get(model, (4.0, 20.0))
    return (usage.input_tokens * pin + usage.output_tokens * pout) / 1_000_000


def structured(system: str, user_content, schema: type[T], project_id=None, max_tokens=16000,
               effort=None, purpose="call") -> T:
    """One Claude call that returns a validated pydantic object."""
    prefs = get_setting("preferences")
    model = prefs.get("claude_model", "claude-opus-5-5")
    effort = effort or prefs.get("claude_effort", "medium")
    c = client()
    content = user_content if isinstance(user_content, list) else [{"type": "text", "text": user_content}]
    try:
        resp = c.messages.parse(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": content}],
            output_format=schema,
            output_config={"effort": effort},
        )
    except anthropic.AuthenticationError as e:
        log_event("anthropic", "error", False, f"{purpose}: authentication failed", project_id=project_id)
        raise StageError("Claude rejected the API key (401). Update it in Integrations.") from e
    except anthropic.RateLimitError as e:
        log_event("anthropic", "error", False, f"{purpose}: rate limited", project_id=project_id)
        raise StageError("Claude rate limit reached. Retry this stage in a minute.") from e
    except anthropic.APIStatusError as e:
        log_event("anthropic", "error", False, f"{purpose}: {e.status_code} {e.message}", project_id=project_id)
        raise StageError(f"Claude API error {e.status_code}: {e.message}") from e
    except anthropic.APIConnectionError as e:
        log_event("anthropic", "error", False, f"{purpose}: connection error", project_id=project_id)
        raise StageError("Could not reach the Claude API (network).") from e

    cost = _cost(model, resp.usage)
    log_event("anthropic", "call", True, f"{purpose}: {resp.usage.input_tokens} in / {resp.usage.output_tokens} out",
              units=resp.usage.input_tokens + resp.usage.output_tokens, cost=cost, project_id=project_id)
    if resp.stop_reason == "refusal":
        raise StageError("Claude declined this request. Rephrase the topic and retry.")
    if resp.stop_reason == "max_tokens":
        raise StageError("Claude's answer was cut off (max_tokens). Retry the stage.")
    if resp.parsed_output is None:
        raise StageError("Claude returned output that did not match the expected structure.")
    if project_id:
        from ..db import SessionLocal, Project
        with SessionLocal() as s:
            p = s.get(Project, project_id)
            if p:
                p.cost_usd = (p.cost_usd or 0) + cost
                s.commit()
    return resp.parsed_output


def image_block(jpeg_path):
    data = base64.standard_b64encode(open(jpeg_path, "rb").read()).decode()
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data}}


def test():
    c = client()
    model = get_setting("preferences").get("claude_model", "claude-opus-5-5")
    m = c.models.retrieve(model)
    return f"Connected. Model {m.id} available."
