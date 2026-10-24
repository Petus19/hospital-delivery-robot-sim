"""Smoke test: the viewer can draw frames without a real display."""

import os

import pytest

from hospital_sim.models import Priority, Task
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
        [Task(1, "pharmacy", "ward_3", "insulin", priority=Priority.URGENT)],
    )
    viewer = Viewer(sim, max_ticks=50)
    for _ in range(10):
        sim.step()
        viewer._draw()
    assert viewer.screen.get_width() > 0


def test_typed_sentence_is_sent_to_callback(hospital_grid):
    import pygame

    from hospital_sim.viz import Viewer

    home = hospital_grid.locations["charging"][0]
    sim = Simulation(hospital_grid, [Robot(id=0, pos=home, home=home)])
    received = []
    viewer = Viewer(sim, max_ticks=10, on_text=lambda text: received.append(text) or "ok")
    viewer.typing = "deliver insulin from pharmacy to ward 3"
    viewer._handle_typing(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    assert received == ["deliver insulin from pharmacy to ward 3"]
    assert viewer.message == "ok"
    assert viewer.typing is None


def test_typing_keeps_the_previous_pause_state(hospital_grid):
    import pygame

    from hospital_sim.viz import Viewer

    home = hospital_grid.locations["charging"][0]
    sim = Simulation(hospital_grid, [Robot(id=0, pos=home, home=home)])
    viewer = Viewer(sim, max_ticks=10, on_text=lambda text: "ok")
    for paused in (True, False):
        viewer.paused = paused
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_t))
        viewer._handle_events()
        assert viewer.typing == "" and viewer.paused  # typing always pauses
        viewer.typing = "insulin from pharmacy to ward 3"
        viewer._handle_typing(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
        assert viewer.paused is paused
