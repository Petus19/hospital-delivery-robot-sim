"""Dispatcher: decides which robot takes which task.

Greedy rule: go through the queue (urgent first, then oldest) and give each task
to the free robot with the shortest *real* path to the pickup. Real path = A*
length around walls, not straight-line distance, because a robot on the other
side of a wall can be far away even if it looks close.
"""

from collections.abc import Collection, Iterable

from hospital_sim.grid import Cell, Grid
from hospital_sim.models import Priority, Task
from hospital_sim.pathfinding import path_length
from hospital_sim.robot import Robot


def queue_order(task: Task) -> tuple[int, int, int]:
    """Sort key: urgent before normal, then first come first served, then id."""
    return (0 if task.priority == Priority.URGENT else 1, task.created_tick, task.id)


def assign_tasks(
    queue: Iterable[Task],
    robots: Iterable[Robot],
    grid: Grid,
    blocked: Collection[Cell] = (),
) -> list[tuple[Task, Robot]]:
    """Return (task, robot) pairs. Does not modify anything; the caller applies them."""
    free = [r for r in robots if r.is_available]
    assignments: list[tuple[Task, Robot]] = []
    for task in sorted(queue, key=queue_order):
        if not free:
            break
        best: tuple[int, int, Robot] | None = None  # (distance, robot id, robot)
        for robot in free:
            distance = distance_to_location(grid, robot.pos, task.pickup, blocked)
            if distance is None:
                continue
            candidate = (distance, robot.id, robot)
            if best is None or candidate[:2] < best[:2]:
                best = candidate
        if best is not None:
            assignments.append((task, best[2]))
            free.remove(best[2])
    return assignments


def distance_to_location(
    grid: Grid, start: Cell, location: str, blocked: Collection[Cell] = ()
) -> int | None:
    """A* distance to the nearest dock cell of a location (None if unreachable)."""
    distances = [path_length(grid, start, dock, blocked) for dock in grid.locations[location]]
    reachable = [d for d in distances if d is not None]
    return min(reachable) if reachable else None
