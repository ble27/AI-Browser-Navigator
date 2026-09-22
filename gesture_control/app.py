"""Command-line entrypoint for the gesture control application.

At this stage (M0 -- repo scaffold) this module only wires up argument
parsing and prints diagnostic information. The camera-capture and
hand-landmark pipeline is added in M1 (see ``docs/PRD.md`` milestones); this
entrypoint is where that pipeline will be started.
"""

from __future__ import annotations

import argparse
import sys

from gesture_control import __version__


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the top-level command-line argument parser.

    Returns:
        A configured :class:`argparse.ArgumentParser` for the application.
    """
    parser = argparse.ArgumentParser(
        prog="gesture-control",
        description="Control your computer with hand gestures and voice.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Show a debug window with the camera feed and hand landmark overlay.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the gesture control application.

    Args:
        argv: Command-line arguments, excluding the program name. Defaults to
            ``sys.argv[1:]`` when ``None``.

    Returns:
        A process exit code (``0`` on success).
    """
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.debug:
        print(
            "Debug mode requested, but the camera/landmark pipeline is not "
            "implemented yet (lands in milestone M1). See docs/PRD.md.",
            file=sys.stderr,
        )
        return 0

    print(f"gesture-control {__version__} -- see README.md to get started.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
