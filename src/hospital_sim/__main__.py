"""Command line entry point.

    python -m hospital_sim run scenarios/demo.yaml              # pygame window
    python -m hospital_sim run scenarios/demo.yaml --headless   # console only
    python -m hospital_sim run scenarios/random_day.yaml --headless --seed 7
    python -m hospital_sim run scenarios/demo.yaml --task "deliver insulin from pharmacy to ward 3"
    python -m hospital_sim parse-task "doruč inzulín z lekárne na oddelenie 3, súrne"

Every run prints a summary table and writes tasks.csv, robots.csv,
summary.json and sim.log into output/<scenario>_seed<seed>/.
Task sentences go to a local LLM (Ollama) first and to a rule-based parser if
Ollama is not running; --no-llm skips the LLM.
"""

import argparse
import io
import logging
import sys
from collections.abc import Callable
from pathlib import Path

from hospital_sim.grid import Grid, load_grid
from hospital_sim.llm import DEFAULT_MODEL, OllamaExtractor, TaskExtractor
from hospital_sim.metrics import export, format_summary
from hospital_sim.scenario import build_simulation, load_scenario
from hospital_sim.simulation import Simulation
from hospital_sim.task_parser import parse_task

DEFAULT_MAP = "maps/hospital.txt"  # relative to the project folder


def main(argv: list[str] | None = None) -> int:
    _use_utf8_output()
    parser = argparse.ArgumentParser(
        prog="hospital_sim", description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run a scenario")
    run.add_argument("scenario", help="path to a scenario YAML file")
    run.add_argument("--headless", action="store_true", help="no window, console output only")
    run.add_argument("--ticks", type=int, help="override max_ticks from the scenario")
    run.add_argument("--seed", type=int, help="override the scenario seed")
    run.add_argument("--out", default="output", help="folder for results (default: output)")
    run.add_argument("-q", "--quiet", action="store_true", help="only print the summary")
    run.add_argument(
        "--task", action="append", default=[], help="extra task as a sentence (repeatable)"
    )
    _add_llm_options(run)

    parse = sub.add_parser("parse-task", help="turn a sentence into a task and print it")
    parse.add_argument("text", help='e.g. "deliver insulin from the pharmacy to ward 3, urgent"')
    parse.add_argument("--map", default=DEFAULT_MAP, help="map with the allowed locations")
    _add_llm_options(parse)

    args = parser.parse_args(argv)
    if args.command == "parse-task":
        return _parse_task(args)
    return _run(args)


def _add_llm_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--no-llm", action="store_true", help="use only the rule-based parser")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Ollama model ({DEFAULT_MODEL})")


def _make_llm(args: argparse.Namespace) -> TaskExtractor | None:
    return None if args.no_llm else OllamaExtractor(model=args.model)


def _run(args: argparse.Namespace) -> int:
    scenario, grid = load_scenario(args.scenario)
    seed = scenario.seed if args.seed is None else args.seed
    out_dir = Path(args.out) / f"{scenario.name}_seed{seed}"
    _setup_logging(out_dir / "sim.log", quiet=args.quiet)

    sim = build_simulation(scenario, grid, seed=seed)
    add_task = _task_adder(sim, _make_llm(args))
    for text in args.task:
        print(add_task(text))

    max_ticks = args.ticks or scenario.max_ticks
    if args.headless:
        sim.run(max_ticks)
    else:
        from hospital_sim.viz import Viewer  # imported lazily: headless runs never need pygame

        title = f"Hospital delivery robots - {scenario.name}"
        Viewer(sim, max_ticks, title=title, on_text=add_task).run()

    print(f"\n=== {scenario.name} (seed {seed}) ===")
    print(format_summary(sim))
    paths = export(sim, out_dir, extra={"scenario": scenario.name, "seed": seed})
    print(f"\nResults written to {out_dir}: {', '.join(p.name for p in paths)}, sim.log")
    return 0


def _task_adder(sim: Simulation, llm: TaskExtractor | None) -> Callable[[str], str]:
    """Return a function that parses a sentence, adds the task and describes the result."""

    def add_task(text: str) -> str:
        try:
            result = parse_task(text, task_locations(sim.grid), llm)
        except ValueError as error:
            return str(error)
        r = result.request
        task = sim.add_task(r.pickup, r.dropoff, r.item, r.priority)
        return (
            f"Added task #{task.id}: {r.item}, {r.pickup} -> {r.dropoff} ({r.priority}) "
            f"[understood by {result.source}]"
        )

    return add_task


def _parse_task(args: argparse.Namespace) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(message)s")

    try:
        result = parse_task(args.text, task_locations(load_grid(args.map)), _make_llm(args))
    except ValueError as error:
        print(error)
        return 1
    print(result.request.model_dump_json(indent=2))
    print(f"(understood by {result.source})")
    return 0


def task_locations(grid: Grid) -> list[str]:
    """Places a task may start or end at: every location except the chargers."""
    return sorted(name for name in grid.locations if name != "charging")


def _use_utf8_output() -> None:
    """Older Windows consoles use cp1252, which cannot print Slovak letters like 'č'."""
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8")


def _setup_logging(log_file: Path, quiet: bool) -> None:
    """Events go to the console (unless --quiet) and always to a log file."""
    log_file.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_file, mode="w", encoding="utf-8")
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.WARNING if quiet else logging.INFO)
    logging.basicConfig(
        level=logging.INFO, format="%(message)s", handlers=[console, file_handler], force=True
    )


if __name__ == "__main__":
    sys.exit(main())
