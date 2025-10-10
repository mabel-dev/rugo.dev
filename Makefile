SHELL := /bin/bash

# Variables
PYTHON := python
UV := $(PYTHON) -m uv
PIP := $(UV) pip
PYTEST := $(PYTHON) -m pytest

# Parallel job count for compilation
JOBS := $(shell nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 4)

# Directories
SRC_DIR := rugo
TEST_DIR := tests

define print_green
	@echo -e "\033[0;32m$(1)\033[0m"
endef

define print_blue
	@echo -e "\033[0;34m$(1)\033[0m"
endef

lint: ## Run all linting tools
	$(call print_blue,"Installing linting tools...")
	@$(PIP) install --quiet --upgrade pycln isort ruff yamllint cython-lint
	$(call print_blue,"Running Cython lint...")
	@cython-lint $(SRC_DIR)/compiled/**/*.pyx || true
	$(call print_blue,"Running Ruff checks...")
	@$(PYTHON) -m ruff check --fix --exit-zero
	$(call print_blue,"Cleaning unused imports...")
	@$(PYTHON) -m pycln .
	$(call print_blue,"Sorting imports...")
	@$(PYTHON) -m isort .
	$(call print_blue,"Formatting code...")
	@$(PYTHON) -m ruff format $(SRC_DIR)
	$(call print_green,"Linting complete!")

test: dev-install ## Run full test suite
	$(call print_blue,"Running full test suite...")
	@$(PIP) install --upgrade pytest pytest-xdist
	@clear
	@$(PYTEST) -n auto --color=yes

compile: ## Compile Cython extensions
	$(call print_blue,"Compiling Cython extensions...")
	@$(PIP) install --upgrade pip uv numpy cython setuptools
	@find . -name '*.so' -delete
	@rm -rf build dist *.egg-info
	@$(PYTHON) setup.py clean
	@$(PYTHON) setup.py build_ext --inplace -j $(JOBS)
	$(call print_green,"Compilation complete!")

dev-install: ## Install development dependencies
	$(call print_blue,"Installing development dependencies...")
	@$(PIP) install --upgrade pip uv
	@$(PIP) install --upgrade -r tests/requirements.txt
