"""Compatibility launcher for run_pir_experiments; see ace/cli/."""
import runpy

if __name__ == "__main__":
    runpy.run_module("ace.cli.run_pir_experiments", run_name="__main__")
