"""Scenario files (YAML): which map, how many robots, which tasks.

Pydantic validates the file, so a typo like `robtos: 3` or `priority: urgnet`
fails loudly at load time instead of somewhere deep inside the simulation.
"""

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from hospital_sim.grid import Grid, load_grid
from hospital_sim.models import Priority, Task
from hospital_sim.robot import Robot
from hospital_sim.simulation import SimConfig, Simulation


class TaskSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tick: int = Field(default=0, ge=0)
    pickup: str
    dropoff: str
    item: str
    priority: Priority = Priority.NORMAL


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    map: str  # path relative to the scenario file
    robots: int = Field(ge=1)
    max_ticks: int = Field(default=1000, ge=1)
    load_ticks: int = Field(default=3, ge=1)
    unload_ticks: int = Field(default=3, ge=1)
    tasks: list[TaskSpec] = []


def load_scenario(path: str | Path) -> tuple[Scenario, Grid]:
    path = Path(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    scenario = Scenario.model_validate(data)
    grid = load_grid(path.parent / scenario.map)
    return scenario, grid


def build_simulation(scenario: Scenario, grid: Grid) -> Simulation:
    chargers = sorted(grid.locations.get("charging", ()), key=lambda c: (c[1], c[0]))
    if scenario.robots > len(chargers):
        raise ValueError(f"{scenario.robots} robots but only {len(chargers)} charging stations")
    # Every robot starts on (and returns to) its own charger.
    robots = [
        Robot(id=i, pos=cell, home=cell) for i, cell in enumerate(chargers[: scenario.robots])
    ]
    tasks = [
        Task(i + 1, s.pickup, s.dropoff, s.item, s.priority, created_tick=s.tick)
        for i, s in enumerate(scenario.tasks)
    ]
    config = SimConfig(load_ticks=scenario.load_ticks, unload_ticks=scenario.unload_ticks)
    return Simulation(grid, robots, tasks, config)
