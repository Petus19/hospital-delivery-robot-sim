"""The simulation core: one `step()` call advances the whole world by one tick.

This module has no I/O, no randomness and no pygame. Given the same inputs it
always produces the same result, which is what makes it testable.
"""

import logging
from collections.abc import Iterable
from dataclasses import dataclass

from hospital_sim.grid import Cell, Grid
from hospital_sim.models import Priority, RobotState, Task, TaskStatus
from hospital_sim.pathfinding import astar, path_length
from hospital_sim.robot import Robot

log = logging.getLogger(__name__)


@dataclass
class SimConfig:
    load_ticks: int = 3
    unload_ticks: int = 3


class Simulation:
    def __init__(
        self,
        grid: Grid,
        robots: Iterable[Robot],
        tasks: Iterable[Task] = (),
        config: SimConfig | None = None,
    ) -> None:
        self.grid = grid
        self.robots = sorted(robots, key=lambda r: r.id)
        self.config = config or SimConfig()
        self.tick = 0
        self.tasks: list[Task] = []  # every task released so far
        self.queue: list[Task] = []  # released but not yet assigned
        self.blocked: set[Cell] = set()  # cells closed right now (e.g. cleaning a corridor)
        self._scheduled = sorted(tasks, key=lambda t: (t.created_tick, t.id))
        self._next_task_id = max((t.id for t in self._scheduled), default=0) + 1
        self._validate()

    # ------------------------------------------------------------------ public API

    def add_task(
        self, pickup: str, dropoff: str, item: str, priority: Priority = Priority.NORMAL
    ) -> Task:
        """Create a task right now (used by the GUI / natural-language input)."""
        task = Task(self._next_task_id, pickup, dropoff, item, priority, created_tick=self.tick)
        self._next_task_id += 1
        self._check_task(task)
        self._scheduled.append(task)
        self._scheduled.sort(key=lambda t: (t.created_tick, t.id))
        return task

    @property
    def is_finished(self) -> bool:
        """True when every task is delivered and every robot is parked at home."""
        return (
            not self._scheduled
            and all(t.status == TaskStatus.DELIVERED for t in self.tasks)
            and all(r.state == RobotState.IDLE for r in self.robots)
        )

    def run(self, max_ticks: int) -> None:
        while self.tick < max_ticks and not self.is_finished:
            self.step()

    def step(self) -> None:
        self._release_tasks()
        self._dispatch()
        self._plan_paths()
        self._move_robots()
        self._update_states()
        self.tick += 1

    # ------------------------------------------------------------------ tick phases

    def _release_tasks(self) -> None:
        while self._scheduled and self._scheduled[0].created_tick <= self.tick:
            task = self._scheduled.pop(0)
            self.tasks.append(task)
            self.queue.append(task)
            log.info("t=%d task %d created: %s", self.tick, task.id, _describe(task))

    def _dispatch(self) -> None:
        """Naive first version: urgent first, then oldest; give it to the first free robot."""
        self.queue.sort(key=_queue_order)
        for task in list(self.queue):
            free = [r for r in self.robots if r.is_available]
            if not free:
                return
            robot = free[0]
            robot.assign(task, self.tick)
            self.queue.remove(task)
            log.info("t=%d task %d -> robot %d", self.tick, task.id, robot.id)

    def _plan_paths(self) -> None:
        for robot in self.robots:
            if not robot.needs_plan:
                continue
            goal = self._choose_goal(robot)
            if goal is None:
                robot.needs_plan = False
                continue
            path = astar(self.grid, robot.pos, goal)
            if path is None:
                continue  # keep needs_plan set and try again next tick
            robot.goal = goal
            robot.path = path[1:]
            robot.needs_plan = False

    def _move_robots(self) -> None:
        for robot in self.robots:
            if robot.path:
                nxt = robot.path.pop(0)
                if nxt != robot.pos:
                    robot.distance += 1
                robot.pos = nxt

    def _update_states(self) -> None:
        now = self.tick + 1  # the moves just made bring the world to the next tick
        for robot in self.robots:
            if robot.task is not None:
                robot.busy_ticks += 1
            if robot.state in (RobotState.LOADING, RobotState.UNLOADING):
                robot.service_left -= 1
                if robot.service_left <= 0:
                    delivered = robot.finish_service(now)
                    if delivered is not None:
                        log.info(
                            "t=%d task %d delivered by robot %d in %d ticks",
                            now,
                            delivered.id,
                            robot.id,
                            delivered.delivery_time,
                        )
            elif robot.is_driving and not robot.path and robot.pos == robot.goal:
                service = (
                    self.config.load_ticks
                    if robot.state == RobotState.TO_PICKUP
                    else self.config.unload_ticks
                )
                robot.arrive(now, service)

    # ------------------------------------------------------------------ helpers

    def _choose_goal(self, robot: Robot) -> Cell | None:
        if robot.state == RobotState.RETURNING:
            return robot.home
        if robot.task is None:
            return None
        if robot.state == RobotState.TO_PICKUP:
            return self._choose_dock(robot, robot.task.pickup)
        if robot.state == RobotState.TO_DROPOFF:
            return self._choose_dock(robot, robot.task.dropoff)
        return None

    def _choose_dock(self, robot: Robot, location: str) -> Cell:
        """Pick the closest dock cell of a location, preferring docks no other robot uses."""
        claimed = {r.goal for r in self.robots if r is not robot and r.goal is not None}
        claimed |= {r.pos for r in self.robots if r is not robot and not r.is_driving}

        def cost(cell: Cell) -> tuple[bool, int, Cell]:
            dist = path_length(self.grid, robot.pos, cell)
            return (cell in claimed, dist if dist is not None else 10**9, cell)

        return min(self.grid.locations[location], key=cost)

    def _validate(self) -> None:
        seen: set[Cell] = set()
        for robot in self.robots:
            if not self.grid.is_free(robot.pos):
                raise ValueError(f"robot {robot.id} starts inside a wall at {robot.pos}")
            if robot.pos in seen:
                raise ValueError(f"two robots start on the same cell {robot.pos}")
            seen.add(robot.pos)
        for task in self._scheduled:
            self._check_task(task)

    def _check_task(self, task: Task) -> None:
        for name in (task.pickup, task.dropoff):
            if name not in self.grid.locations:
                raise ValueError(f"task {task.id}: unknown location {name!r}")


def _queue_order(task: Task) -> tuple[int, int, int]:
    return (0 if task.priority == Priority.URGENT else 1, task.created_tick, task.id)


def _describe(task: Task) -> str:
    return f"{task.item} {task.pickup} -> {task.dropoff} ({task.priority})"
