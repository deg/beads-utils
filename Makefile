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
# This repo has no package and no build step — the scripts run in place. Every
# Python entry point below goes through `uv run --no-project`, which resolves
# dependencies into a throwaway environment: nothing is installed globally and
# no pyproject.toml is needed.
#
# `make install` does not change that. It symlinks the scripts into a bin
# directory; each one still runs from this tree, because Python resolves a
# symlink before setting sys.path[0], which is what lets the sibling `bdutils`
# import keep working through the link.
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

# Where `make install` puts its symlinks. Override per invocation:
#     make install PREFIX=~/bin
PREFIX ?= $(HOME)/.local/bin

# Expand a leading `~` ourselves. zsh does not tilde-expand an argument that
# merely looks like an assignment, so `make install PREFIX=~/bin` hands make
# a literal `~`, and make substitutes it into the recipe inside double quotes
# where the shell will never expand it either — `mkdir -p "~/bin"` then
# silently creates a directory *named* `~` in the current directory. (Which
# .gitignore's `*~` backup pattern also hides, so it goes unnoticed.)
#
# `override` is required: a variable set on the command line cannot be
# reassigned from the makefile without it.
override PREFIX := $(patsubst ~,$(HOME),$(patsubst ~/%,$(HOME)/%,$(PREFIX)))

# A trailing slash would otherwise make the PATH check below compare
# "/Users/deg/bin/" against a PATH entry of "/Users/deg/bin" and never match,
# reporting a directory as absent from a PATH it is on. (`PREFIX=/` collapses
# to empty here and is caught by check-prefix, which is the right answer for
# an input that was never meaningful.)
override PREFIX := $(patsubst %/,%,$(PREFIX))

# Every executable script in bin/, found by shebang, so a new script is picked
# up with no edit here. The names are bare (`bd-log`, not `bin/bd-log`): they are
# what `install` links into PREFIX. `-d skip` makes grep ignore subdirectories
# rather than exiting 2 on them (which would silently abort the recipe); see
# .claude/rules/makefile.md.
#
# HASH exists because make strips `#` and everything after it *before* parsing
# a function call — an inline '^#!' would truncate the $(shell ...) mid-call.
HASH := \#
BIN := bin
SCRIPTS := $(shell cd $(BIN) && grep -lE -d skip '^$(HASH)!' * 2>/dev/null)

# Everything ruff should see: the extension-less scripts, the shared helper
# modules, the test suite and the maintenance tools. The scripts are named one
# by one because ruff, given a directory, lints only its *.py files; `bin/`
# itself is what covers the helper modules, which have no shebang.
LINT_TARGETS := $(addprefix $(BIN)/,$(SCRIPTS)) $(BIN)/ tests/ tools/


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
		"./$(BIN)/$$s" --version || exit 1; \
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
	@./$(BIN)/bd-dolt-check .

dolt-diff: ## Preview the issue-level changes a 'bd dolt push' would send
	@./$(BIN)/bd-dolt-diff .

export-csv: ## Export this repo's beads to a CSV in the current directory
	@./$(BIN)/bd-export-csv .

.PHONY: dolt-check dolt-diff export-csv

# The render script deliberately lives under tools/ rather than in bin/:
# SCRIPTS is shebang-discovered, so a script in bin/ would be swept into
# `make smoke`, which runs `--version` on everything it finds.
#
# Not idempotent — the images capture live bead data and timestamps, so every
# run produces a diff even when nothing about the tools changed. That is not
# just noise: each regeneration adds another ~1 MB of PNG to git history,
# permanently. Regenerate deliberately, and commit only the images whose
# content actually changed.
screenshots: ## Regenerate the README's terminal screenshots into docs/img/
	@./tools/make-screenshots.py

.PHONY: screenshots


################################################################
## Claude Code integration
##
## The skills and hooks that make Claude Code follow the beads workflow.
## Symlinked into CLAUDE_HOME (default ~/.claude) exactly as `install` links
## scripts into PREFIX, with the same refusal to replace anything that is not
## already a symlink. A separate target so that someone who only wants the
## scripts never has ~/.claude touched. The hooks still have to be wired into
## settings.json by hand; the README has the snippet.

