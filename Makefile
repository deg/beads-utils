#
# Makefile for beads-utils
#
# Everyday use:
#    make test      - run the test suite
#    make check     - static analysis (ruff) plus a --version smoke test
#    make ci        - everything CI runs, in CI's order
#    make help      - list every target
#
# Run one test file, one class, or one test:
#    make test PYTEST_ARGS=tests/test_bd_log.py
#    make test PYTEST_ARGS='tests/test_bd_log.py -k SelectSubtreesBranches'
#    make test PYTEST_ARGS='-k "warning and not children"'
#
# This repo has no package, no build step and no installer — the scripts run
# in place. Every Python entry point below goes through `uv run --no-project`,
# which resolves dependencies into a throwaway environment: nothing is
# installed globally and no pyproject.toml is needed.
#
# CI (.github/workflows/lint.yml) invokes these same targets, so a command
# lives in exactly one place. Change it here and CI follows.
#

# Use Bash for shell commands
SHELL := /bin/bash

# Project Name
PROJECT_NAME := beads-utils

.DEFAULT_GOAL := help

# Pinned tool versions. Pinning keeps CI reproducible; `make outdated` reports
# when a newer release exists.
RUFF_VERSION   ?= 0.15.14
PYTEST_VERSION ?= 9.1.1

# bd-view's own third-party deps (declared in its PEP 723 header). Named for
# the test run so its rich-rendering tests actually execute — without them
# those tests skip, which is honest but covers less.
RICH_DEPS := --with rich --with markdown-it-py

# --no-project: there is deliberately no pyproject.toml to discover.
UV_RUN := uv run --no-project

# Test selection override — see the header for examples. Empty by default:
# pytest.ini's `testpaths` already points at tests/.
PYTEST_ARGS ?=

# Every executable script, found by shebang, so a new script is picked up with
# no edit here. `-d skip` makes grep ignore subdirectories rather than exiting
# 2 on them (which would silently abort the recipe); see the note in CLAUDE.md.
#
# HASH exists because make strips `#` and everything after it *before* parsing
# a function call — an inline '^#!' would truncate the $(shell ...) mid-call.
HASH := \#
SCRIPTS := $(shell grep -lE -d skip '^$(HASH)!' * 2>/dev/null)

# Everything ruff should see: the extension-less scripts, the shared helper
# modules, and the test suite. Named explicitly because shebang discovery
# finds neither the helpers (no shebang) nor tests/ (a subdirectory).
LINT_TARGETS := $(SCRIPTS) *.py tests/


# Show this help message
.PHONY: help
help: ## Show this help message
	@printf "\033[1;34mUsage:\033[0m make [target]\n\n"
	@printf "\033[1;36mTargets:\033[0m\n"
	@# List every command target. A target missing its '## ' doc prints
	@# "(no description)", which makes the omission obvious in this output.
	@awk -F: '/^[a-zA-Z0-9_-]+:/ { \
	    desc = "(no description)"; \
	    if (match($$0, /## /)) { desc = substr($$0, RSTART + 3); } \
	    printf "  \033[1;32m%-20s\033[0m \033[0;37m%s\033[0m\n", $$1, desc; \
	}' $(MAKEFILE_LIST) | sort
	@printf "\n"


################################################################
## Testing

test: ## Run the test suite (with bd-view's rich deps, so nothing skips)
	@echo "🔍 Running tests..."
	@$(UV_RUN) --with pytest==$(PYTEST_VERSION) $(RICH_DEPS) pytest $(PYTEST_ARGS)

# The suite is designed to degrade honestly when bd-view's optional deps are
# absent: its rich-rendering tests skip loudly instead of silently exercising
# only the plain-text fallback. This target is how you confirm that still
# holds — expect 3 skips and no failures.
test-minimal: ## Run the suite WITHOUT rich, confirming the skips are honest
	@echo "🔍 Running tests without rich (expect 3 skips)..."
	@$(UV_RUN) --with pytest==$(PYTEST_VERSION) pytest $(PYTEST_ARGS)

