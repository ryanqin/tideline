#!/usr/bin/env bash
# Tideline install / requirement check.
#
# Verifies the environment, installs core + web + dev extras, runs the
# test suite, and checks for optional real-model dependencies. Idempotent
# — re-run any time to catch a missing dependency.
#
#   $ bash install.sh              # default: install + verify
#   $ PYTHON=python3.12 bash install.sh   # pin a specific interpreter

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

# Color codes — work in any modern terminal, degrade to plain on dumb ones.
if [ -t 1 ]; then
  C_BLUE=$'\033[34m'; C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'
  C_RED=$'\033[31m'; C_BOLD=$'\033[1m'; C_RESET=$'\033[0m'
else
  C_BLUE=''; C_GREEN=''; C_YELLOW=''; C_RED=''; C_BOLD=''; C_RESET=''
fi

step() { echo "${C_BLUE}${C_BOLD}==>${C_RESET} ${C_BOLD}$1${C_RESET}"; }
ok() { echo "    ${C_GREEN}ok${C_RESET}  $1"; }
warn() { echo "    ${C_YELLOW}warn${C_RESET}  $1"; }
fail() { echo "    ${C_RED}fail${C_RESET}  $1"; exit 1; }

echo
echo "${C_BOLD}Tideline${C_RESET} — install + requirement check"
echo

# --- 1. Python interpreter ----------------------------------------------

step "Python interpreter"
PYTHON="${PYTHON:-python3}"
command -v "$PYTHON" >/dev/null 2>&1 || fail "$PYTHON not on PATH"

PY_VERSION=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')")
PY_OK=$("$PYTHON" -c "import sys; print(1 if sys.version_info >= (3, 11) else 0)")
if [ "$PY_OK" -ne 1 ]; then
  fail "Python 3.11+ required, found $PY_VERSION"
fi
ok "Python $PY_VERSION ($PYTHON)"

"$PYTHON" -m pip --version >/dev/null 2>&1 || fail "pip not available for $PYTHON"
PIP_VERSION=$("$PYTHON" -m pip --version | awk '{print $2}')
ok "pip $PIP_VERSION"

# --- 2. Install core + extras -------------------------------------------

step "Install tideline core, web, dev extras"
"$PYTHON" -m pip install -e "./core[web,dev]" --quiet --upgrade-strategy only-if-needed
ok "core + web + dev installed (editable)"

# --- 3. Verify imports --------------------------------------------------

step "Verify Python imports"
"$PYTHON" -c "
import tideline
import tideline.agent
import tideline.cluster
import tideline.intelligence.concept_match
import tideline.intelligence.episodic_title
import tideline.promotion
import tideline.runtimes
import tideline.tools
import tideline.web.app
" || fail "import smoke failed — pyproject may be missing dependencies"
ok "all core modules import"

step "Verify web stack"
"$PYTHON" -c "
import fastapi
import uvicorn
from fastapi.testclient import TestClient
from tideline.web.app import create_app
app = create_app(runtime_name='mock', db_path=':memory:')
c = TestClient(app)
r = c.get('/')
assert r.status_code == 200, f'unexpected status: {r.status_code}'
r = c.post('/api/translate', json={'text': 'hello', 'target_lang': 'Chinese'})
assert r.status_code == 200, f'translate failed: {r.status_code}'
" || fail "web smoke failed"
ok "FastAPI app boots; /api/translate responds 200"

# --- 4. Run test suite --------------------------------------------------

step "Run full test suite"
cd "$REPO_ROOT/core"
TEST_OUTPUT=$("$PYTHON" -m pytest --tb=short -q 2>&1) || {
  echo "$TEST_OUTPUT"
  cd "$REPO_ROOT"
  fail "tests failed — see output above"
}
cd "$REPO_ROOT"
TEST_SUMMARY=$(echo "$TEST_OUTPUT" | grep -E "^[0-9]+ passed" | tail -1)
ok "${TEST_SUMMARY:-suite passed}"

# --- 5. Optional: real model runtime ------------------------------------

step "Optional real-model runtime (llama-cpp-python)"
if "$PYTHON" -c "import llama_cpp" >/dev/null 2>&1; then
  LLAMA_VERSION=$("$PYTHON" -c "import llama_cpp; print(llama_cpp.__version__)" 2>/dev/null || echo "?")
  ok "llama-cpp-python $LLAMA_VERSION (real runtime available)"
else
  warn "llama-cpp-python not installed (mock runtime still works)"
  echo "       To enable real Gemma inference:  pip install -e './core[real]'"
fi

# --- 6. Optional: GGUF model files --------------------------------------

step "Optional GGUF model files (./models/)"
GGUF_DIR="$REPO_ROOT/models"
GGUF_E2B="$GGUF_DIR/gemma-4-E2B-it-Q4_K_M.gguf"
GGUF_E4B="$GGUF_DIR/gemma-4-E4B-it-Q4_K_M.gguf"

if [ -f "$GGUF_E2B" ]; then
  SZ=$(du -h "$GGUF_E2B" | cut -f1)
  ok "E2B GGUF present ($SZ)"
else
  warn "E2B GGUF missing — needed for the default real-model runtime"
  echo "       huggingface-cli download unsloth/gemma-4-E2B-it-GGUF \\"
  echo "         --include 'gemma-4-E2B-it-Q4_K_M.gguf' --local-dir ./models/"
fi

if [ -f "$GGUF_E4B" ]; then
  SZ=$(du -h "$GGUF_E4B" | cut -f1)
  ok "E4B GGUF present ($SZ)"
else
  warn "E4B GGUF missing (optional, larger model for higher quality)"
fi

# --- 7. Quick-start hints -----------------------------------------------

echo
echo "${C_GREEN}${C_BOLD}Tideline ready.${C_RESET}"
echo
echo "Quick UI check (mock model, instant; outputs are echo strings):"
echo "  ${C_BOLD}python -m tideline.web --runtime mock --port 8000${C_RESET}"
echo
echo "Full demo (real model, ~90s prime + interactive):"
echo "  ${C_BOLD}python -m tideline.seed --db /tmp/tl.db${C_RESET}"
echo "  ${C_BOLD}python -m tideline.cluster --db /tmp/tl.db --runtime llama_cpp \\${C_RESET}"
echo "  ${C_BOLD}    --compare 200 --rebuild --name-clusters${C_RESET}"
echo "  ${C_BOLD}python -m tideline.web --runtime llama_cpp --db /tmp/tl.db --port 8000${C_RESET}"
echo
echo "Then open http://127.0.0.1:8000 in a browser."
echo
