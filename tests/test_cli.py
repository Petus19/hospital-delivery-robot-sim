import json
import logging
import os
import subprocess
import sys
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


def test_parse_task_command_without_llm(capsys):
    code = main(["parse-task", "doruč inzulín z lekárne na oddelenie 3, súrne", "--no-llm"])
    out = capsys.readouterr().out
    assert code == 0
    assert '"dropoff": "ward_3"' in out
    assert '"priority": "urgent"' in out
    assert "understood by rules" in out


def test_parse_task_command_reports_failure(capsys):
    assert main(["parse-task", "make me a coffee", "--no-llm"]) == 1
    assert "Could not understand" in capsys.readouterr().out


def test_run_with_extra_task_sentence(tmp_path, capsys):
    args = ["run", str(SCENARIOS / "single_robot.yaml"), "--headless", "-q", "--no-llm"]
    args += ["--out", str(tmp_path), "--task", "bring test kits from the lab to ward 9, urgent"]
    assert main(args) == 0
    logging.shutdown()
    out = capsys.readouterr().out
    assert "Added task #4: test kits, lab -> ward_9 (urgent) [understood by rules]" in out
    assert "Delivered: 4/4" in out


def test_slovak_output_on_a_legacy_windows_console():
    # cp1252 cannot encode "č"; the CLI must switch its output to UTF-8 itself.
    env = os.environ | {"PYTHONIOENCODING": "cp1252"}
    result = subprocess.run(
        [sys.executable, "-m", "hospital_sim", "parse-task", "doruč čaj z kuchyne na oddelenie 2",
         "--no-llm"],
        capture_output=True, env=env, check=False,
    )  # fmt: skip
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    assert '"item": "čaj"' in result.stdout.decode("utf-8")
