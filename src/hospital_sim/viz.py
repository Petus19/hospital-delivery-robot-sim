"""Pygame window that shows a running simulation.

The viewer only *reads* simulation state and calls `sim.step()`; it never changes
robots or tasks directly. Delete this file and the simulator still works headless.

Keys: SPACE pause | N single step | UP/DOWN speed | T type a task | ESC quit
"""

from collections.abc import Callable

import pygame

from hospital_sim.grid import Cell
from hospital_sim.models import Priority, RobotState, TaskStatus
from hospital_sim.simulation import Simulation

CELL = 30
PANEL_WIDTH = 380
FPS = 60
SPEEDS = [1, 2, 4, 8, 16, 32]  # ticks per second

BACKGROUND = (24, 26, 32)
WALL = (55, 60, 72)
FLOOR = (225, 228, 232)
TEXT = (235, 235, 240)
DIM_TEXT = (150, 155, 165)
URGENT = (230, 70, 70)

LOCATION_COLORS = {
    "pharmacy": (170, 220, 170),
    "lab": (170, 200, 240),
    "kitchen": (245, 215, 160),
    "charging": (200, 200, 200),
}
WARD_COLOR = (230, 190, 230)

STATE_COLORS = {
    RobotState.IDLE: (120, 120, 130),
    RobotState.TO_PICKUP: (50, 120, 230),
    RobotState.LOADING: (240, 170, 30),
    RobotState.TO_DROPOFF: (30, 170, 90),
    RobotState.UNLOADING: (240, 120, 30),
    RobotState.RETURNING: (150, 90, 200),
}


