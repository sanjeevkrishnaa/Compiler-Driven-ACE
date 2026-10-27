# Tests and historical fixtures

`test_*.py` contains the active regression tests. The JSON and text request
fixtures in this directory retain their existing paths because historical
experiment runners still reference them.

With the compatible pinned SeQUeNCe dependency on `PYTHONPATH`, run:

```text
python -B -m unittest discover -s test -v
```

For the compiler subsystem only:

```text
python -B -m unittest discover -s test -p "test_compiler*.py" -v
```

The full-trace evidence archive contains additional physical ownership and
ordering audits; see `results/compiler_memory_handoff_2026-10-28/README.md`.
