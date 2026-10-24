from pathlib import Path

import pytest

from hospital_sim.grid import Grid, load_grid, parse_grid

ROOT = Path(__file__).resolve().parent.parent

# Small map used by most tests: one corridor, a wall with a gap, a few locations.
SMALL_MAP = """\
#########
#P.....1#
#.###.#.#
#L..#..2#
#########
"""


@pytest.fixture
def small_grid() -> Grid:
    return parse_grid(SMALL_MAP)


@pytest.fixture
def hospital_grid() -> Grid:
    return load_grid(ROOT / "maps" / "hospital.txt")
