"""Multi-robot safety: robots never share a cell and never swap places."""

from pathlib import Path

import pytest

from hospital_sim.grid import parse_grid
from hospital_sim.models import Task, TaskStatus
from hospital_sim.robot import Robot
from hospital_sim.scenario import build_simulation, load_scenario
from hospital_sim.simulation import SimConfig, Simulation

SCENARIOS = Path(__file__).resolve().parent.parent / "scenarios"


def run_checked(sim: Simulation, max_ticks: int) -> None:
    """Run the simulation and assert the safety invariants after every tick."""
    while sim.tick < max_ticks and not sim.is_finished:
        before = {r.id: r.pos for r in sim.robots}
        sim.step()
        after = {r.id: r.pos for r in sim.robots}
        cells = list(after.values())
        assert len(cells) == len(set(cells)), f"two robots on one cell at tick {sim.tick}"
        for a in sim.robots:
            for b in sim.robots:
                if a.id < b.id:
                    swapped = after[a.id] == before[b.id] and after[b.id] == before[a.id]
                    assert not swapped, f"robots {a.id} and {b.id} swapped at tick {sim.tick}"


@pytest.mark.parametrize("name", ["demo", "rush_hour", "blocked_corridor"])
def test_scenarios_have_no_collisions(name):
    scenario, grid = load_scenario(SCENARIOS / f"{name}.yaml")
    sim = build_simulation(scenario, grid)
    run_checked(sim, scenario.max_ticks)
    assert sim.is_finished
    assert all(t.status == TaskStatus.DELIVERED for t in sim.tasks)
    # Planning alone should have avoided every conflict; the safety layer is a backup.
    assert sum(r.safety_stops for r in sim.robots) == 0


# One-cell-wide corridor (row 2) with side pockets: chargers above, docks below.
CROSSING_MAP = """\
###########
##C#####C##
#1.......2#
###P#.#L###
###########
"""


def test_head_on_robots_cross_without_collision():
    grid = parse_grid(CROSSING_MAP)
    robots = [Robot(id=0, pos=(2, 1), home=(2, 1)), Robot(id=1, pos=(8, 1), home=(8, 1))]
    # Robot 0 fetches from the pharmacy (left) for ward_2 (right end), robot 1 the
    # other way round, so they meet head-on in the narrow corridor.
    tasks = [Task(1, "pharmacy", "ward_2", "insulin"), Task(2, "lab", "ward_1", "samples")]
    sim = Simulation(grid, robots, tasks, SimConfig(load_ticks=1, unload_ticks=1))
    run_checked(sim, 200)
    assert sim.is_finished
    assert all(t.status == TaskStatus.DELIVERED for t in sim.tasks)
    assert sum(r.planned_waits for r in sim.robots) > 0  # someone waited aside for the other


def test_robot_waiting_on_a_dock_steps_aside(hospital_grid):
    # Two idle robots park on both lab docks, so robot 0 cannot plan to its pickup.
    # It must not keep blocking the ward_1 dock while it waits.
    lab = hospital_grid.locations["lab"]
    robots = [
        Robot(id=0, pos=(4, 7), home=(19, 1)),  # on a ward_1 dock
        Robot(id=1, pos=lab[0], home=lab[0]),
        Robot(id=2, pos=lab[1], home=lab[1]),
    ]
    sim = Simulation(hospital_grid, robots, config=SimConfig(dock_timeout=3))
    task = Task(1, "lab", "ward_2", "test kits")
    robots[0].assign(task, tick=0)
    sim.tasks.append(task)
    run_checked(sim, 15)
    waiting = robots[0]
    assert hospital_grid.location_at(waiting.pos) is None  # off the dock
    assert not hospital_grid.blocks_passage(waiting.pos)  # and not in anyone's way
    assert waiting.pos != waiting.home  # a short step aside, not a trip home
    assert waiting.deadlock_recoveries == 1


def test_deadlock_is_resolved_by_retreating():
    # Each robot is loaded on a single-cell dock and wants the dock the other one occupies.
    # Neither can plan (the goal is occupied forever) until one of them gives way.
    grid = parse_grid("#########\n#P.....L#\n###C#C###\n#########")
    robots = [Robot(id=0, pos=(1, 1), home=(3, 2)), Robot(id=1, pos=(7, 1), home=(5, 2))]
    tasks = [Task(1, "pharmacy", "lab", "insulin"), Task(2, "lab", "pharmacy", "samples")]
    config = SimConfig(load_ticks=1, unload_ticks=1, stuck_timeout=5)
    sim = Simulation(grid, robots, tasks, config)
    run_checked(sim, 300)
    assert all(t.status == TaskStatus.DELIVERED for t in sim.tasks)
    assert sum(r.deadlock_recoveries for r in sim.robots) >= 1