CLAUDE_HOME ?= $(HOME)/.claude
# Set DOCTOR_RUN=echo to see the install commands the doctor would run, without running them.
DOCTOR_RUN ?=
DOCTOR_ARGS = $(if $(DOCTOR_RUN),--run "$(DOCTOR_RUN)",)
HOOKS := $(wildcard hooks/*.sh)
# Each skill is a directory holding SKILL.md; the directory is what gets linked,
# as ~/.claude/skills/<name>, so the skill answers to /<name> with no prefix.
SKILLS := $(patsubst %/SKILL.md,%,$(wildcard skills/*/SKILL.md))

check-claude-home:
	@case "$(CLAUDE_HOME)" in \
	    "") echo "error: CLAUDE_HOME is empty"; exit 1;; \
	    "~"*) echo "error: cannot expand '$(CLAUDE_HOME)' — pass an absolute path"; exit 1;; \
	esac

# The hooks need jq and claim-guard likes GNU timeout: tools/doctor.py reports
# both and, on a terminal, offers to install them. jq declined means the hooks
# could not run, so the doctor exits 1 and nothing is linked. The check comes
# first so a refusal is not a half-install.
install-claude: check-claude-home ## Symlink the skills and hooks into CLAUDE_HOME (default ~/.claude)
	@python3 tools/doctor.py --for install-claude --offer $(DOCTOR_ARGS)
	@command -v bd-find-live >/dev/null 2>&1 || \
	    echo "note: bd-find-live is not on PATH; /close-shop needs it, so run 'make install' too"
	@for h in $(HOOKS) $(SKILLS); do \
	    target="$(CLAUDE_HOME)/$$h"; \
	    if [ -e "$$target" ] && [ ! -L "$$target" ]; then \
	        echo "refusing to replace non-symlink: $$target"; exit 1; \
	    fi; \
	done
	@mkdir -p "$(CLAUDE_HOME)/hooks" "$(CLAUDE_HOME)/skills"
	@for h in $(HOOKS) $(SKILLS); do \
	    ln -sfn "$(CURDIR)/$$h" "$(CLAUDE_HOME)/$$h" || exit 1; \
	done
	@echo "Linked $(words $(SKILLS)) skills and $(words $(HOOKS)) hooks into $(CLAUDE_HOME)"
	@echo "note: hooks run only once wired into settings.json; see the README sections"
	@echo "      'Guarding the beads workflow' and 'Keeping Claude Code memories'"

