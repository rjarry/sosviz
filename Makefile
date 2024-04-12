# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2024 Robin Jarry

PYTHON = python3
PIP = $(PYTHON) -m pip
VIRTUALENV = $(PYTHON) -m venv
VENV = .venv
in_venv = . $(VENV)/bin/activate &&

.PHONY: all
all: lint

$(VENV)/bin/activate:
	$(VIRTUALENV) $(VENV)

$(VENV)/.stamp: $(VENV)/bin/activate requirements-dev.txt pyproject.toml
	$(in_venv) $(PIP) install -U -r requirements-dev.txt -e .
	@touch $@

PY_FILES = $(shell find * -name '*.py')
J ?= $(shell nproc)

.PHONY: lint
lint: $(VENV)/.stamp
	@echo "[black]"
	@$(in_venv) $(PYTHON) -m black -q --diff --check $(PY_FILES) || \
		{ echo "Use 'make format' to fix the problems."; exit 1; }
	@echo "[isort]"
	@$(in_venv) $(PYTHON) -m isort -j$(J) --diff --check-only $(PY_FILES) || \
		{ echo "Use 'make format' to fix the problems."; exit 1; }
	@echo "[pylint]"
	@$(in_venv) $(PYTHON) -m pylint $(PY_FILES)

.PHONY: format
format: $(VENV)/.stamp
	@echo "[isort]"
	@$(in_venv) $(PYTHON) -m isort -j$(J) $(PY_FILES)
	@echo "[black]"
	@$(in_venv) $(PYTHON) -m black -q $(PY_FILES)