coverage: ## Run the suite and write a coverage report to htmlcov/
	@$(UV_RUN) --with pytest==$(PYTEST_VERSION) $(RICH_DEPS) --with pytest-cov \
		pytest --cov=. --cov-report=term-missing --cov-report=html $(PYTEST_ARGS)
	@echo "✅ Coverage report in htmlcov/index.html"

.PHONY: test test-minimal coverage


################################################################
## Static analysis

lint: check ## Run all static analysis (alias for check)

check: ruff-check smoke ## Run all static analysis: ruff plus a --version smoke test
	@echo "✅ All checks passed."

ruff-check: ## Run ruff over every script, the shared modules, and the tests
	@[ -n "$(SCRIPTS)" ] || { echo "❌ shebang discovery found no scripts"; exit 1; }
	@echo "🔍 ruff $(RUFF_VERSION)..."
	@uvx ruff@$(RUFF_VERSION) check $(LINT_TARGETS)

format: ## Apply ruff's automatic fixes in place
	@echo "🎨 Formatting..."
	@uvx ruff@$(RUFF_VERSION) check --fix $(LINT_TARGETS)

# ruff is static-only, so actually invoke each script. This is the cheapest
# check that catches an argparse or import break — and for bd-view it also
# exercises the `uv run --script` shebang, which nothing else does.
smoke: ## Invoke every script's --version (catches import/argparse breakage)
	@for s in $(SCRIPTS); do \
		echo "== $$s --version =="; \
		"./$$s" --version || exit 1; \
	done

ci: check test ## Run everything CI runs, in CI's order

.PHONY: lint check ruff-check format smoke ci


################################################################
## This project's own beads data
##
## beads-utils tracks its own work in bd, whose Dolt data lives under
## refs/dolt/data on the git remote — invisible in GitHub's UI, which is
## exactly why these checks exist.

dolt-check: ## Verify this repo's Dolt data has been pushed (exits 1 if not)
	@./bd-dolt-check .

dolt-diff: ## Preview the issue-level changes a 'bd dolt push' would send
	@./bd-dolt-diff .

export-csv: ## Export this repo's beads to a CSV in the current directory
	@./bd-export-csv .

.PHONY: dolt-check dolt-diff export-csv


################################################################
## Housekeeping

version: ## Print the version string shared by every script
	@python3 -c "import bdutils; print(bdutils.__version__)"

# The scripts must be on $PATH for completion to work, since the completion
# functions shell out to bd-complete by name.
completions: ## Print the line to add to your shell rc file for tab completion
	@echo "Add to ~/.zshrc (oh-my-zsh users: after 'source \$$ZSH/oh-my-zsh.sh'):"
	@echo "    source $(CURDIR)/completions/beads-utils.zsh"
	@echo ""
	@echo "Add to ~/.bashrc:"
	@echo "    source $(CURDIR)/completions/beads-utils.bash"
	@echo ""
	@echo "Also put $(CURDIR) on your \$$PATH — the completions call bd-complete by name."

outdated: ## Report newer releases of the pinned tools
	@echo "❗ ruff:   pinned $(RUFF_VERSION), latest $$(uvx ruff@latest --version | awk '{print $$2}')"
	@echo "❗ pytest: pinned $(PYTEST_VERSION), latest $$($(UV_RUN) --with pytest \
		python -c 'import pytest; print(pytest.__version__)' 2>/dev/null)"

tags: ## Build an etags TAGS file over the scripts and modules
	@command -v etags >/dev/null || { echo "❌ etags not found"; exit 1; }
	@etags $(SCRIPTS) *.py tests/*.py
	@echo "✅ Wrote TAGS"

clean: ## Remove caches and generated reports
	@echo "🧹 Cleaning..."
	@rm -rf .pytest_cache .ruff_cache htmlcov .coverage coverage.xml TAGS
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@find . -name '*.pyc' -delete 2>/dev/null || true
	@echo "🧹 Clean complete."

.PHONY: version completions outdated tags clean
