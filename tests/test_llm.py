"""OllamaExtractor with a fake client: no Ollama server is needed (CI never has one)."""

import json

import ollama

from hospital_sim.llm import OllamaExtractor, TaskRequest, json_schema
from hospital_sim.models import Priority

LOCATIONS = ["lab", "pharmacy", "ward_1", "ward_3"]


class FakeClient:
    """Mimics ollama.Client.chat: returns a canned reply or raises a canned error."""

    def __init__(self, reply: str = "", error: Exception | None = None) -> None:
        self.reply = reply
        self.error = error
        self.kwargs: dict = {}

    def chat(self, **kwargs):
        self.kwargs = kwargs
        if self.error is not None:
            raise self.error
        return ollama.ChatResponse(message=ollama.Message(role="assistant", content=self.reply))


def reply(**fields) -> str:
    return json.dumps({"item": "insulin", "priority": "normal"} | fields)


def test_valid_reply_becomes_request():
    client = FakeClient(reply(pickup="pharmacy", dropoff="ward_3", priority="urgent"))
    request = OllamaExtractor(client=client).extract("insulin to ward 3 asap", LOCATIONS)
    assert request == TaskRequest(
        pickup="pharmacy", dropoff="ward_3", item="insulin", priority=Priority.URGENT
    )


def test_request_uses_schema_and_deterministic_settings():
    client = FakeClient(reply(pickup="pharmacy", dropoff="ward_3"))
    OllamaExtractor(model="tiny-model", client=client).extract("text", LOCATIONS)
    assert client.kwargs["model"] == "tiny-model"
    assert client.kwargs["format"] == json_schema(LOCATIONS)
    assert client.kwargs["options"] == {"temperature": 0}
    assert "ward_3" in client.kwargs["messages"][0]["content"]  # locations are in the prompt


def test_schema_limits_locations_to_the_map():
    schema = json_schema(LOCATIONS)
    assert schema["properties"]["pickup"]["enum"] == [*LOCATIONS, "unknown"]
    assert schema["properties"]["priority"]["enum"] == ["normal", "urgent"]


def test_unknown_location_is_rejected():
    client = FakeClient(reply(pickup="pharmacy", dropoff="ward_42"))
    assert OllamaExtractor(client=client).extract("text", LOCATIONS) is None


def test_invalid_json_is_rejected():
    client = FakeClient("Sure! The robot should go to ward 3.")
    assert OllamaExtractor(client=client).extract("text", LOCATIONS) is None


def test_missing_field_is_rejected():
    client = FakeClient(json.dumps({"pickup": "pharmacy", "dropoff": "ward_3"}))
    assert OllamaExtractor(client=client).extract("text", LOCATIONS) is None


def test_server_not_running_returns_none():
    client = FakeClient(error=ConnectionError("Failed to connect to Ollama"))
    assert OllamaExtractor(client=client).extract("text", LOCATIONS) is None


def test_model_not_downloaded_returns_none():
    client = FakeClient(error=ollama.ResponseError("model 'qwen2.5:3b' not found", 404))
    assert OllamaExtractor(client=client).extract("text", LOCATIONS) is None


def test_real_client_without_server_returns_none():
    # Port 9 (discard) has no Ollama behind it: the connection fails fast.
    extractor = OllamaExtractor(host="http://127.0.0.1:9", timeout=2)
    assert extractor.extract("deliver insulin from pharmacy to ward 3", LOCATIONS) is None


def test_unknown_answer_is_rejected():
    # The model's way of saying "this is not a delivery between known places".
    client = FakeClient(reply(pickup="unknown", dropoff="unknown", item="coffee"))
    assert OllamaExtractor(client=client).extract("make me a coffee", LOCATIONS) is None


def test_prompt_forbids_guessing_and_translating():
    client = FakeClient(reply(pickup="pharmacy", dropoff="ward_3"))
    OllamaExtractor(client=client).extract("text", LOCATIONS)
    prompt = client.kwargs["messages"][0]["content"]
    assert '"unknown"' in prompt
    assert "do not translate" in prompt
