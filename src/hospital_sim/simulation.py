"""The simulation core: one `step()` call advances the whole world by one tick.

This module has no I/O, no randomness and no pygame. Given the same inputs it
always produces the same result, which is what makes it testable.

Collision avoidance has two layers:
  1. planning - every path is booked in a reservation table and later robots
     plan around earlier bookings (prioritized planning, cooperative A*);
  2. execution - before anyone moves, a safety check stops a robot whose move
     would hit another robot. A stopped robot replans on the next tick.
"""

import logging
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass

from hospital_sim.dispatcher import assign_tasks, queue_order
from hospital_sim.grid import Cell, Grid
from hospital_sim.models import BlockEvent, Priority, RobotState, Task, TaskStatus
from hospital_sim.pathfinding import path_length, space_time_astar
from hospital_sim.reservations import ReservationTable
from hospital_sim.robot import Robot

log = logging.getLogger(__name__)


@dataclass
class SimConfig:
    load_ticks: int = 3
    unload_ticks: int = 3
    stuck_timeout: int = 12  # ticks without a usable plan before a robot retreats home
    dock_timeout: int = 3  # the same, but for a robot blocking a dock: it steps aside sooner
    plan_horizon: int = 150  # how far into the future cooperative A* may plan


class Simulation:
    def __init__(
        self,
        grid: Grid,
        robots: Iterable[Robot],
        tasks: Iterable[Task] = (),
        config: SimConfig | None = None,
        events: Iterable[BlockEvent] = (),
    ) -> None:
        self.grid = grid
        self.robots = sorted(robots, key=lambda r: r.id)
        self.config = config or SimConfig()
        self.events = list(events)
        self.tick = 0
        self.tasks: list[Task] = []  # every task released so far
        self.queue: list[Task] = []  # released but not yet assigned
        self.blocked: set[Cell] = set()  # cells closed right now (e.g. cleaning a corridor)
        self.reservations = ReservationTable()
        self.blockage_replans = 0  # how often a closed corridor forced a robot to replan
        self._stopped: set[int] = set()  # robots halted by the safety check this tick
        self._scheduled = sorted(tasks, key=lambda t: (t.created_tick, t.id))
        self._next_task_id = max((t.id for t in self._scheduled), default=0) + 1
        self._validate()
        for robot in self.robots:
            self.reservations.reserve(robot.id, [robot.pos], self.tick)  # parked at start

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
        self._apply_events()
        self._release_tasks()
        self._dispatch()
        self._plan_paths()
        self._move_robots()
        self._update_states()
        self.tick += 1

    # ------------------------------------------------------------------ tick phases

    def _apply_events(self) -> None:
        """Close and reopen cells according to the blockage events.

        A robot whose remaining path crosses a newly closed cell replans now.
        When cells reopen, every driving robot replans, since a shorter way may be
        free again. The robots learn about a blockage only when it starts, like
        real robots that see it on arrival rather than from a schedule.
        """
        blocked: set[Cell] = set()
        for event in self.events:
            if event.is_active(self.tick):
                blocked |= event.cells
        if blocked == self.blocked:
            return
        closed, opened = blocked - self.blocked, self.blocked - blocked
        self.blocked = blocked
        if closed:
            log.warning("t=%d %d cell(s) closed: %s", self.tick, len(closed), sorted(closed))
        if opened:
            log.info("t=%d %d cell(s) open again", self.tick, len(opened))
        for robot in self.robots:
            if closed and any(cell in closed for cell in robot.path):
                robot.needs_plan = True
                self.blockage_replans += 1
                log.info("t=%d robot %d replans around the blockage", self.tick, robot.id)
            elif opened and robot.is_driving:
                robot.needs_plan = True

    def _release_tasks(self) -> None:
        while self._scheduled and self._scheduled[0].created_tick <= self.tick:
            task = self._scheduled.pop(0)
            self.tasks.append(task)
            self.queue.append(task)
            log.info("t=%d task %d created: %s", self.tick, task.id, _describe(task))

    def _dispatch(self) -> None:
        for task, robot in assign_tasks(self.queue, self.robots, self.grid, self.blocked):
            robot.assign(task, self.tick)
            self.queue.remove(task)
            log.info("t=%d task %d -> robot %d", self.tick, task.id, robot.id)
        self.queue.sort(key=queue_order)

    def _plan_paths(self) -> None:
        """Prioritized planning: robots plan one by one, urgent work first.

        Each robot removes its old bookings, plans around everyone else's, and books
        the new path. If no safe path exists yet, it keeps its old bookings (which
        others already plan around) and tries again next tick.
        """
        needing = [r for r in self.robots if r.needs_plan]
        for robot in sorted(needing, key=_planning_order):
            goal = self._choose_goal(robot)
            if goal is None:
                robot.needs_plan = False
                continue
            self.reservations.clear(robot.id)
            path = space_time_astar(
                self.grid,
                robot.pos,
                goal,
                self.tick,
                self.reservations,
                robot.id,
                self.blocked,
                self.config.plan_horizon,
            )
            if path is None:
                self.reservations.reserve(robot.id, [robot.pos, *robot.path], self.tick)
                continue
            self.reservations.reserve(robot.id, path, self.tick)
            robot.goal = goal
            robot.path = path[1:]
            robot.needs_plan = False

    def _move_robots(self) -> None:
        """Move every robot one step along its plan, after a final safety check."""
        wanted = {r.id: r.path[0] if r.path else r.pos for r in self.robots}
        final = {r.id: r.pos for r in self.robots}  # start by assuming nobody moves
        waiting = [r for r in self.robots if wanted[r.id] != r.pos]
        progress = True
        while progress:  # approving one move can free the cell another robot wants
            progress = False
            for robot in list(waiting):
                if self._is_safe_move(robot, wanted[robot.id], final):
                    final[robot.id] = wanted[robot.id]
                    waiting.remove(robot)
                    progress = True

        self._stopped = {r.id for r in waiting}
        for robot in self.robots:
            if robot.id in self._stopped:
                robot.safety_stops += 1
                robot.needs_plan = True
                log.debug("t=%d robot %d safety stop before %s", self.tick, robot.id, robot.path[0])
                continue
            if not robot.path:
                continue
            nxt = robot.path.pop(0)
            if nxt == robot.pos:
                robot.planned_waits += 1
            else:
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
            elif robot.detour is not None and not robot.path and robot.pos == robot.detour:
                robot.detour = None  # out of the way now, try the real goal again
                robot.needs_plan = True
            elif (
                robot.is_driving
                and not robot.needs_plan  # a stale goal from a failed replan does not count
                and not robot.path
                and robot.pos == robot.goal
            ):
                service = (
                    self.config.load_ticks
                    if robot.state == RobotState.TO_PICKUP
                    else self.config.unload_ticks
                )
                robot.arrive(now, service)
            self._check_stuck(robot, now)

    # ------------------------------------------------------------------ helpers

    def _is_safe_move(self, robot: Robot, target: Cell, final: dict[int, Cell]) -> bool:
        if target in self.blocked:
            return False  # never drive into a closed cell, even with an outdated plan
        for other in self.robots:
            if other is robot:
                continue
            if final[other.id] == target:
                return False  # vertex conflict: the cell will be occupied
            if other.pos == target and final[other.id] == robot.pos:
                return False  # edge conflict: the two robots would swap places
        return True

    def _check_stuck(self, robot: Robot, now: int) -> None:
        """Deadlock handling: timeout, then get out of the way and replan.

        Only ticks without a usable plan count (planned waits are fine).
          * A robot standing on a dock steps aside to the nearest free side cell
            after `dock_timeout` ticks, so the dock is free for others. Typical
            case: it has just delivered and waits for a free dock at its next pickup.
          * A robot stuck in a doorway or one-lane passage retreats to its home
            charger after `stuck_timeout`.
          * A robot on any other cell blocks nobody, so it simply keeps waiting.
        Giving way breaks e.g. two robots waiting for each other's dock.
        """
        if robot.is_driving and (robot.needs_plan or robot.id in self._stopped):
            robot.stuck_ticks += 1
        else:
            robot.stuck_ticks = 0
            return
        on_dock = robot.pos != robot.home and self.grid.location_at(robot.pos) is not None
        if not on_dock and self._is_waiting_spot(robot.pos):
            return
        timeout = self.config.dock_timeout if on_dock else self.config.stuck_timeout
        if robot.stuck_ticks < timeout:
            return
        robot.stuck_ticks = 0
        robot.needs_plan = True
        if robot.task is None or robot.detour is not None:
            return  # nothing to give way for, or already giving way: just keep replanning
        side_cell = self._side_cell(robot, now) if on_dock else None
        detour = side_cell or robot.home  # no free side cell nearby: go home instead
        if detour == robot.pos:
            return
        robot.detour = detour
        robot.deadlock_recoveries += 1
        log.warning("t=%d robot %d is stuck, moving out of the way to %s", now, robot.id, detour)

    def _side_cell(self, robot: Robot, now: int) -> Cell | None:
        """Nearest free waiting spot (BFS) not booked by any other robot from now on."""
        seen = {robot.pos}
        queue = deque([robot.pos])
        while queue:
            cell = queue.popleft()
            if self._is_waiting_spot(cell) and self.reservations.is_free_from(cell, now, robot.id):
                return cell
            for nxt in self.grid.neighbors(cell):
                if nxt not in seen and nxt not in self.blocked:
                    seen.add(nxt)
                    queue.append(nxt)
        return None

    def _is_waiting_spot(self, cell: Cell) -> bool:
        """A cell where a waiting robot blocks nobody: not a dock, not closed, and not
        a doorway or one-lane passage."""
        return (
            self.grid.location_at(cell) is None
            and cell not in self.blocked
            and not self.grid.blocks_passage(cell)
        )

    def _choose_goal(self, robot: Robot) -> Cell | None:
        if robot.detour is not None:
            return robot.detour
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
            dist = path_length(self.grid, robot.pos, cell, self.blocked)
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
        for event in self.events:
            for cell in event.cells:
                if not self.grid.is_free(cell):
                    raise ValueError(f"blockage cell {cell} is a wall or outside the map")

    def _check_task(self, task: Task) -> None:
        for name in (task.pickup, task.dropoff):
            if name not in self.grid.locations:
                raise ValueError(f"task {task.id}: unknown location {name!r}")


def _planning_order(robot: Robot) -> tuple[int, int]:
    """Who plans first: robots with urgent tasks, then busy robots, then idle ones."""
    if robot.task is not None and robot.task.priority == Priority.URGENT:
        return (0, robot.id)
    return (1 if robot.task is not None else 2, robot.id)


def _describe(task: Task) -> str:
    return f"{task.item} {task.pickup} -> {task.dropoff} ({task.priority})"
