"""Command line entry point: `python -m hospital_sim run scenarios/demo.yaml --headless`."""

import argparse
import logging
import sys

from hospital_sim.scenario import build_simulation, load_scenario


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hospital_sim", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run a scenario")
    run.add_argument("scenario", help="path to a scenario YAML file")
    run.add_argument("--headless", action="store_true", help="no window, console output only")
    run.add_argument("--ticks", type=int, help="override max_ticks from the scenario")
    run.add_argument("-q", "--quiet", action="store_true", help="only print the summary")

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(message)s",
        stream=sys.stdout,
    )
    return _run(args)


def _run(args: argparse.Namespace) -> int:
    scenario, grid = load_scenario(args.scenario)
    sim = build_simulation(scenario, grid)
    max_ticks = args.ticks or scenario.max_ticks
    if args.headless:
        sim.run(max_ticks)
    else:
        from hospital_sim.viz import Viewer  # imported lazily: headless runs never need pygame

        Viewer(sim, max_ticks, title=f"Hospital delivery robots - {scenario.name}").run()
    delivered = sum(t.delivered_tick is not None for t in sim.tasks)
    print(f"\nScenario '{scenario.name}': {sim.tick} ticks, {delivered}/{len(sim.tasks)} delivered")
    return 0


if __name__ == "__main__":
    sys.exit(main())
