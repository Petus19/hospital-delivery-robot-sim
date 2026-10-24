from hospital_sim.reservations import ReservationTable


def test_reserved_cell_is_taken_for_others_only():
    table = ReservationTable()
    table.reserve(robot_id=1, path=[(1, 1), (2, 1), (3, 1)], start_tick=0)
    assert not table.is_free((2, 1), 1, robot_id=2)
    assert table.is_free((2, 1), 1, robot_id=1)  # own booking is not an obstacle
    assert table.is_free((2, 1), 2, robot_id=2)  # robot 1 has moved on by tick 2


def test_last_cell_is_parked_forever():
    table = ReservationTable()
    table.reserve(robot_id=1, path=[(1, 1), (2, 1)], start_tick=0)
    assert table.is_free((2, 1), 0, robot_id=2)  # robot 1 is not there yet
    assert not table.is_free((2, 1), 1, robot_id=2)
    assert not table.is_free((2, 1), 500, robot_id=2)
    assert table.parked_by_other((2, 1), robot_id=2)


def test_vertex_conflict_blocks_move():
    table = ReservationTable()
    table.reserve(robot_id=1, path=[(1, 1), (2, 1)], start_tick=0)
    # Robot 2 wants to enter (2,1) at tick 1 as well.
    assert not table.can_move((3, 1), (2, 1), 0, robot_id=2)


def test_swap_conflict_blocks_move():
    table = ReservationTable()
    table.reserve(robot_id=1, path=[(1, 1), (2, 1), (3, 1)], start_tick=0)
    # Robot 2 at (2,1) at tick 0 moving to (1,1) would swap with robot 1 head-on.
    # (1,1) itself is free at tick 1, so only the edge check catches this.
    assert table.is_free((1, 1), 1, robot_id=2)
    assert not table.can_move((2, 1), (1, 1), 0, robot_id=2)


def test_clear_removes_all_bookings():
    table = ReservationTable()
    table.reserve(robot_id=1, path=[(1, 1), (2, 1)], start_tick=0)
    table.clear(1)
    assert table.is_free((2, 1), 1, robot_id=2)
    assert table.can_move((2, 1), (1, 1), 0, robot_id=2)
    assert not table.parked_by_other((2, 1), robot_id=2)


def test_is_free_from_checks_future_bookings():
    table = ReservationTable()
    # Robot 1 passes through (2,1) at tick 5 and parks at (3,1).
    table.reserve(robot_id=1, path=[(1, 1)] * 5 + [(2, 1), (3, 1)], start_tick=0)
    assert not table.is_free_from((2, 1), 2, robot_id=2)  # would be in robot 1's way at tick 5
    assert table.is_free_from((2, 1), 6, robot_id=2)
    assert not table.is_free_from((3, 1), 100, robot_id=2)  # parked forever
