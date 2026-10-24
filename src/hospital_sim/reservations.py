"""Reservation table: a shared calendar of who will be where, and when.

When a robot plans a path it books every (cell, tick) on it. The next robot to
plan treats those bookings as obstacles, so it routes around the first one or
waits. This is the core of *prioritized planning*: robots plan one after another,
and each one respects everything booked before it.

Three kinds of bookings:
    cells   robot R is on cell C at tick t                -> vertex conflicts
    edges   robot R moves from A to B between t and t+1   -> swap (edge) conflicts
    parked  robot R stays on cell C forever from tick t   -> end of every path
"""

from hospital_sim.grid import Cell


class ReservationTable:
    def __init__(self) -> None:
        self._cells: dict[Cell, dict[int, int]] = {}  # cell -> {tick: robot id}
        self._edges: dict[tuple[Cell, Cell, int], int] = {}  # (from, to, tick) -> robot id
        self._parked: dict[Cell, tuple[int, int]] = {}  # cell -> (robot id, from tick)
        # What each robot booked, so its bookings can be removed when it replans.
        self._owned: dict[
            int, tuple[list[tuple[Cell, int]], list[tuple[Cell, Cell, int]], Cell]
        ] = {}

    def reserve(self, robot_id: int, path: list[Cell], start_tick: int) -> None:
        """Book a path. path[i] is the robot's cell at tick start_tick + i.

        The robot is assumed to stay on the last cell until it books a new path.
        """
        self.clear(robot_id)
        cells: list[tuple[Cell, int]] = []
        edges: list[tuple[Cell, Cell, int]] = []
        for i, cell in enumerate(path):
            tick = start_tick + i
            self._cells.setdefault(cell, {})[tick] = robot_id
            cells.append((cell, tick))
            if i + 1 < len(path) and path[i + 1] != cell:
                edge = (cell, path[i + 1], tick)
                self._edges[edge] = robot_id
                edges.append(edge)
        last = path[-1]
        self._parked[last] = (robot_id, start_tick + len(path) - 1)
        self._owned[robot_id] = (cells, edges, last)

    def clear(self, robot_id: int) -> None:
        """Remove every booking of one robot."""
        owned = self._owned.pop(robot_id, None)
        if owned is None:
            return
        cells, edges, last = owned
        for cell, tick in cells:
            if self._cells[cell].get(tick) == robot_id:
                del self._cells[cell][tick]
        for edge in edges:
            if self._edges.get(edge) == robot_id:
                del self._edges[edge]
        if self._parked.get(last, (None, 0))[0] == robot_id:
            del self._parked[last]

    def is_free(self, cell: Cell, tick: int, robot_id: int) -> bool:
        """Is the cell free for this robot at this tick?"""
        owner = self._cells.get(cell, {}).get(tick)
        if owner is not None and owner != robot_id:
            return False
        parked = self._parked.get(cell)
        return parked is None or parked[0] == robot_id or tick < parked[1]

    def can_move(self, src: Cell, dst: Cell, tick: int, robot_id: int) -> bool:
        """Can the robot go from src (at tick) to dst (at tick + 1)? dst == src means waiting."""
        if not self.is_free(dst, tick + 1, robot_id):
            return False  # vertex conflict: someone else will be on dst
        other = self._edges.get((dst, src, tick))
        return other is None or other == robot_id  # edge conflict: head-on swap

    def is_free_from(self, cell: Cell, tick: int, robot_id: int) -> bool:
        """Can the robot stop on this cell at `tick` and stay there indefinitely?"""
        parked = self._parked.get(cell)
        if parked is not None and parked[0] != robot_id:
            return False
        bookings = self._cells.get(cell, {})
        return all(t < tick or owner == robot_id for t, owner in bookings.items())

    def parked_by_other(self, cell: Cell, robot_id: int) -> bool:
        parked = self._parked.get(cell)
        return parked is not None and parked[0] != robot_id
