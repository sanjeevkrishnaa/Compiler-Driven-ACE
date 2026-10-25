#!/bin/sh
# Run ACE with its pinned SeQUeNCe 0.8.1 simulator checkout.
# Usage: tools/run_ace.sh -B run_trace_comparison.py [arguments...]
set -eu

repo=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
python_bin=${ACE_PYTHON:-"$repo/.venv/bin/python"}
sequence_root=${SEQUENCE_ROOT:-"$repo/../SeQUeNCe-0.8.1"}

if [ ! -x "$python_bin" ]; then
    echo "ACE Python not found: $python_bin" >&2
    echo "Set ACE_PYTHON=/absolute/path/to/the/ACE/.venv/bin/python" >&2
    exit 2
fi
if [ ! -f "$sequence_root/sequence/__init__.py" ]; then
    echo "SeQUeNCe 0.8.1 checkout not found: $sequence_root" >&2
    echo "Set SEQUENCE_ROOT=/absolute/path/to/SeQUeNCe-0.8.1" >&2
    exit 2
fi

export PYTHONPATH="$sequence_root${PYTHONPATH:+:$PYTHONPATH}"
imported=$(
    "$python_bin" -c 'import os, sequence; print(os.path.realpath(sequence.__file__))'
)
version=$("$python_bin" -c 'import sequence; print(sequence.__version__)')
case "$imported" in
    "$sequence_root"/sequence/*) ;;
    *)
        echo "Refusing to run ACE with a different SeQUeNCe: $imported" >&2
        exit 2
        ;;
esac
if [ "$version" != "0.8.1" ]; then
    echo "Refusing to run ACE with SeQUeNCe $version; ACE is pinned to 0.8.1" >&2
    exit 2
fi

exec "$python_bin" "$@"
