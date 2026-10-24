"""Metrics: turn a finished (or stopped) simulation into tables and files.

Everything here only reads the simulation. Output:
    tasks.csv     one row per task (times in ticks)
    robots.csv    one row per robot (distance, waits, utilisation)
    summary.json  fleet-level numbers for a quick comparison between runs
"""

import csv
import json
from pathlib import Path
from statistics import mean
from typing import Any

from hospital_sim.models import Priority
from hospital_sim.simulation import Simulation


def task_rows(sim: Simulation) -> list[dict[str, Any]]:
    return [
        {
            "id": t.id,
            "item": t.item,
            "pickup": t.pickup,
            "dropoff": t.dropoff,
            "priority": t.priority.value,
            "status": t.status.value,
            "robot_id": t.robot_id,
            "created_tick": t.created_tick,
            "assigned_tick": t.assigned_tick,
            "picked_tick": t.picked_tick,
            "delivered_tick": t.delivered_tick,
            "queue_time": t.queue_time,
            "delivery_time": t.delivery_time,
        }
        for t in sim.tasks
    ]


def robot_rows(sim: Simulation) -> list[dict[str, Any]]:
    ticks = max(sim.tick, 1)
    return [
        {
            "id": r.id,
            "distance": r.distance,
            "busy_ticks": r.busy_ticks,
            "utilization": round(r.busy_ticks / ticks, 3),
            "planned_waits": r.planned_waits,
            "safety_stops": r.safety_stops,
            "deadlock_recoveries": r.deadlock_recoveries,
        }
        for r in sim.robots
    ]


def summary(sim: Simulation) -> dict[str, Any]:
    delivery = _known([t.delivery_time for t in sim.tasks])
    urgent = _known([t.delivery_time for t in sim.tasks if t.priority == Priority.URGENT])
    normal = _known([t.delivery_time for t in sim.tasks if t.priority == Priority.NORMAL])
    robots = robot_rows(sim)
    return {
        "ticks": sim.tick,
        "robots": len(sim.robots),
        "tasks_total": len(sim.tasks),
        "tasks_delivered": len(delivery),
        "avg_delivery_time": _avg(delivery),
        "max_delivery_time": max(delivery, default=None),
        "avg_delivery_time_urgent": _avg(urgent),
        "avg_delivery_time_normal": _avg(normal),
        "avg_queue_time": _avg(_known([t.queue_time for t in sim.tasks])),
        "total_distance": sum(r["distance"] for r in robots),
        "collision_waits": sum(r["planned_waits"] + r["safety_stops"] for r in robots),
        "safety_stops": sum(r["safety_stops"] for r in robots),
        "deadlock_recoveries": sum(r["deadlock_recoveries"] for r in robots),
        "avg_utilization": _avg([r["utilization"] for r in robots]),
    }


def export(sim: Simulation, out_dir: Path, extra: dict[str, Any] | None = None) -> list[Path]:
    """Write tasks.csv, robots.csv and summary.json into out_dir. Returns the paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = [
        _write_csv(out_dir / "tasks.csv", task_rows(sim)),
        _write_csv(out_dir / "robots.csv", robot_rows(sim)),
    ]
    summary_path = out_dir / "summary.json"
    summary_path.write_text(json.dumps((extra or {}) | summary(sim), indent=2), encoding="utf-8")
    paths.append(summary_path)
    return paths


def format_summary(sim: Simulation) -> str:
    """Human-readable console report: fleet summary plus one line per robot."""
    s = summary(sim)
    lines = [
        f"Ticks: {s['ticks']}   Robots: {s['robots']}   "
        f"Delivered: {s['tasks_delivered']}/{s['tasks_total']}",
        f"Delivery time (ticks)  avg {_fmt(s['avg_delivery_time'])}   "
        f"urgent {_fmt(s['avg_delivery_time_urgent'])}   "
        f"normal {_fmt(s['avg_delivery_time_normal'])}   max {_fmt(s['max_delivery_time'])}",
        f"Avg queue time: {_fmt(s['avg_queue_time'])}   "
        f"Collision waits: {s['collision_waits']}   Safety stops: {s['safety_stops']}   "
        f"Deadlock recoveries: {s['deadlock_recoveries']}",
        "",
        f"{'robot':>5} {'distance':>9} {'busy':>6} {'util':>6} {'waits':>6} {'stops':>6}",
    ]
    for r in robot_rows(sim):
        lines.append(
            f"{r['id']:>5} {r['distance']:>9} {r['busy_ticks']:>6} "
            f"{r['utilization']:>6.0%} {r['planned_waits']:>6} {r['safety_stops']:>6}"
        )
    return "\n".join(lines)


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> Path:
    with path.open("w", newline="", encoding="utf-8") as f:
        if rows:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    return path


def _known(values: list[int | None]) -> list[int]:
    """Drop missing values (e.g. delivery time of a task that is not delivered yet)."""
    return [v for v in values if v is not None]


def _avg(values: list[int] | list[float]) -> float | None:
    return round(mean(values), 2) if values else None


def _fmt(value: float | None) -> str:
    return "-" if value is None else f"{value:g}"
