import json
import logging
from pathlib import Path

from hospital_sim.__main__ import main

SCENARIOS = Path(__file__).resolve().parent.parent / "scenarios"


def test_headless_run_writes_results(tmp_path, capsys):
    code = main(["run", str(SCENARIOS / "demo.yaml"), "--headless", "-q", "--out", str(tmp_path)])
    logging.shutdown()  # release the log file handle (needed on Windows)
    assert code == 0
    out_dir = tmp_path / "demo_seed0"
    assert {p.name for p in out_dir.iterdir()} == {
        "tasks.csv",
        "robots.csv",
        "summary.json",
        "sim.log",
    }
    summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["tasks_delivered"] == summary["tasks_total"] == 10
    assert "delivered by robot" in (out_dir / "sim.log").read_text(encoding="utf-8")
    assert "Delivered: 10/10" in capsys.readouterr().out
