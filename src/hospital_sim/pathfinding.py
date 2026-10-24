"""Path planning on the grid.

`astar` is classic A* in space only (x, y). It ignores other robots and is used
by the dispatcher to measure real travel distances.

`space_time_astar` is the same algorithm in (x, y, time). It avoids the paths
other robots have already booked in the reservation table.
"""

import heapq
from collections.abc import Collection

from hospital_sim.grid import Cell, Grid
from hospital_sim.reservations import ReservationTable

State = tuple[Cell, int]  # space-time search node: (cell, steps since start_tick)


def manhattan(a: Cell, b: Cell) -> int:
    """Admissible heuristic for 4-connected moves: it never overestimates the true distance."""
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def astar(grid: Grid, start: Cell, goal: Cell, blocked: Collection[Cell] = ()) -> list[Cell] | None:
    """Shortest path from start to goal (both included), or None if the goal is unreachable.

    Same idea as BFS, but the queue is a priority queue ordered by
    f = g (steps so far) + h (Manhattan distance still to go), so cells that look
    closer to the goal are expanded first.
    """
    if not grid.is_free(start) or not grid.is_free(goal) or goal in blocked:
        return None

    # Heap entries: (f, g, cell). Ties are broken by g, then by the cell tuple itself,
    # which keeps the result deterministic.
    open_heap: list[tuple[int, int, Cell]] = [(manhattan(start, goal), 0, start)]
    g_score: dict[Cell, int] = {start: 0}
    came_from: dict[Cell, Cell] = {}

    while open_heap:
        _, g, cell = heapq.heappop(open_heap)
        if cell == goal:
            return _reconstruct(came_from, cell)
        if g > g_score[cell]:
            continue  # stale entry: a shorter way to this cell was already found
        for nxt in grid.neighbors(cell):
            if nxt in blocked:
                continue
            new_g = g + 1
            if new_g < g_score.get(nxt, new_g + 1):
                g_score[nxt] = new_g
                came_from[nxt] = cell
                heapq.heappush(open_heap, (new_g + manhattan(nxt, goal), new_g, nxt))
    return None


def path_length(grid: Grid, start: Cell, goal: Cell, blocked: Collection[Cell] = ()) -> int | None:
    """Number of moves on the shortest path, or None if unreachable."""
    path = astar(grid, start, goal, blocked)
    return None if path is None else len(path) - 1


def space_time_astar(
    grid: Grid,
    start: Cell,
    goal: Cell,
    start_tick: int,
    reservations: ReservationTable,
    robot_id: int,
    blocked: Collection[Cell] = (),
    max_steps: int = 200,
) -> list[Cell] | None:
    """Cooperative A*: plan in (x, y, time) around other robots' reservations.

    Differences from plain `astar`:
      * a search node is (cell, tick) instead of just cell, so the same cell can
        be visited again later in time;
      * "wait in place" is a legal move, next to up/right/down/left;
      * a move is allowed only if the reservation table says so (no vertex and
        no swap conflict);
      * the goal counts only if the robot can stay there afterwards.

    Returns cells for ticks start_tick, start_tick + 1, ... (repeated cell = wait),
    or None if no plan exists within `max_steps` ticks.
    """
    # Cheap checks first, so hopeless searches don't explore the whole time horizon.
    if reservations.parked_by_other(goal, robot_id):
        return None
    if astar(grid, start, goal, [c for c in blocked if c != start]) is None:
        return None

    open_heap: list[tuple[int, int, Cell]] = [(manhattan(start, goal), 0, start)]
    came_from: dict[State, State] = {}
    seen: set[State] = {(start, 0)}

    while open_heap:
        _, steps, cell = heapq.heappop(open_heap)
        tick = start_tick + steps
        if cell == goal and reservations.is_free_from(goal, tick, robot_id):
            path = _reconstruct(came_from, (cell, steps))
            return [c for c, _ in path]
        if steps >= max_steps:
            continue
        for nxt in [cell, *grid.neighbors(cell)]:  # first option: wait where we are
            if nxt != cell and nxt in blocked:
                continue
            state = (nxt, steps + 1)
            if state in seen or not reservations.can_move(cell, nxt, tick, robot_id):
                continue
            seen.add(state)
            came_from[state] = (cell, steps)
            heapq.heappush(open_heap, (steps + 1 + manhattan(nxt, goal), steps + 1, nxt))
    return None


def _reconstruct[T](came_from: dict[T, T], cell: T) -> list[T]:
    path = [cell]
    while cell in came_from:
        cell = came_from[cell]
        path.append(cell)
    path.reverse()
    return path
