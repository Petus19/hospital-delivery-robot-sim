"""Hospital map: loading an ASCII file, validating it and answering 'where can I move?'.

Map legend (one character per cell):
    #   wall
    .   floor (corridor or room)
    P   pharmacy dock      L   lab dock       K   kitchen dock
    C   charging station   1-9 ward_1 .. ward_9 dock

All cells with the same letter form one named location, so a location can have
several dock cells (several robots can be served at once).
"""

from collections import deque
from dataclasses import dataclass
from pathlib import Path

# A cell is (x, y): x = column (grows to the right), y = row (grows downwards).
Cell = tuple[int, int]

WALL = "#"
FLOOR = "."
LOCATION_SYMBOLS: dict[str, str] = {
    "P": "pharmacy",
    "L": "lab",
    "K": "kitchen",
    "C": "charging",
    **{str(n): f"ward_{n}" for n in range(1, 10)},
}

# Fixed neighbour order (up, right, down, left) keeps every search deterministic.
DIRECTIONS: tuple[Cell, ...] = ((0, -1), (1, 0), (0, 1), (-1, 0))


class MapError(ValueError):
    """Raised when a map file is malformed."""


@dataclass(frozen=True)
class Grid:
    width: int
    height: int
    walls: frozenset[Cell]
    locations: dict[str, tuple[Cell, ...]]

    def in_bounds(self, cell: Cell) -> bool:
        x, y = cell
        return 0 <= x < self.width and 0 <= y < self.height

    def is_free(self, cell: Cell) -> bool:
        return self.in_bounds(cell) and cell not in self.walls

    def neighbors(self, cell: Cell) -> list[Cell]:
        """Free 4-connected neighbours of a cell."""
        x, y = cell
        result = []
        for dx, dy in DIRECTIONS:
            nxt = (x + dx, y + dy)
            if self.is_free(nxt):
                result.append(nxt)
        return result

    def free_cells(self) -> list[Cell]:
        return [
            (x, y) for y in range(self.height) for x in range(self.width) if self.is_free((x, y))
        ]

    def location_at(self, cell: Cell) -> str | None:
        for name, cells in self.locations.items():
            if cell in cells:
                return name
        return None

    def blocks_passage(self, cell: Cell) -> bool:
        """Would a robot standing on this cell cut a doorway or a one-lane passage?

        Local check: the cell's free neighbours must still be able to reach each
        other inside the surrounding 3x3 block without using the cell itself
        (a small BFS). True in doorways and narrow corridors, False in rooms and
        in the two-lane corridor.
        """
        x, y = cell
        around = self.neighbors(cell)
        if not around:
            return False
        block = {(x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)} - {cell}
        seen = {around[0]}
        queue = deque([around[0]])
        while queue:
            for nxt in self.neighbors(queue.popleft()):
                if nxt in block and nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
        return not all(n in seen for n in around)


def parse_grid(text: str) -> Grid:
    """Build a Grid from map text and validate it. Raises MapError on any problem."""
    rows = [line.rstrip("\r") for line in text.strip("\n").split("\n")]
    if not rows or not rows[0]:
        raise MapError("map is empty")

    width = len(rows[0])
    for y, row in enumerate(rows):
        if len(row) != width:
            raise MapError(
                f"row {y} has length {len(row)}, expected {width} (map must be a rectangle)"
            )

    walls: set[Cell] = set()
    locations: dict[str, list[Cell]] = {}
    for y, row in enumerate(rows):
        for x, char in enumerate(row):
            if char == WALL:
                walls.add((x, y))
            elif char in LOCATION_SYMBOLS:
                locations.setdefault(LOCATION_SYMBOLS[char], []).append((x, y))
            elif char != FLOOR:
                raise MapError(f"unknown character {char!r} at (x={x}, y={y})")

    grid = Grid(
        width=width,
        height=len(rows),
        walls=frozenset(walls),
        locations={name: tuple(cells) for name, cells in sorted(locations.items())},
    )
    _check_border(grid)
    _check_connected(grid)
    return grid


def load_grid(path: str | Path) -> Grid:
    return parse_grid(Path(path).read_text(encoding="utf-8"))


def _check_border(grid: Grid) -> None:
    for x in range(grid.width):
        for y in (0, grid.height - 1):
            if grid.is_free((x, y)):
                raise MapError(f"border cell (x={x}, y={y}) must be a wall")
    for y in range(grid.height):
        for x in (0, grid.width - 1):
            if grid.is_free((x, y)):
                raise MapError(f"border cell (x={x}, y={y}) must be a wall")


def _check_connected(grid: Grid) -> None:
    """Every free cell must be reachable from every other one (plain BFS flood fill)."""
    free = grid.free_cells()
    if not free:
        raise MapError("map has no free cells")
    seen = {free[0]}
    queue = deque([free[0]])
    while queue:
        for nxt in grid.neighbors(queue.popleft()):
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    unreachable = [cell for cell in free if cell not in seen]
    if unreachable:
        raise MapError(f"{len(unreachable)} free cell(s) are unreachable, e.g. {unreachable[0]}")
