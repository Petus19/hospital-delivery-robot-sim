"""Command line entry point.

    python -m hospital_sim run scenarios/demo.yaml              # pygame window
    python -m hospital_sim run scenarios/demo.yaml --headless   # console only
    python -m hospital_sim run scenarios/random_day.yaml --headless --seed 7

Every run prints a summary table and writes tasks.csv, robots.csv,
summary.json and sim.log into output/<scenario>_seed<seed>/.
"""

import argparse
import logging
import sys
from pathlib import Path

from hospital_sim.metrics import export, format_summary
from hospital_sim.scenario import build_simulation, load_scenario


def main(argv: list[str] | None = None) -> int:
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

    args = parser.parse_args(argv)
    return _run(args)


def _run(args: argparse.Namespace) -> int:
    scenario, grid = load_scenario(args.scenario)
    seed = scenario.seed if args.seed is None else args.seed
    out_dir = Path(args.out) / f"{scenario.name}_seed{seed}"
    _setup_logging(out_dir / "sim.log", quiet=args.quiet)

    sim = build_simulation(scenario, grid, seed=seed)
    max_ticks = args.ticks or scenario.max_ticks
    if args.headless:
        sim.run(max_ticks)
    else:
        from hospital_sim.viz import Viewer  # imported lazily: headless runs never need pygame

        Viewer(sim, max_ticks, title=f"Hospital delivery robots - {scenario.name}").run()

    print(f"\n=== {scenario.name} (seed {seed}) ===")
    print(format_summary(sim))
    paths = export(sim, out_dir, extra={"scenario": scenario.name, "seed": seed})
    print(f"\nResults written to {out_dir}: {', '.join(p.name for p in paths)}, sim.log")
    return 0


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