# unlink, not rm: it takes exactly one path and cannot recurse, which is all
# removing a symlink needs.
uninstall-claude: check-claude-home ## Remove the links that 'make install-claude' created
	@removed=0; failed=0; \
	for target in "$(CLAUDE_HOME)"/hooks/* "$(CLAUDE_HOME)"/skills/*; do \
	    [ -L "$$target" ] || continue; \
	    case "$$(readlink "$$target")" in \
	        "$(CURDIR)/hooks/"*|"$(CURDIR)/skills/"*) ;; \
	        *) continue;; \
	    esac; \
	    if unlink "$$target"; then \
	        removed=$$((removed + 1)); \
	    else \
	        failed=$$((failed + 1)); \
	    fi; \
	done; \
	echo "Removed $$removed symlink(s) from $(CLAUDE_HOME)"; \
	if [ "$$failed" -ne 0 ]; then \
	    echo "error: $$failed symlink(s) could not be removed"; exit 1; \
	fi

.PHONY: install-claude uninstall-claude check-claude-home


################################################################
## Installation
##
## Symlinks, not copies: the script still runs from this tree, so an edit
## takes effect with no reinstall. The cost is that moving or deleting this
## clone leaves the links dangling — `make uninstall` first if you relocate.
## The same property cuts both ways: writing to an installed name writes
## through to this tree, so `cp something $(PREFIX)/bd-log` silently edits
## your clone. (Observed, not theoretical.)
##
## This does NOT put PREFIX on your PATH, and it does not install shell
## completion. Both remain your shell's business; see `make completions`.
## It does check for the tools the scripts need (tools/doctor.py) and, on a
## terminal, offers to install each missing one; nothing in the global
## environment changes without a yes at that prompt.

# `~user`, `~+` and `~-` are deliberately refused rather than expanded: make
# has no way to look up another user's home, and guessing would recreate the
# literal-`~`-directory bug this guard exists to prevent.
check-prefix:
	@case "$(PREFIX)" in \
	    "") echo "error: PREFIX is empty"; exit 1;; \
	    "~"*) echo "error: cannot expand '$(PREFIX)' — pass an absolute path"; exit 1;; \
	esac

install: check-prefix ## Symlink every script into PREFIX (default ~/.local/bin)
	@for s in $(SCRIPTS); do \
	    target="$(PREFIX)/$$s"; \
	    if [ -e "$$target" ] && [ ! -L "$$target" ]; then \
	        echo "refusing to replace non-symlink: $$target"; exit 1; \
	    fi; \
	done
	@mkdir -p "$(PREFIX)"
	@for s in $(SCRIPTS); do \
	    ln -sfn "$(CURDIR)/$(BIN)/$$s" "$(PREFIX)/$$s" || exit 1; \
	done
	@echo "Linked $(words $(SCRIPTS)) scripts into $(PREFIX)"
	@case ":$$PATH:" in \
	    *":$(PREFIX):"*) ;; \
	    *) echo "note: $(PREFIX) is not on your PATH";; \
	esac
	@python3 tools/doctor.py --for install --offer $(DOCTOR_ARGS)

# Scans PREFIX for links back into this clone rather than iterating SCRIPTS,
# which is only the scripts that exist *now*: a script renamed or dropped
# since you installed would otherwise be left behind as a dangling link while
# the count claimed a complete uninstall. Only links to a file directly in
# bin/ count, so a hand-made link to something else inside the clone is not
# collateral -- plus links to a file directly at the root, which is where the
# scripts lived before bin/ and where an older `make install` pointed.
uninstall: check-prefix ## Remove the symlinks that 'make install' created
	@removed=0; failed=0; \
	for target in "$(PREFIX)"/*; do \
	    [ -L "$$target" ] || continue; \
	    case "$$(readlink "$$target")" in \
	        "$(CURDIR)/$(BIN)/"*/*) continue;; \
	        "$(CURDIR)/$(BIN)/"*) ;; \
	        "$(CURDIR)/"*/*) continue;; \
	        "$(CURDIR)/"*) ;; \
	        *) continue;; \
	    esac; \
	    if rm -f "$$target"; then \
	        removed=$$((removed + 1)); \
	    else \
	        failed=$$((failed + 1)); \
	    fi; \
	done; \
	echo "Removed $$removed symlink(s) from $(PREFIX)"; \
	if [ "$$failed" -ne 0 ]; then \
	    echo "error: $$failed symlink(s) could not be removed"; exit 1; \
	fi

.PHONY: install uninstall check-prefix


################################################################
## Housekeeping

version: ## Print the version string shared by every script
	@cd $(BIN) && python3 -c "import bdutils; print(bdutils.__version__)"

# The scripts must be on $PATH for completion to work, since the completion
# functions shell out to bd-complete by name.
completions: ## Print the line to add to your shell rc file for tab completion
	@echo "Add to ~/.zshrc (oh-my-zsh users: after 'source \$$ZSH/oh-my-zsh.sh'):"
	@echo "    source $(CURDIR)/completions/beads-utils.zsh"
	@echo ""
	@echo "Add to ~/.bashrc:"
	@echo "    source $(CURDIR)/completions/beads-utils.bash"
	@echo ""
	@echo "Also put $(CURDIR)/$(BIN) on your \$$PATH — the completions call bd-complete by name."

outdated: ## Report newer releases of the pinned tools
	@echo "❗ ruff:   pinned $(RUFF_VERSION), latest $$(uvx ruff@latest --version | awk '{print $$2}')"
	@echo "❗ pytest: pinned $(PYTEST_VERSION), latest $$($(UV_RUN) --with pytest \
		python -c 'import pytest; print(pytest.__version__)' 2>/dev/null)"

# tools/doctor.py reports the tools the scripts and hooks need and, on a terminal,
# offers to install each missing one; nothing is installed without a yes, and a
# pipe or CI gets the report alone. DOCTOR_RUN=echo makes it print the install
# commands instead of running them, which is how the tests exercise the offers.
doctor: ## Report which tools the scripts and hooks need are present, and offer to install the rest
	@python3 tools/doctor.py --offer $(DOCTOR_ARGS)

tags: ## Build an etags TAGS file over the scripts and modules
	@command -v etags >/dev/null || { echo "❌ etags not found"; exit 1; }
	@etags $(addprefix $(BIN)/,$(SCRIPTS)) $(BIN)/*.py tests/*.py
	@echo "✅ Wrote TAGS"

clean: ## Remove caches and generated reports
	@echo "🧹 Cleaning..."
	@rm -rf .pytest_cache .ruff_cache htmlcov .coverage coverage.xml TAGS
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@find . -name '*.pyc' -delete 2>/dev/null || true
	@echo "🧹 Clean complete."

.PHONY: version completions doctor outdated tags clean