class Viewer:
    def __init__(
        self,
        sim: Simulation,
        max_ticks: int,
        title: str = "Hospital delivery robots",
        on_text: Callable[[str], str] | None = None,
    ) -> None:
        """`on_text` handles a typed natural-language task and returns a status message."""
        self.sim = sim
        self.max_ticks = max_ticks
        self.on_text = on_text
        self.paused = False
        self.speed_index = 2
        self.typing: str | None = None  # text being typed, None when not typing
        self.message = ""
        pygame.init()
        width = sim.grid.width * CELL + PANEL_WIDTH
        height = max(sim.grid.height * CELL, 480)
        self.screen = pygame.display.set_mode((width, height))
        pygame.display.set_caption(title)
        self.font = pygame.font.Font(None, 20)
        self.small = pygame.font.Font(None, 16)
        self.big = pygame.font.Font(None, 26)

    def run(self) -> None:
        clock = pygame.time.Clock()
        elapsed = 0.0
        running = True
        while running:
            running = self._handle_events()
            elapsed += clock.tick(FPS) / 1000
            tick_length = 1 / SPEEDS[self.speed_index]
            while not self.paused and elapsed >= tick_length and self._can_step():
                self.sim.step()
                elapsed -= tick_length
            if self.paused or not self._can_step():
                elapsed = 0.0
            self._draw()
        pygame.quit()

    def _can_step(self) -> bool:
        return self.sim.tick < self.max_ticks and not self.sim.is_finished

    # ------------------------------------------------------------------ input

    def _handle_events(self) -> bool:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN:
                if self.typing is not None:
                    self._handle_typing(event)
                elif event.key in (pygame.K_ESCAPE, pygame.K_q):
                    return False
                elif event.key == pygame.K_SPACE:
                    self.paused = not self.paused
                elif event.key == pygame.K_n and self.paused and self._can_step():
                    self.sim.step()
                elif event.key in (pygame.K_UP, pygame.K_PLUS, pygame.K_KP_PLUS):
                    self.speed_index = min(self.speed_index + 1, len(SPEEDS) - 1)
                elif event.key in (pygame.K_DOWN, pygame.K_MINUS, pygame.K_KP_MINUS):
                    self.speed_index = max(self.speed_index - 1, 0)
                elif event.key == pygame.K_t and self.on_text is not None:
                    self.typing = ""
                    self.paused = True
                    pygame.key.start_text_input()
            if event.type == pygame.TEXTINPUT and self.typing is not None:
                self.typing += event.text
        return True

    def _handle_typing(self, event: pygame.event.Event) -> None:
        assert self.typing is not None
        if event.key == pygame.K_RETURN:
            text, self.typing = self.typing, None
            pygame.key.stop_text_input()
            if text.strip() and self.on_text is not None:
                self.message = "Parsing..."
                self._draw()
                self.message = self.on_text(text)
            self.paused = False
        elif event.key == pygame.K_ESCAPE:
            self.typing = None
            pygame.key.stop_text_input()
            self.paused = False
        elif event.key == pygame.K_BACKSPACE:
            self.typing = self.typing[:-1]

    # ------------------------------------------------------------------ drawing

    def _draw(self) -> None:
        self.screen.fill(BACKGROUND)
        self._draw_map()
        self._draw_paths()
        self._draw_robots()
        self._draw_panel()
        if self.typing is not None:
            self._draw_input_box()
        pygame.display.flip()

    def _rect(self, cell: Cell) -> pygame.Rect:
        return pygame.Rect(cell[0] * CELL, cell[1] * CELL, CELL, CELL)

    def _center(self, cell: Cell) -> tuple[int, int]:
        return cell[0] * CELL + CELL // 2, cell[1] * CELL + CELL // 2

    def _draw_map(self) -> None:
        grid = self.sim.grid
        for y in range(grid.height):
            for x in range(grid.width):
                color = WALL if (x, y) in grid.walls else FLOOR
                pygame.draw.rect(self.screen, color, self._rect((x, y)))
        for cell in self.sim.blocked:
            pygame.draw.rect(self.screen, (90, 30, 30), self._rect(cell))
            pygame.draw.line(
                self.screen, URGENT, self._rect(cell).topleft, self._rect(cell).bottomright, 2
            )
        for name, cells in grid.locations.items():
            color = LOCATION_COLORS.get(name, WARD_COLOR)
            for cell in cells:
                pygame.draw.rect(self.screen, color, self._rect(cell).inflate(-2, -2))
            # Name in the corner of the first dock cell.
            label = self.small.render(name.replace("_", " "), True, (30, 30, 30))
            x, y = cells[0]
            self.screen.blit(label, (x * CELL + 2, y * CELL + 2))

    def _draw_paths(self) -> None:
        for robot in self.sim.robots:
            if not robot.path:
                continue
            color = STATE_COLORS[robot.state]
            points = [self._center(robot.pos)] + [self._center(c) for c in robot.path]
            if len(points) > 1:
                pygame.draw.lines(self.screen, color, False, points, 3)
            pygame.draw.circle(self.screen, color, self._center(robot.path[-1]), 5)

    def _draw_robots(self) -> None:
        for robot in self.sim.robots:
            center = self._center(robot.pos)
            pygame.draw.circle(self.screen, STATE_COLORS[robot.state], center, CELL // 2 - 2)
            if robot.task is not None and robot.task.priority == Priority.URGENT:
                pygame.draw.circle(self.screen, URGENT, center, CELL // 2 - 2, 3)
            label = self.font.render(str(robot.id), True, (255, 255, 255))
            self.screen.blit(label, label.get_rect(center=center))

    def _draw_panel(self) -> None:
        x0 = self.sim.grid.width * CELL + 14
        y = 12
        status = "PAUSED" if self.paused else f"{SPEEDS[self.speed_index]} ticks/s"
        if self.sim.is_finished:
            status = "FINISHED"
        y = self._text(f"Tick {self.sim.tick}   {status}", x0, y, self.big)
        delivered = sum(t.status == TaskStatus.DELIVERED for t in self.sim.tasks)
        y = self._text(f"Delivered {delivered}/{len(self.sim.tasks)}", x0, y + 4)
        active = [e for e in self.sim.events if e.is_active(self.sim.tick)]
        if active:
            until = max(e.end for e in active)
            closed = f"Closed: {len(self.sim.blocked)} cell(s) until tick {until}"
            y = self._text(closed, x0, y, color=URGENT)

        y = self._text("Robots", x0, y + 10, self.big)
        for robot in self.sim.robots:
            pygame.draw.circle(self.screen, STATE_COLORS[robot.state], (x0 + 6, y + 7), 6)
            task = f"#{robot.task.id} {robot.task.item}" if robot.task else ""
            y = self._text(f"{robot.id}  {robot.state.value:<11} {task}", x0 + 18, y)

        y = self._text("Queue", x0, y + 10, self.big)
        for task in self.sim.queue[:8]:
            color = URGENT if task.priority == Priority.URGENT else TEXT
            line = f"#{task.id} {task.item}: {task.pickup} -> {task.dropoff}"
            y = self._text(line, x0, y, color=color)
        if len(self.sim.queue) > 8:
            y = self._text(f"... and {len(self.sim.queue) - 8} more", x0, y, color=DIM_TEXT)
        if not self.sim.queue:
            y = self._text("(empty)", x0, y, color=DIM_TEXT)

        if self.message:
            y += 10
            for line in self._wrap(self.message, PANEL_WIDTH - 28):
                y = self._text(line, x0, y, color=(120, 200, 255))
        help_lines = ["SPACE pause   N step   UP/DOWN speed   ESC quit"]
        if self.on_text is not None:
            help_lines.append("T  type a task in plain English / Slovak")
        bottom = self.screen.get_height() - 18 * len(help_lines) - 6
        for line in help_lines:
            bottom = self._text(line, x0, bottom, self.small, DIM_TEXT)

    def _draw_input_box(self) -> None:
        width = self.screen.get_width() - 40
        box = pygame.Rect(20, self.screen.get_height() // 2 - 30, width, 60)
        pygame.draw.rect(self.screen, (15, 15, 20), box)
        pygame.draw.rect(self.screen, (120, 200, 255), box, 2)
        prompt = "New task (Enter to send, Esc to cancel):"
        self._text(prompt, box.x + 10, box.y + 6, self.small, DIM_TEXT)
        self._text((self.typing or "") + "_", box.x + 10, box.y + 26, self.big)

    def _wrap(self, text: str, width: int) -> list[str]:
        """Split text into lines that fit into `width` pixels (word wrap)."""
        lines: list[str] = []
        for word in text.split():
            candidate = f"{lines[-1]} {word}" if lines else word
            if lines and self.font.size(candidate)[0] <= width:
                lines[-1] = candidate
            else:
                lines.append(word)
        return lines

    def _text(
        self,
        text: str,
        x: int,
        y: int,
        font: pygame.font.Font | None = None,
        color: tuple[int, int, int] = TEXT,
    ) -> int:
        """Draw one line of text and return the y coordinate for the next line."""
        font = font or self.font
        self.screen.blit(font.render(text, True, color), (x, y))
        return y + font.get_linesize() + 2
