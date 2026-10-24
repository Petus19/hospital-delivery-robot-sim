"""Smoke test: the viewer can draw frames without a real display."""

import os

import pytest

from hospital_sim.models import Task
from hospital_sim.robot import Robot
from hospital_sim.simulation import Simulation


@pytest.fixture(autouse=True)
def headless_display(monkeypatch):
    monkeypatch.setitem(os.environ, "SDL_VIDEODRIVER", "dummy")


def test_viewer_draws_frames(hospital_grid):
    from hospital_sim.viz import Viewer

    home = hospital_grid.locations["charging"][0]
    sim = Simulation(
        hospital_grid,
        [Robot(id=0, pos=home, home=home)],
        [Task(1, "pharmacy", "ward_3", "insulin", priority="urgent")],
    )
    viewer = Viewer(sim, max_ticks=50)
    for _ in range(10):
        sim.step()
        viewer._draw()
    assert viewer.screen.get_width() > 0
