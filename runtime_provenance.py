"""Record the exact ACE and SeQUeNCe implementation used by an experiment."""

from __future__ import annotations

from pathlib import Path
import platform
import subprocess
import sys

import sequence


def _git(path: Path, *arguments: str) -> str | None:
    """Return a Git value for ``path`` without making Git a runtime requirement."""
    try:
        result = subprocess.run(
            ["git", *arguments], cwd=path, capture_output=True, text=True, check=True
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip()


def runtime_provenance(ace_root: str | Path) -> dict:
    """Describe the interpreter, ACE checkout and imported SeQUeNCe checkout.

    ``sequence.__file__`` is authoritative: it records what Python actually
    imported, rather than what a shell variable was intended to select.
    """
    ace_root = Path(ace_root).resolve()
    sequence_init = Path(sequence.__file__).resolve()
    sequence_root = sequence_init.parent.parent
    return {
        "python": {
            "executable": sys.executable,
            "version": sys.version,
            "implementation": platform.python_implementation(),
        },
        "sequence": {
            "module_file": str(sequence_init),
            "root": str(sequence_root),
            "version": getattr(sequence, "__version__", None),
            "git_commit": _git(sequence_root, "rev-parse", "HEAD"),
            "git_dirty": bool(_git(sequence_root, "status", "--porcelain")),
        },
        "ace": {
            "root": str(ace_root),
            "git_commit": _git(ace_root, "rev-parse", "HEAD"),
            "git_dirty": bool(_git(ace_root, "status", "--porcelain")),
        },
    }
