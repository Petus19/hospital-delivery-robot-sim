import pytest

from hospital_sim.llm import TaskRequest
from hospital_sim.models import Priority
from hospital_sim.task_parser import RuleBasedExtractor, parse_task

LOCATIONS = ["kitchen", "lab", "pharmacy"] + [f"ward_{n}" for n in range(1, 10)]


@pytest.mark.parametrize(
    ("text", "pickup", "dropoff", "item", "priority"),
    [
        ("deliver insulin from the pharmacy to ward 3, urgent",
         "pharmacy", "ward_3", "insulin", "urgent"),
        ("Bring blood samples to the lab from ward 5",
         "ward_5", "lab", "blood samples", "normal"),
        ("take meal trays from kitchen to ward_7 ASAP",
         "kitchen", "ward_7", "meal trays", "urgent"),
        ("send test kits from lab to ward number two",
         "lab", "ward_2", "test kits", "normal"),
        ("doruč inzulín z lekárne na oddelenie 3, súrne",
         "pharmacy", "ward_3", "inzulín", "urgent"),
        ("Prines vzorky krvi z oddelenia č. 4 do laboratória",
         "ward_4", "lab", "vzorky krvi", "normal"),
        ("odvez obedy z kuchyne na oddelenie päť",
         "kitchen", "ward_5", "obedy", "normal"),
    ],
)  # fmt: skip
def test_rule_based_parser(text, pickup, dropoff, item, priority):
    request = RuleBasedExtractor().extract(text, LOCATIONS)
    assert request == TaskRequest(pickup=pickup, dropoff=dropoff, item=item, priority=priority)


@pytest.mark.parametrize(
    "text",
    [
        "deliver insulin to ward 3",  # no pickup
        "hello robot",
        "deliver insulin from the pharmacy to ward 12",  # no ward 12 on the map
        "move it from ward 2 to ward 2",  # same place
    ],
)
def test_rule_based_parser_gives_up(text):
    assert RuleBasedExtractor().extract(text, LOCATIONS) is None


class FakeLLM:
    """Stands in for Ollama in tests: returns a fixed answer and records calls."""

    def __init__(self, answer: TaskRequest | None) -> None:
        self.answer = answer
        self.calls: list[str] = []

    def extract(self, text: str, locations: list[str]) -> TaskRequest | None:
        self.calls.append(text)
        return self.answer


def test_llm_answer_is_used_when_valid():
    answer = TaskRequest(pickup="lab", dropoff="ward_1", item="results", priority=Priority.URGENT)
    llm = FakeLLM(answer)
    result = parse_task("whatever the user typed", LOCATIONS, llm)
    assert result.source == "llm"
    assert result.request == answer
    assert llm.calls == ["whatever the user typed"]


def test_falls_back_to_rules_when_llm_gives_up():
    result = parse_task("deliver insulin from pharmacy to ward 3", LOCATIONS, FakeLLM(None))
    assert result.source == "rules"
    assert result.request.dropoff == "ward_3"


def test_works_without_any_llm():
    result = parse_task("deliver insulin from pharmacy to ward 3", LOCATIONS, llm=None)
    assert result.source == "rules"


def test_nothing_understood_raises():
    with pytest.raises(ValueError, match="Could not understand"):
        parse_task("make me a coffee", LOCATIONS, FakeLLM(None))
