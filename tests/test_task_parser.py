import pytest

from hospital_sim.llm import TaskRequest
from hospital_sim.models import Priority
from hospital_sim.task_parser import RuleBasedExtractor, mentioned_locations, parse_task

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
        ("potrebujeme na šestku antibiotiká z lekárne, ponáhľajte sa",
         "pharmacy", "ward_6", "antibiotiká", "urgent"),
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
    result = parse_task("results from the lab for ward 1, asap", LOCATIONS, llm)
    assert result.source == "llm"
    assert result.request == answer
    assert llm.calls == ["results from the lab for ward 1, asap"]


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


def test_mentioned_locations():
    assert mentioned_locations("insulin from the pharmacy to ward 12") == {"pharmacy", "ward_12"}
    assert mentioned_locations("na trojku z labáku") == {"ward_3", "lab"}
    assert mentioned_locations("make me a coffee") == set()


@pytest.mark.parametrize(
    ("text", "guess"),
    [
        # What qwen2.5:3b really answered for these sentences:
        ("deliver insulin from the pharmacy to ward 12", ("pharmacy", "ward_1")),
        ("make me a coffee", ("kitchen", "ward_1")),
        ("prines kávu z kaviarne na oddelenie 2", ("kitchen", "ward_2")),
    ],
)
def test_llm_guess_of_unmentioned_location_is_rejected(text, guess):
    llm = FakeLLM(TaskRequest(pickup=guess[0], dropoff=guess[1], item="x"))
    with pytest.raises(ValueError, match="Could not understand"):
        parse_task(text, LOCATIONS, llm)


def test_llm_answer_with_hospital_slang_is_accepted():
    answer = TaskRequest(pickup="pharmacy", dropoff="ward_3", item="inzulín")
    result = parse_task("inzulín z lekárne na trojku", LOCATIONS, FakeLLM(answer))
    assert result.source == "llm"


def test_stat_counts_as_urgent_only_as_a_whole_word():
    rules = RuleBasedExtractor()
    stat = rules.extract("blood samples from ward 2 to the lab, stat", LOCATIONS)
    status = rules.extract("bring the status report from the lab to ward 2", LOCATIONS)
    assert stat is not None and stat.priority == Priority.URGENT
    assert status is not None and status.priority == Priority.NORMAL
