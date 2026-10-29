"""Compatibility launcher for run_pir_experiments_event; see ace/cli/."""
import runpy

if __name__ == "__main__":
    runpy.run_module("ace.cli.run_pir_experiments_event", run_name="__main__")
