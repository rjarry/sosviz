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
	$(in_venv) $(PIP) install -U -r requirements-dev.txt
	@touch $@

PY_FILES = $(shell find * -name '*.py')
J ?= $(shell nproc)

.PHONY: lint
lint: $(VENV)/.stamp
	@echo "[black]"
	@$(in_venv) $(PYTHON) -m black -q -t py36 --diff --check $(PY_FILES) || \
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
	@$(in_venv) $(PYTHON) -m black -q -t py36 $(PY_FILES)

.PHONY: tests
tests: $(VENV)/.stamp
	@$(in_venv) $(PYTHON) -m pytest -v

prefix = /usr/local

.PHONY: install_python
install_python:
	$(PYTHON) -m pip install --prefix=$(prefix) $(addprefix --root=,$(destdir))

docs/%: docs/%.scdoc
	scdoc < $< > $@

man_src = $(wildcard docs/*.scdoc)

.PHONY: man
man: $(man_src:.scdoc=)
	@:

.PHONY: install_man
install_man:
	@:

define install_man_rule
$(destdir)$(prefix)/share/man/man$2/$1.$2: docs/$1.$2
	install -m 644 -DTC $$< $$@

install_man: $(destdir)$(prefix)/share/man/man$2/$1.$2
endef

man_names = $(notdir $(man_src:.scdoc=))
$(foreach m,$(man_names),\
	$(eval $(call install_man_rule,$(basename $(m)),$(subst .,,$(suffix $(m))))))

.PHONY: install
install: install_python install_man
