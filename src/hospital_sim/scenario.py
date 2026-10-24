"""Scenario files (YAML): which map, which robots, which tasks.

Pydantic validates the file, so a typo like `robtos: 3` or `priority: urgnet`
fails loudly at load time instead of somewhere deep inside the simulation.

Tasks come from an explicit list, from a seeded random generator, or both.
All randomness lives here, before the simulation starts: the generator turns a
seed into a fixed task list, so the same seed always gives the same run.
"""

import random
from pathlib import Path
from typing import Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from hospital_sim.grid import Cell, Grid, load_grid
from hospital_sim.models import BlockEvent, Priority, Task
from hospital_sim.robot import Robot
from hospital_sim.simulation import SimConfig, Simulation

DEFAULT_ITEMS: dict[str, list[str]] = {
    "pharmacy": ["insulin", "antibiotics", "morphine", "heparin", "saline", "paracetamol"],
    "lab": ["test kits", "test results"],
    "kitchen": ["meal trays"],
}


class TaskSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tick: int = Field(default=0, ge=0)
    pickup: str
    dropoff: str
    item: str
    priority: Priority = Priority.NORMAL


class GeneratorSpec(BaseModel):
    """Random task generator. Each tick a new task appears with probability `rate`."""

    model_config = ConfigDict(extra="forbid")

    rate: float = Field(gt=0, le=1)
    until_tick: int = Field(ge=1)
    urgent_share: float = Field(default=0.2, ge=0, le=1)
    samples_share: float = Field(default=0.15, ge=0, le=1)  # ward -> lab sample runs
    items: dict[str, list[str]] = DEFAULT_ITEMS  # pickup location -> possible items
    wards: list[str] | None = None  # default: every ward on the map


class BlockageSpec(BaseModel):
    """Cells closed for a while, e.g. a corridor being cleaned."""

    model_config = ConfigDict(extra="forbid")

    cells: list[tuple[int, int]] = Field(min_length=1)
    start: int = Field(ge=0)
    end: int

    @model_validator(mode="after")
    def _end_after_start(self) -> Self:
        if self.end <= self.start:
            raise ValueError(f"blockage ends ({self.end}) before it starts ({self.start})")
        return self


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    map: str  # path relative to the scenario file
    robots: int = Field(ge=1)
    starts: list[tuple[int, int]] | None = None  # default: one charging station each
    seed: int = 0
    max_ticks: int = Field(default=1000, ge=1)
    load_ticks: int = Field(default=3, ge=1)
    unload_ticks: int = Field(default=3, ge=1)
    stuck_timeout: int = Field(default=12, ge=1)
    dock_timeout: int = Field(default=3, ge=1)
    tasks: list[TaskSpec] = []
    generator: GeneratorSpec | None = None
    blockages: list[BlockageSpec] = []

    @model_validator(mode="after")
    def _starts_match_robots(self) -> Self:
        if self.starts is not None and len(self.starts) != self.robots:
            raise ValueError(f"{len(self.starts)} start cells given for {self.robots} robots")
        return self


def load_scenario(path: str | Path) -> tuple[Scenario, Grid]:
    path = Path(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    scenario = Scenario.model_validate(data)
    grid = load_grid(path.parent / scenario.map)
    return scenario, grid


def build_simulation(scenario: Scenario, grid: Grid, seed: int | None = None) -> Simulation:
    """Create the simulation. `seed` overrides the scenario's seed (e.g. from the CLI)."""
    robots = [
        Robot(id=i, pos=cell, home=cell) for i, cell in enumerate(_start_cells(scenario, grid))
    ]
    tasks = [
        Task(i + 1, s.pickup, s.dropoff, s.item, s.priority, created_tick=s.tick)
        for i, s in enumerate(scenario.tasks)
    ]
    if scenario.generator is not None:
        rng = random.Random(scenario.seed if seed is None else seed)
        tasks += generate_tasks(scenario.generator, grid, rng, first_id=len(tasks) + 1)
    config = SimConfig(
        load_ticks=scenario.load_ticks,
        unload_ticks=scenario.unload_ticks,
        stuck_timeout=scenario.stuck_timeout,
        dock_timeout=scenario.dock_timeout,
    )
    events = [BlockEvent(frozenset(b.cells), b.start, b.end) for b in scenario.blockages]
    return Simulation(grid, robots, tasks, config, events)


def generate_tasks(
    spec: GeneratorSpec, grid: Grid, rng: random.Random, first_id: int = 1
) -> list[Task]:
    """Turn a random number generator into a fixed list of tasks."""
    wards = spec.wards or sorted(name for name in grid.locations if name.startswith("ward_"))
    pickups = sorted(spec.items)
    tasks: list[Task] = []
    for tick in range(spec.until_tick):
        if rng.random() >= spec.rate:
            continue
        if rng.random() < spec.samples_share:
            pickup, dropoff, item = rng.choice(wards), "lab", "blood samples"
        else:
            pickup = rng.choice(pickups)
            dropoff = rng.choice(wards)
            item = rng.choice(spec.items[pickup])
        priority = Priority.URGENT if rng.random() < spec.urgent_share else Priority.NORMAL
        tasks.append(
            Task(first_id + len(tasks), pickup, dropoff, item, priority, created_tick=tick)
        )
    return tasks


def _start_cells(scenario: Scenario, grid: Grid) -> list[Cell]:
    if scenario.starts is not None:
        return list(scenario.starts)
    # Every robot starts on (and returns to) its own charger.
    chargers = sorted(grid.locations.get("charging", ()), key=lambda c: (c[1], c[0]))
    if scenario.robots > len(chargers):
        raise ValueError(f"{scenario.robots} robots but only {len(chargers)} charging stations")
    return chargers[: scenario.robots]
