"""Plain data types shared by the whole simulator."""

from dataclasses import dataclass
from enum import StrEnum


class Priority(StrEnum):
    NORMAL = "normal"
    URGENT = "urgent"


class TaskStatus(StrEnum):
    QUEUED = "queued"  # waiting for a robot
    ASSIGNED = "assigned"  # a robot is driving to the pickup
    IN_TRANSIT = "in_transit"  # loaded, on the way to the dropoff
    DELIVERED = "delivered"


class RobotState(StrEnum):
    IDLE = "idle"
    TO_PICKUP = "to_pickup"
    LOADING = "loading"
    TO_DROPOFF = "to_dropoff"
    UNLOADING = "unloading"
    RETURNING = "returning"  # driving back to its home charger


@dataclass
class Task:
    """One delivery request, e.g. 'insulin from pharmacy to ward_3, urgent'."""

    id: int
    pickup: str
    dropoff: str
    item: str
    priority: Priority = Priority.NORMAL
    created_tick: int = 0
    status: TaskStatus = TaskStatus.QUEUED
    robot_id: int | None = None
    assigned_tick: int | None = None
    picked_tick: int | None = None
    delivered_tick: int | None = None

    @property
    def queue_time(self) -> int | None:
        """Ticks spent waiting in the queue before a robot took the task."""
        return None if self.assigned_tick is None else self.assigned_tick - self.created_tick

    @property
    def delivery_time(self) -> int | None:
        """Ticks from creation to delivery (what a nurse actually experiences)."""
        return None if self.delivered_tick is None else self.delivered_tick - self.created_tick
