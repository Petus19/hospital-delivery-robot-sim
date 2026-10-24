import random
from pathlib import Path

import pytest
from pydantic import ValidationError

from hospital_sim.metrics import robot_rows, task_rows
from hospital_sim.scenario import (
    GeneratorSpec,
    Scenario,
    build_simulation,
    generate_tasks,
    load_scenario,
)

SCENARIOS = Path(__file__).resolve().parent.parent / "scenarios"


def run(seed: int | None = None):
    scenario, grid = load_scenario(SCENARIOS / "random_day.yaml")
    sim = build_simulation(scenario, grid, seed=seed)
    sim.run(scenario.max_ticks)
    return sim


def test_same_seed_gives_identical_run():
    first, second = run(seed=7), run(seed=7)
    assert task_rows(first) == task_rows(second)
    assert robot_rows(first) == robot_rows(second)
    assert first.tick == second.tick


def test_different_seed_gives_different_tasks():
    assert task_rows(run(seed=1)) != task_rows(run(seed=2))


def test_generator_respects_spec(hospital_grid):
    spec = GeneratorSpec(rate=0.5, until_tick=200, urgent_share=0.0, samples_share=0.0)
    tasks = generate_tasks(spec, hospital_grid, random.Random(0))
    assert 60 < len(tasks) < 140  # about rate * until_tick
    assert all(t.created_tick < 200 for t in tasks)
    assert all(t.priority == "normal" for t in tasks)
    assert {t.pickup for t in tasks} <= {"pharmacy", "lab", "kitchen"}
    assert all(t.dropoff.startswith("ward_") for t in tasks)
    assert [t.id for t in tasks] == list(range(1, len(tasks) + 1))


def test_typo_in_scenario_is_rejected():
    with pytest.raises(ValidationError):
        Scenario.model_validate({"name": "x", "map": "m.txt", "robtos": 3})


def test_starts_must_match_robot_count():
    with pytest.raises(ValidationError, match="start cells"):
        Scenario.model_validate({"name": "x", "map": "m.txt", "robots": 2, "starts": [[1, 1]]})


def test_custom_start_cells(hospital_grid):
    scenario = Scenario(name="x", map="m.txt", robots=2, starts=[(1, 4), (2, 4)])
    sim = build_simulation(scenario, hospital_grid)
    assert [r.pos for r in sim.robots] == [(1, 4), (2, 4)]
