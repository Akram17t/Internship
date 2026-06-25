#!/usr/bin/env python
import argparse
import json
import sys
import warnings

from football_transfer_crew.crew import FootballTransferCrew
from football_transfer_crew.tools.playersearch import PlayerSearchTool

warnings.filterwarnings("ignore", category=SyntaxWarning, module="pysbd")


DEFAULT_CLUB = "Arsenal"
DEFAULT_POSITION = "CM"
DEFAULT_BUDGET = 75.0
POSITION_TOOL = PlayerSearchTool()


def _configure_console() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def _prompt_text(label: str) -> str:
    while True:
        value = input(f"{label}: ").strip()
        if value:
            return value

        print(f"{label} cannot be empty. Please try again.")


def _available_positions_text() -> str:
    return ", ".join(POSITION_TOOL.get_available_positions())


def _build_inputs(club: str, position: str, budget: float) -> dict[str, str | float]:
    return {
        "club": club,
        "position": _normalize_position_or_raise(position),
        "budget": budget,
    }


def _normalize_position_or_raise(position: str) -> str:
    normalized_position = position.strip().upper()
    if POSITION_TOOL.is_valid_position(normalized_position):
        return normalized_position

    raise ValueError(
        f"Position '{position}' is not available in players.csv. "
        f"Available positions: {_available_positions_text()}"
    )


def _prompt_position() -> str:
    print(f"Available positions: {_available_positions_text()}")
    while True:
        value = input("Needed position: ").strip()
        if not value:
            print("Needed position cannot be empty. Please choose one of the available positions above.")
            continue

        candidate = value.upper()
        if POSITION_TOOL.is_valid_position(candidate):
            return candidate

        print("Position not found in players.csv. Please choose one of the available positions above.")


def _prompt_budget() -> float:
    while True:
        value = input("Budget in million euros: ").strip()
        if not value:
            print("Budget cannot be empty. Try again.")
            continue

        try:
            parsed_value = float(value)
        except ValueError:
            print("Budget must be a number. Try again.")
            continue

        if parsed_value <= 0:
            print("Budget must be greater than zero. Try again.")
            continue

        return parsed_value


def _add_shared_input_arguments(parser: argparse.ArgumentParser, *, with_defaults: bool) -> None:
    parser.add_argument(
        "--club",
        type=str,
        default=DEFAULT_CLUB if with_defaults else None,
        help="Club requesting the transfer recommendation.",
    )
    parser.add_argument(
        "--position",
        type=str,
        default=DEFAULT_POSITION if with_defaults else None,
        help="Target position, for example ST, CM, or CB.",
    )
    parser.add_argument(
        "--budget",
        type=float,
        default=DEFAULT_BUDGET if with_defaults else None,
        help="Maximum transfer budget in million euros.",
    )


def _build_run_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the football transfer scouting crew.")
    _add_shared_input_arguments(parser, with_defaults=False)
    parser.add_argument(
        "--no-prompt",
        action="store_true",
        help="Use defaults for any missing inputs instead of asking interactively.",
    )
    return parser


def _build_train_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train the football transfer crew.")
    parser.add_argument("n_iterations", type=int)
    parser.add_argument("filename", type=str)
    _add_shared_input_arguments(parser, with_defaults=True)
    return parser


def _build_test_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Test the football transfer crew.")
    parser.add_argument("n_iterations", type=int)
    parser.add_argument("eval_llm", type=str)
    _add_shared_input_arguments(parser, with_defaults=True)
    return parser


def _collect_run_inputs() -> dict[str, str | float]:
    parser = _build_run_parser()
    args, _ = parser.parse_known_args(sys.argv[1:])

    if args.no_prompt:
        club = args.club or DEFAULT_CLUB
        position = _normalize_position_or_raise(args.position or DEFAULT_POSITION)
        budget = args.budget or DEFAULT_BUDGET
    else:
        club = args.club or _prompt_text("Club")
        position = _normalize_position_or_raise(args.position) if args.position else _prompt_position()
        budget = args.budget if args.budget is not None else _prompt_budget()

    return _build_inputs(club, position, budget)


def run():
    """Run the crew."""
    _configure_console()
    inputs = _collect_run_inputs()

    try:
        FootballTransferCrew().crew().kickoff(inputs=inputs)
        return None
    except Exception as e:
        raise Exception(f"An error occurred while running the crew: {e}")


def train():
    """Train the crew for a given number of iterations."""
    _configure_console()
    parser = _build_train_parser()
    args, _ = parser.parse_known_args(sys.argv[1:])
    inputs = _build_inputs(args.club, args.position, args.budget)

    try:
        FootballTransferCrew().crew().train(
            n_iterations=args.n_iterations,
            filename=args.filename,
            inputs=inputs,
        )
    except Exception as e:
        raise Exception(f"An error occurred while training the crew: {e}")


def replay():
    """Replay the crew execution from a specific task."""
    _configure_console()
    if len(sys.argv) < 2:
        raise Exception("No task ID provided. Please provide the task ID as an argument.")

    try:
        FootballTransferCrew().crew().replay(task_id=sys.argv[1])
    except Exception as e:
        raise Exception(f"An error occurred while replaying the crew: {e}")


def test():
    """Test the crew execution and return the results."""
    _configure_console()
    parser = _build_test_parser()
    args, _ = parser.parse_known_args(sys.argv[1:])
    inputs = _build_inputs(args.club, args.position, args.budget)

    try:
        FootballTransferCrew().crew().test(
            n_iterations=args.n_iterations,
            eval_llm=args.eval_llm,
            inputs=inputs,
        )
    except Exception as e:
        raise Exception(f"An error occurred while testing the crew: {e}")


def run_with_trigger():
    """Run the crew with trigger payload."""
    _configure_console()
    if len(sys.argv) < 2:
        raise Exception("No trigger payload provided. Please provide JSON payload as argument.")

    try:
        trigger_payload = json.loads(sys.argv[1])
    except json.JSONDecodeError:
        raise Exception("Invalid JSON payload provided as argument")

    inputs = {
        "crewai_trigger_payload": trigger_payload,
        **_build_inputs(
            trigger_payload.get("club", DEFAULT_CLUB),
            trigger_payload.get("position", DEFAULT_POSITION),
            float(trigger_payload.get("budget", DEFAULT_BUDGET)),
        ),
    }

    try:
        FootballTransferCrew().crew().kickoff(inputs=inputs)
        return None
    except Exception as e:
        raise Exception(f"An error occurred while running the crew with trigger: {e}")
