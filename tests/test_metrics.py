import csv
import json

from hospital_sim.metrics import export, format_summary, summary
from hospital_sim.models import Priority, Task
from hospital_sim.robot import Robot
from hospital_sim.simulation import SimConfig, Simulation


def finished_sim(small_grid) -> Simulation:
    robot = Robot(id=0, pos=(3, 1), home=(3, 1))
    tasks = [
        Task(1, "pharmacy", "ward_2", "insulin"),
        Task(2, "lab", "ward_1", "samples", Priority.URGENT, created_tick=2),
    ]
    sim = Simulation(small_grid, [robot], tasks, SimConfig(load_ticks=2, unload_ticks=2))
    sim.run(200)
    return sim


def test_summary_numbers(small_grid):
    sim = finished_sim(small_grid)
    s = summary(sim)
    assert s["tasks_total"] == 2
    assert s["tasks_delivered"] == 2
    assert s["total_distance"] == sim.robots[0].distance
    # The first task is delivered at tick 14 (see test_robot), so its time is known exactly.
    assert sim.tasks[0].delivery_time == 14
    assert s["max_delivery_time"] >= s["avg_delivery_time"]
    assert 0 < s["avg_utilization"] <= 1


def test_export_writes_three_files(small_grid, tmp_path):
    sim = finished_sim(small_grid)
    paths = export(sim, tmp_path, extra={"scenario": "test", "seed": 7})
    assert sorted(p.name for p in paths) == ["robots.csv", "summary.json", "tasks.csv"]

    with (tmp_path / "tasks.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert [r["id"] for r in rows] == ["1", "2"]
    assert rows[1]["priority"] == "urgent"

    data = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert data["seed"] == 7
    assert data["tasks_delivered"] == 2


def test_format_summary_mentions_every_robot(small_grid):
    text = format_summary(finished_sim(small_grid))
    assert "Delivered: 2/2" in text
    assert "robot" in text
