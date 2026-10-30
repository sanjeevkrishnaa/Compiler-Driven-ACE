# Run from the ACE repository root. Python must have the study dependencies.
.DEFAULT_GOAL := help
PYTHON ?= python
WORKLOAD ?= qaoa
ROUTING ?= greedy
QUBITS ?= 96
SEEDS ?= 60,61,62,63
RESERVATION_MS ?= 50
OUTPUT ?= output/$(WORKLOAD)-$(ROUTING)
ARGS = --workload "$(WORKLOAD)" --routing "$(ROUTING)" --qubits "$(QUBITS)" --seeds "$(SEEDS)" --reservation-ms "$(RESERVATION_MS)" --output "$(OUTPUT)"

.PHONY: help init run trace route simulate dry-run
help:
	@echo make run WORKLOAD=qaoa ROUTING=greedy
	@echo Targets: init, run, trace, route, simulate, dry-run
	@echo Options: PYTHON, WORKLOAD, ROUTING, QUBITS, SEEDS, RESERVATION_MS, OUTPUT
init:
	git submodule update --init --recursive
run trace route simulate:
	"$(PYTHON)" -B tools/run_workload.py $@ $(ARGS)
dry-run:
	"$(PYTHON)" -B tools/run_workload.py run $(ARGS) --dry-run
