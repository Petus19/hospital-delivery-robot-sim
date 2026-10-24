from hospital_sim.dispatcher import assign_tasks, queue_order
from hospital_sim.grid import parse_grid
from hospital_sim.models import Priority, Task
from hospital_sim.robot import Robot

# A robot at (1,3) is 2 cells from the pharmacy (1,1) in a straight line, but a wall
# is in the way, so its real path is 12 moves. A robot at (4,1) is 3 cells away
# with a clear corridor.
WALL_MAP = """\
#########
#P......#
######..#
#.......#
#########
"""


def task(id, priority=Priority.NORMAL, created=0, pickup="pharmacy"):
    return Task(id, pickup, "pharmacy", "x", priority, created_tick=created)


def test_nearest_robot_by_path_not_straight_line():
    grid = parse_grid(WALL_MAP)
    behind_wall = Robot(id=0, pos=(1, 3), home=(1, 3))  # straight-line distance 2
    in_corridor = Robot(id=1, pos=(4, 1), home=(4, 1))  # straight-line distance 3
    [(t, robot)] = assign_tasks([task(1)], [behind_wall, in_corridor], grid)
    assert robot is in_corridor


def test_urgent_task_gets_the_closest_robot(small_grid):
    near = Robot(id=0, pos=(2, 1), home=(2, 1))
    far = Robot(id=1, pos=(6, 1), home=(6, 1))
    normal = task(1, created=0)
    urgent = task(2, Priority.URGENT, created=5)
    pairs = {t.id: r for t, r in assign_tasks([normal, urgent], [near, far], small_grid)}
    assert pairs[urgent.id] is near
    assert pairs[normal.id] is far


def test_busy_robots_are_skipped(small_grid):
    busy = Robot(id=0, pos=(2, 1), home=(2, 1))
    busy.assign(task(9), tick=0)
    free = Robot(id=1, pos=(6, 1), home=(6, 1))
    [(_, robot)] = assign_tasks([task(1)], [busy, free], small_grid)
    assert robot is free


def test_more_tasks_than_robots(small_grid):
    robot = Robot(id=0, pos=(2, 1), home=(2, 1))
    pairs = assign_tasks([task(1), task(2)], [robot], small_grid)
    assert len(pairs) == 1


def test_queue_order():
    tasks = [task(1, created=3), task(2, Priority.URGENT, created=9), task(3, created=1)]
    assert [t.id for t in sorted(tasks, key=queue_order)] == [2, 3, 1]
