from hospital_sim.grid import parse_grid
from hospital_sim.models import BlockEvent, Task, TaskStatus
from hospital_sim.robot import Robot
from hospital_sim.simulation import SimConfig, Simulation

# Two routes from the pharmacy (left) to ward_1 (right): the short top row and a
# longer detour through the bottom row.
LOOP_MAP = """\
#########
#P.....1#
#.#####.#
#.......#
#########
"""
TOP_ROW = frozenset({(4, 1)})


def make_sim(events, start=(2, 1)):
    grid = parse_grid(LOOP_MAP)
    robot = Robot(id=0, pos=start, home=start)
    task = Task(1, "pharmacy", "ward_1", "insulin")
    return Simulation(grid, [robot], [task], SimConfig(load_ticks=1, unload_ticks=1), events)


def run_and_watch(sim, max_ticks=200):
    """Run, asserting no robot ever stands on a closed cell; return visited cells."""
    visited = []
    while sim.tick < max_ticks and not sim.is_finished:
        sim.step()
        for robot in sim.robots:
            assert robot.pos not in sim.blocked, f"robot on closed cell at tick {sim.tick}"
            visited.append(robot.pos)
    return visited


def test_robot_detours_around_closed_corridor():
    sim = make_sim([BlockEvent(TOP_ROW, start=0, end=500)])
    visited = run_and_watch(sim)
    assert sim.tasks[0].status == TaskStatus.DELIVERED
    assert (4, 1) not in visited
    assert (4, 3) in visited  # took the bottom detour


def test_blockage_starting_mid_route_triggers_replan():
    # The robot has already planned the short top route when the corridor closes.
    sim = make_sim([BlockEvent(TOP_ROW, start=4, end=500)])
    visited = run_and_watch(sim)
    assert sim.tasks[0].status == TaskStatus.DELIVERED
    assert sim.blockage_replans >= 1
    assert (4, 1) not in visited


def test_reopened_corridor_is_used_again():
    sim = make_sim([BlockEvent(TOP_ROW, start=0, end=3)])
    visited = run_and_watch(sim)
    assert sim.blocked == set()
    assert (4, 1) in visited  # back on the short route after the blockage ended


def test_unreachable_goal_waits_until_reopened():
    grid = parse_grid(LOOP_MAP)
    robot = Robot(id=0, pos=(2, 1), home=(2, 1))
    task = Task(1, "pharmacy", "ward_1", "insulin")
    ward = frozenset(grid.locations["ward_1"])
    sim = Simulation(
        grid,
        [robot],
        [task],
        SimConfig(load_ticks=1, unload_ticks=1),
        [BlockEvent(ward, start=0, end=40)],
    )
    run_and_watch(sim)
    assert task.status == TaskStatus.DELIVERED
    assert task.delivered_tick is not None and task.delivered_tick > 40
