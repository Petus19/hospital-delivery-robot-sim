import pytest

from hospital_sim.models import RobotState, Task, TaskStatus
from hospital_sim.robot import InvalidTransition, Robot


def make_task(**kwargs):
    defaults = {"id": 1, "pickup": "pharmacy", "dropoff": "ward_2", "item": "insulin"}
    return Task(**(defaults | kwargs))


def test_full_cycle_of_states():
    robot = Robot(id=0, pos=(0, 0), home=(0, 0))
    task = make_task()
    robot.assign(task, tick=0)
    assert robot.state == RobotState.TO_PICKUP
    robot.arrive(tick=5, service_ticks=2)
    assert robot.state == RobotState.LOADING
    robot.finish_service(tick=7)
    assert robot.state == RobotState.TO_DROPOFF
    assert task.status == TaskStatus.IN_TRANSIT
    robot.arrive(tick=12, service_ticks=2)
    assert robot.state == RobotState.UNLOADING
    robot.pos = (3, 3)
    delivered = robot.finish_service(tick=14)
    assert delivered is task
    assert task.status == TaskStatus.DELIVERED
    assert robot.state == RobotState.RETURNING  # not at home, so it drives back
    robot.arrive(tick=20, service_ticks=0)
    assert robot.state == RobotState.IDLE


def test_illegal_transition_raises():
    robot = Robot(id=0, pos=(0, 0), home=(0, 0))
    with pytest.raises(InvalidTransition):
        robot.arrive(tick=0, service_ticks=1)  # IDLE robot cannot "arrive" at a pickup
    robot.assign(make_task(), tick=0)
    with pytest.raises(InvalidTransition):
        robot.assign(make_task(id=2), tick=0)  # already busy
