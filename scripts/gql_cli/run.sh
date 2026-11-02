#!/usr/bin/env bash
#
# Run the gql_cli harness with the repo's own virtualenv (no extra dependency).
# Config (incl. PEEK_AUTH_TOKEN) is read from ./.env in this folder; if the
# token is unset the CLI prompts for it.
#
#   ./run.sh [--pii] <function_name> [params...]
#   ./run.sh help
#   ./run.sh help <function_name>
#
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$DIR/../.." && pwd)"

PYTHON="$ROOT/.venv/bin/python"
if [ ! -x "$PYTHON" ]; then
  echo "python not found at $PYTHON — run 'uv sync --group dev' in the repo root first." >&2
  exit 1
fi

# cwd = this folder so the CLI reads ./.env from here; PYTHONPATH = the repo
# root so `-m scripts.gql_cli.cli` resolves (the package itself is installed
# into .venv in editable mode).
cd "$DIR"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
exec "$PYTHON" -m scripts.gql_cli.cli "$@"
