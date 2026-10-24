import pytest

from hospital_sim.grid import MapError, parse_grid


def test_small_map_locations(small_grid):
    assert small_grid.width == 9
    assert small_grid.height == 5
    assert small_grid.locations["pharmacy"] == ((1, 1),)
    assert small_grid.locations["ward_2"] == ((7, 3),)
    assert small_grid.location_at((1, 3)) == "lab"
    assert small_grid.location_at((2, 1)) is None


def test_hospital_map_loads(hospital_grid):
    names = set(hospital_grid.locations)
    assert {"pharmacy", "lab", "kitchen", "charging"} <= names
    assert {f"ward_{n}" for n in range(1, 7)} <= names
    assert len(hospital_grid.locations["charging"]) == 4


def test_neighbors_skip_walls(small_grid):
    assert small_grid.neighbors((1, 1)) == [(2, 1), (1, 2)]


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("", "empty"),
        ("#####\n#..#\n#####", "rectangle"),
        ("#####\n#.X.#\n#####", "unknown character"),
        ("#####\n#....\n#####", "border"),
        ("#######\n#..#..#\n#######", "unreachable"),
    ],
)
def test_invalid_maps_are_rejected(text, message):
    with pytest.raises(MapError, match=message):
        parse_grid(text)
