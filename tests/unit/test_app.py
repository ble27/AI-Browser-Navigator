"""Tests for the command-line entrypoint (:mod:`gesture_control.app`)."""

from gesture_control.app import build_arg_parser, main


def test_build_arg_parser_defaults_debug_to_false() -> None:
    """The ``--debug`` flag should default to off when not supplied."""
    parser = build_arg_parser()
    args = parser.parse_args([])
    assert args.debug is False


def test_build_arg_parser_accepts_debug_flag() -> None:
    """The ``--debug`` flag should be recognized when supplied."""
    parser = build_arg_parser()
    args = parser.parse_args(["--debug"])
    assert args.debug is True


def test_main_returns_zero_without_arguments() -> None:
    """Running with no arguments should succeed and print a startup message."""
    exit_code = main([])
    assert exit_code == 0


def test_main_returns_zero_in_debug_mode() -> None:
    """Debug mode should succeed even though M1's pipeline isn't wired up yet."""
    exit_code = main(["--debug"])
    assert exit_code == 0
