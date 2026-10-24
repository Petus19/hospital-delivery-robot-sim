"""Turning a sentence into a task with a language model.

`TaskExtractor` is the small interface every provider implements. Today there is
one real provider, a local model served by Ollama, so hospital data never leaves
the machine. A cloud provider would be another class with the same `extract`
method; nothing else in the project would change.

The model is asked for JSON that follows a schema in which pickup and dropoff
can only be one of the allowed location names. Its answer is still validated
with pydantic, because a model can always return something unexpected.
"""

import logging
from typing import Any, Protocol

import httpx
import ollama
from pydantic import BaseModel, Field, ValidationError

from hospital_sim.models import Priority

log = logging.getLogger(__name__)

DEFAULT_MODEL = "qwen2.5:3b"
DEFAULT_HOST = "http://localhost:11434"

SYSTEM_PROMPT = """\
You turn delivery requests for hospital robots into JSON.
Requests can be written in English or Slovak.

Allowed locations: {locations}
Slovak names: lekáreň = pharmacy, laboratórium / labák = lab, kuchyňa = kitchen,
oddelenie N = ward_N.

Fields:
- pickup: where the robot collects the item (one allowed location)
- dropoff: where the robot delivers it (one allowed location)
- item: what is delivered, a few words in the user's language
- priority: "urgent" if the request says urgent, ASAP, emergency, súrne, urgentne
  or similar, otherwise "normal"

Answer with the JSON object only."""


class TaskRequest(BaseModel):
    """A validated delivery request, ready to become a `Task`."""

    pickup: str
    dropoff: str
    item: str = Field(min_length=1, max_length=60)
    priority: Priority = Priority.NORMAL


class TaskExtractor(Protocol):
    """Anything that can turn a sentence into a TaskRequest (or give up with None)."""

    def extract(self, text: str, locations: list[str]) -> TaskRequest | None: ...


def check_locations(request: TaskRequest, locations: list[str]) -> TaskRequest | None:
    """Reject requests that name a location that does not exist on the map."""
    if request.pickup not in locations or request.dropoff not in locations:
        return None
    if request.pickup == request.dropoff:
        return None
    return request


def json_schema(locations: list[str]) -> dict[str, Any]:
    """JSON schema for structured output: the model can only pick allowed locations."""
    return {
        "type": "object",
        "properties": {
            "pickup": {"type": "string", "enum": locations},
            "dropoff": {"type": "string", "enum": locations},
            "item": {"type": "string"},
            "priority": {"type": "string", "enum": [p.value for p in Priority]},
        },
        "required": ["pickup", "dropoff", "item", "priority"],
    }


class OllamaExtractor:
    """Local LLM through Ollama (https://ollama.com). No API key, no data leaves the PC."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        host: str = DEFAULT_HOST,
        timeout: float = 30.0,
        client: Any = None,  # noqa: ANN401 - any object with a .chat() method (a fake in tests)
    ) -> None:
        self.model = model
        self.client = client or ollama.Client(host=host, timeout=timeout)

    def extract(self, text: str, locations: list[str]) -> TaskRequest | None:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT.format(locations=", ".join(locations))},
            {"role": "user", "content": text},
        ]
        try:
            response = self.client.chat(
                model=self.model,
                messages=messages,
                format=json_schema(locations),
                options={"temperature": 0},  # same sentence -> same answer
            )
            request = TaskRequest.model_validate_json(response.message.content or "")
        except (ConnectionError, httpx.HTTPError) as error:
            log.warning("Ollama is not reachable (%s), using the rule-based parser", error)
            return None
        except ollama.ResponseError as error:
            log.warning("Ollama error: %s (try: ollama pull %s)", error.error, self.model)
            return None
        except ValidationError as error:
            log.warning("LLM returned invalid output: %s", error.errors()[0]["msg"])
            return None
        return check_locations(request, locations)
