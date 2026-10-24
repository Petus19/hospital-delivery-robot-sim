import pytest

from hospital_sim.models import RobotState, Task, TaskStatus
from hospital_sim.robot import InvalidTransition, Robot
from hospital_sim.simulation import SimConfig, Simulation


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


def test_single_robot_delivers_task(small_grid):
    robot = Robot(id=0, pos=(3, 1), home=(3, 1))
    sim = Simulation(small_grid, [robot], [make_task()], SimConfig(load_ticks=2, unload_ticks=2))
    sim.run(max_ticks=100)
    task = sim.tasks[0]
    assert task.status == TaskStatus.DELIVERED
    # (3,1) -> pharmacy (1,1): 2 moves, load 2 ticks, -> ward_2 (7,3): 8 moves, unload 2 ticks.
    assert task.picked_tick == 4
    assert task.delivered_tick == 14
    assert robot.state == RobotState.IDLE
    assert robot.pos == robot.home
    assert robot.distance == 2 + 8 + 6  # 6 moves back home


def test_urgent_task_is_served_first(small_grid):
    robot = Robot(id=0, pos=(3, 1), home=(3, 1))
    normal = make_task(id=1)
    urgent = make_task(id=2, dropoff="ward_1", priority="urgent")
    sim = Simulation(small_grid, [robot], [normal, urgent])
    sim.step()
    assert robot.task is urgent


def test_unknown_location_is_rejected(small_grid):
    robot = Robot(id=0, pos=(3, 1), home=(3, 1))
    with pytest.raises(ValueError, match="unknown location"):
        Simulation(small_grid, [robot], [make_task(dropoff="ward_99")])
