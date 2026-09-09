set dotenv-load

PYTHON := "python"
DOCKER_NAME := "yutto"
VERSION := "2.3.1"

_default:
  @just --list

# dev
install:
  uv sync --all-extras --dev

install-min:
  uv sync --no-dev --no-default-groups

format:
  uv run ruff format .

lint:
  uv run ty check --error-on-warning src/yutto packages/biliass/src/biliass tests
  uv run ruff check .
  uv run typos

fix:
  uv run ruff check --fix .

check:
  just format
  just lint

# test
test *ARGS:
  uv run pytest {{ARGS}}

test-api *ARGS:
  uv run pytest -m "api" {{ARGS}}

test-e2e *ARGS:
  uv run pytest -m "e2e" {{ARGS}}

test-processor *ARGS:
  uv run pytest -m "processor" {{ARGS}}

test-biliass *ARGS:
  uv run pytest -m "biliass" {{ARGS}}

# build
build:
  uv build

build-wheel:
  uv build --wheel

build-sdist:
  uv build --sdist

# docs
docs-install:
  pnpm --dir docs install

docs-dev:
  pnpm --dir docs dev

docs-build:
  pnpm --dir docs build

docs-preview:
  pnpm --dir docs preview

docs-check:
  pnpm --dir docs check

# schema
generate-schema:
  uv run scripts/generate-schema.py

# CI specific
ci-install pyversion:
  uv sync --locked --all-extras --dev -p {{pyversion}}

ci-fmt-check:
  uv run ruff format --check --diff .

ci-lint:
  just lint

ci-test pyversion:
  uv run -p {{pyversion}} pytest -m "(api or processor or biliass) and not (ci_skip or ignore)" --reruns 3 --reruns-delay 1
  uv run -p {{pyversion}} pytest tests/test_core/test_options.py tests/test_download_manager_media.py tests/test_listing.py tests/test_parser.py tests/test_resource.py tests/test_selection.py tests/test_selection_priority.py tests/test_source.py tests/test_source_all_favourites.py tests/test_source_publication_filter.py tests/test_source_ugc_containers.py --reruns 3 --reruns-delay 1

ci-e2e-test pyversion:
  uv run -p {{pyversion}} pytest -m "e2e and not (ci_skip or ignore)"

# docker specific
docker-run *ARGS:
  docker run --rm -it -v `pwd`:/app {{DOCKER_NAME}} {{ARGS}}
docker-build:
  docker build --no-cache -t "{{DOCKER_NAME}}:{{VERSION}}" -t "{{DOCKER_NAME}}:latest" .
