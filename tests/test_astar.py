from hospital_sim.grid import parse_grid
from hospital_sim.pathfinding import astar, manhattan, path_length


def assert_valid_path(grid, path, start, goal):
    assert path[0] == start
    assert path[-1] == goal
    for a, b in zip(path, path[1:], strict=False):
        assert manhattan(a, b) == 1, f"jump between {a} and {b}"
        assert grid.is_free(b)


def test_straight_line(small_grid):
    path = astar(small_grid, (1, 1), (7, 1))
    assert_valid_path(small_grid, path, (1, 1), (7, 1))
    assert len(path) - 1 == 6


def test_start_equals_goal(small_grid):
    assert astar(small_grid, (2, 1), (2, 1)) == [(2, 1)]


def test_path_goes_around_walls(small_grid):
    # Lab (1,3) to ward_2 (7,3): the direct row is cut by a wall at (4,3).
    path = astar(small_grid, (1, 3), (7, 3))
    assert_valid_path(small_grid, path, (1, 3), (7, 3))
    assert path_length(small_grid, (1, 3), (7, 3)) == 10


def test_unreachable_goal_returns_none(small_grid):
    # Blocking both openings into the right part makes ward_2 unreachable from the lab.
    assert astar(small_grid, (1, 3), (7, 3), blocked={(5, 2), (7, 2)}) is None


def test_goal_inside_wall_returns_none(small_grid):
    assert astar(small_grid, (1, 1), (0, 0)) is None


def test_blocked_cells_force_detour():
    grid = parse_grid("#######\n#.....#\n#.....#\n#######")
    direct = astar(grid, (1, 1), (5, 1))
    assert len(direct) - 1 == 4
    detour = astar(grid, (1, 1), (5, 1), blocked={(3, 1)})
    assert_valid_path(grid, detour, (1, 1), (5, 1))
    assert (3, 1) not in detour
    assert len(detour) - 1 == 6


def test_astar_is_optimal_against_bfs(hospital_grid):
    """A* must find exactly the BFS distance (BFS is optimal on unit-cost grids)."""
    from collections import deque

    start = hospital_grid.locations["pharmacy"][0]
    dist = {start: 0}
    queue = deque([start])
    while queue:
        cell = queue.popleft()
        for nxt in hospital_grid.neighbors(cell):
            if nxt not in dist:
                dist[nxt] = dist[cell] + 1
                queue.append(nxt)
    for name, cells in hospital_grid.locations.items():
        for goal in cells:
            assert path_length(hospital_grid, start, goal) == dist[goal], name
