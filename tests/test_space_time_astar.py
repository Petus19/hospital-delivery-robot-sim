from hospital_sim.grid import parse_grid
from hospital_sim.pathfinding import astar, manhattan, space_time_astar
from hospital_sim.reservations import ReservationTable

# A one-cell-wide corridor with a single side pocket at (3,2) where a robot can step aside.
POCKET_MAP = """\
#######
#.....#
###.###
#######
"""


def assert_no_conflicts(a, b):
    """Two timed paths never share a cell at the same tick and never swap cells."""
    length = max(len(a), len(b))
    a = a + [a[-1]] * (length - len(a))  # robots stay on their last cell
    b = b + [b[-1]] * (length - len(b))
    for t in range(length):
        assert a[t] != b[t], f"vertex conflict at tick {t} on {a[t]}"
        if t + 1 < length:
            assert not (a[t] == b[t + 1] and b[t] == a[t + 1]), f"swap at tick {t}"


def assert_steps_valid(path):
    for x, y in zip(path, path[1:], strict=False):
        assert manhattan(x, y) <= 1  # move to a neighbor or wait


def test_without_other_robots_it_matches_astar(hospital_grid):
    start = hospital_grid.locations["charging"][0]
    goal = hospital_grid.locations["ward_9"][0]
    path = space_time_astar(hospital_grid, start, goal, 0, ReservationTable(), robot_id=1)
    assert path == astar(hospital_grid, start, goal)


def test_robot_steps_into_pocket_to_let_other_pass():
    grid = parse_grid(POCKET_MAP)
    table = ReservationTable()
    first = [(1, 1), (2, 1), (3, 1), (4, 1), (5, 1)]
    table.reserve(robot_id=1, path=first, start_tick=0)

    second = space_time_astar(grid, (4, 1), (1, 1), 0, table, robot_id=2)
    assert second is not None
    assert second[-1] == (1, 1)
    assert (3, 2) in second  # it had to use the pocket
    assert_steps_valid(second)
    assert_no_conflicts(first, second)


def test_robot_waits_when_path_is_crossed():
    grid = parse_grid("#######\n#.....#\n#..#..#\n#######")
    table = ReservationTable()
    # Robot 1 goes down through (2,1) -> (2,2) at ticks 1-2 and parks at (2,2).
    table.reserve(robot_id=1, path=[(2, 1), (2, 1), (2, 2)], start_tick=0)
    path = space_time_astar(grid, (1, 1), (5, 1), 0, table, robot_id=2)
    assert path is not None
    assert_no_conflicts([(2, 1), (2, 1), (2, 2)], path)
    assert len(path) - 1 > 4  # longer than the free-road 4 moves


def test_goal_parked_by_other_robot_is_rejected():
    grid = parse_grid(POCKET_MAP)
    table = ReservationTable()
    table.reserve(robot_id=1, path=[(5, 1)], start_tick=0)
    assert space_time_astar(grid, (1, 1), (5, 1), 0, table, robot_id=2) is None


def test_impossible_head_on_in_corridor_returns_none():
    grid = parse_grid("#######\n#.....#\n#######")
    table = ReservationTable()
    table.reserve(robot_id=1, path=[(1, 1), (2, 1), (3, 1), (4, 1)], start_tick=0)
    assert space_time_astar(grid, (5, 1), (1, 1), 0, table, robot_id=2, max_steps=30) is None
