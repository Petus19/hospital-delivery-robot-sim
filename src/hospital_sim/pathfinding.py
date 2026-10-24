"""Path planning on the grid.

`astar` is classic A* in space only (x, y). It ignores other robots and is used
by the dispatcher to measure real travel distances.
"""

import heapq
from collections.abc import Collection

from hospital_sim.grid import Cell, Grid


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


def _reconstruct(came_from: dict[Cell, Cell], cell: Cell) -> list[Cell]:
    path = [cell]
    while cell in came_from:
        cell = came_from[cell]
        path.append(cell)
    path.reverse()
    return path
