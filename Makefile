.PHONY: lint typecheck test build clean mypyc mypyc-clean test-mypyc bench bench-compare bench-py \
	docs docs-serve

lint:
	@uv run ruff check h11_mypyc tests --fix

typecheck:
	@uv run mypy h11_mypyc

test:
	@uv run pytest tests -q

build:
	@uv build

clean: mypyc-clean
	@rm -rf dist site

# Compiles in place, next to the .py sources: Python prefers the .so, so
# `import h11_mypyc` picks up the compiled build. `make mypyc-clean` reverts it.
mypyc: mypyc-clean
	@uv run env H11_MYPYC=1 python setup.py build_ext --inplace

mypyc-clean:
	@rm -rf build *.egg-info
	@rm -f h11_mypyc/*.so *.so

# The compiled build is where annotations become runtime checks, so it can fail
# where the interpreted one passes.
test-mypyc: mypyc
	@uv run pytest tests -q

# --- docs ----------------------------------------------------------------
#
# Zensical renders docs/src/*.md into site/. Everything else under docs/ is
# build input that must stay outside docs_dir, because Zensical publishes every
# file it finds there and has no exclude setting -- that is where the Mermaid
# state-machine diagrams in docs/includes/ live. They mirror the transition
# tables in h11_mypyc/_state.py, so edit them alongside it.

# --clean, not the incremental default: Zensical's cache keys off the page
# sources, so editing a snippet under docs/includes/ does not invalidate the
# pages that pull it in.
docs:
	@uv run --group docs zensical build --clean --strict

# The preview server has the same blind spot: restart it after editing a
# snippet under docs/includes/.
docs-serve:
	@uv run --group docs zensical serve

# --- benchmarks ----------------------------------------------------------

# PYTHONPATH=. finds mypyc's shared runtime module, which lands in the repo
# root while a script run puts only its own directory on sys.path.
bench:
	@PYTHONPATH=. uv run python -c "import h11_mypyc; \
	print('mode:', 'mypyc' if h11_mypyc._connection.__file__.endswith('.so') else 'pure Python')"
	@PYTHONPATH=. uv run python bench/benchmarks/benchmarks.py

bench-compare:
	@$(MAKE) --no-print-directory mypyc-clean
	@echo "=== pure Python ==="
	@$(MAKE) --no-print-directory bench
	@$(MAKE) --no-print-directory mypyc
	@echo "=== mypyc ==="
	@$(MAKE) --no-print-directory bench
	@$(MAKE) --no-print-directory mypyc-clean

bench-py:
	@uv run pytest tests/test_benchmarks.py --codspeed
