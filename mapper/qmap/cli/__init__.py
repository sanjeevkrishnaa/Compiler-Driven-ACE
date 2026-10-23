
from __future__ import annotations

import logging
import sys

from qmap.cli.commands import dispatch
from qmap.cli.parser import build_parser
from qmap.exceptions import QMapError

__all__ = ["build_parser", "dispatch", "main"]

def _configure_logging(verbose: int, quiet: bool) -> None:
    if quiet:
        level = logging.ERROR
    elif verbose >= 2:
        level = logging.DEBUG
    elif verbose == 1:
        level = logging.INFO
    else:
        level = logging.WARNING
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")

def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _configure_logging(getattr(args, 'verbose', 0), getattr(args, 'quiet', False))

    try:
        return dispatch(args)
    except QMapError as exc:

        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130
