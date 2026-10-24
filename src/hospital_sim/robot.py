"""A single delivery robot and its state machine.

    IDLE ──assign──> TO_PICKUP ──arrive──> LOADING ──done──> TO_DROPOFF
      ^                  ^                                       │
      │                  └────────assign────────┐              arrive
      │                                         │                v
      └─────arrive home──── RETURNING <──done── UNLOADING <──────┘

The robot only stores state and enforces legal transitions. Decisions (which task,
which path) are made by the simulation, so this class stays small and testable.
"""

from dataclasses import dataclass, field

from hospital_sim.grid import Cell
from hospital_sim.models import RobotState, Task, TaskStatus

S = RobotState
TRANSITIONS: dict[RobotState, set[RobotState]] = {
    S.IDLE: {S.TO_PICKUP, S.RETURNING},
    S.TO_PICKUP: {S.LOADING},
    S.LOADING: {S.TO_DROPOFF},
    S.TO_DROPOFF: {S.UNLOADING},
    S.UNLOADING: {S.IDLE, S.RETURNING},
    S.RETURNING: {S.IDLE, S.TO_PICKUP},
}


class InvalidTransition(RuntimeError):
    pass


@dataclass
class Robot:
    id: int
    pos: Cell
    home: Cell  # charger the robot parks at when it has nothing to do
    state: RobotState = RobotState.IDLE
    task: Task | None = None
    goal: Cell | None = None  # dock cell the robot is currently driving to
    # Future cells, one per tick: path[0] is where the robot wants to be next tick.
    # A repeated cell means a planned wait.
    path: list[Cell] = field(default_factory=list)
    service_left: int = 0  # ticks of loading/unloading still to go
    needs_plan: bool = False
    retreating: bool = False  # deadlock recovery: temporarily driving home
    stuck_ticks: int = 0
    # Metrics
    distance: int = 0
    busy_ticks: int = 0
    planned_waits: int = 0
    safety_stops: int = 0
    deadlock_recoveries: int = 0

    @property
    def is_available(self) -> bool:
        """Can the dispatcher give this robot a new task?"""
        return self.state in (S.IDLE, S.RETURNING) and self.task is None

    @property
    def is_driving(self) -> bool:
        return self.state in (S.TO_PICKUP, S.TO_DROPOFF, S.RETURNING)

    def _set_state(self, new: RobotState) -> None:
        if new not in TRANSITIONS[self.state]:
            raise InvalidTransition(f"robot {self.id}: {self.state} -> {new} is not allowed")
        self.state = new

    def assign(self, task: Task, tick: int) -> None:
        self._set_state(S.TO_PICKUP)
        self.task = task
        task.status = TaskStatus.ASSIGNED
        task.robot_id = self.id
        task.assigned_tick = tick
        self.goal = None
        self.needs_plan = True
        self.retreating = False

    def go_home(self) -> None:
        self._set_state(S.RETURNING)
        self.goal = self.home
        self.needs_plan = True

    def arrive(self, tick: int, service_ticks: int) -> None:
        """Called when the robot reaches the cell it was driving to."""
        if self.state == S.TO_PICKUP:
            self._set_state(S.LOADING)
            self.service_left = service_ticks
        elif self.state == S.TO_DROPOFF:
            self._set_state(S.UNLOADING)
            self.service_left = service_ticks
        elif self.state == S.RETURNING:
            self._set_state(S.IDLE)
        else:
            raise InvalidTransition(f"robot {self.id} is not driving anywhere ({self.state})")
        self.goal = None

    def finish_service(self, tick: int) -> Task | None:
        """End of loading/unloading. Returns the task if it was just delivered."""
        assert self.task is not None
        if self.state == S.LOADING:
            self._set_state(S.TO_DROPOFF)
            self.task.status = TaskStatus.IN_TRANSIT
            self.task.picked_tick = tick
            self.needs_plan = True
            return None
        delivered = self.task
        delivered.status = TaskStatus.DELIVERED
        delivered.delivered_tick = tick
        self.task = None
        if self.pos == self.home:
            self._set_state(S.IDLE)
        else:
            self.go_home()
        return delivered
