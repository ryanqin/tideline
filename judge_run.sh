#!/usr/bin/env bash
# judge_run.sh — one command from a clean checkout to a working Tideline demo.
#
# This is Tideline's "Reproducibility" deliverable for the Kaggle Gemma 4
# Good Hackathon judges. Run it after install.sh has set the environment.
#
#   $ bash install.sh        # one-time: install deps + verify pyproject
#   $ bash judge_run.sh      # repeatable: seed → prime → launch UI
#
# What it does:
#   1. Verifies install.sh has been run (imports work)
#   2. Picks a runtime: llama_cpp (real Gemma) if GGUF + lib available,
#      otherwise mock (UI shape only)
#   3. Seeds a fresh demo DB with 147 translations across 6 scenarios
#   4. Primes the cluster engine: 200 votes + rebuild + episodic naming
#      (~90s on E2B real model, instant under mock)
#   5. Starts the web playground on http://127.0.0.1:8000
#   6. Opens it in the default browser
#   7. Stays in foreground; Ctrl+C cleanly shuts the server down
#
# Override:
#   PORT=8765 bash judge_run.sh         # custom port
#   FORCE_MOCK=1 bash judge_run.sh      # skip GGUF check, use mock
#   SKIP_PRIME=1 bash judge_run.sh      # don't re-prime an existing DB
#   NO_BROWSER=1 bash judge_run.sh      # don't auto-open browser

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

# --- styling ------------------------------------------------------------

if [ -t 1 ]; then
  C_BLUE=$'\033[34m'; C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'
  C_RED=$'\033[31m'; C_BOLD=$'\033[1m'; C_DIM=$'\033[2m'; C_RESET=$'\033[0m'
else
  C_BLUE=''; C_GREEN=''; C_YELLOW=''; C_RED=''; C_BOLD=''; C_DIM=''; C_RESET=''
fi

step() { echo "${C_BLUE}${C_BOLD}==>${C_RESET} ${C_BOLD}$1${C_RESET}"; }
ok() { echo "    ${C_GREEN}ok${C_RESET}  $1"; }
warn() { echo "    ${C_YELLOW}warn${C_RESET}  $1"; }
fail() { echo "    ${C_RED}fail${C_RESET}  $1"; exit 1; }

echo
echo "${C_BOLD}Tideline${C_RESET} — demo runner (Kaggle Gemma 4 Good Hackathon)"
echo

# --- config -------------------------------------------------------------

PYTHON="${PYTHON:-python3}"
PORT="${PORT:-8000}"
DB_PATH="${DB_PATH:-/tmp/tideline-demo.db}"
URL="http://127.0.0.1:${PORT}"

# --- 1. precheck: install.sh ran ---------------------------------------

step "Precheck — install.sh has been run"
if ! "$PYTHON" -c "import tideline.web.app" >/dev/null 2>&1; then
  fail "tideline.web not importable. Run: bash install.sh"
fi
ok "tideline.web imports"

# --- 2. pick runtime ----------------------------------------------------

step "Pick runtime (real Gemma vs mock)"
RUNTIME="mock"
GGUF="$REPO_ROOT/models/gemma-4-E2B-it-Q4_K_M.gguf"

if [ "${FORCE_MOCK:-0}" = "1" ]; then
  warn "FORCE_MOCK=1 — using mock runtime (UI shape only, no real translations)"
elif ! "$PYTHON" -c "import llama_cpp" >/dev/null 2>&1; then
  warn "llama-cpp-python not installed — falling back to mock"
  echo "       For real Gemma: pip install -e './core[real]'"
elif [ ! -f "$GGUF" ]; then
  warn "GGUF missing at $GGUF — falling back to mock"
  echo "       To download: huggingface-cli download unsloth/gemma-4-E2B-it-GGUF \\"
  echo "         --include 'gemma-4-E2B-it-Q4_K_M.gguf' --local-dir ./models/"
else
  RUNTIME="llama_cpp"
  ok "real Gemma 4 E2B available"
fi
ok "runtime: $RUNTIME"

# --- 3. seed fresh demo DB ---------------------------------------------

step "Seed demo database"
if [ -f "$DB_PATH" ] && [ "${SKIP_PRIME:-0}" = "1" ]; then
  ok "existing DB at $DB_PATH (SKIP_PRIME=1)"
else
  rm -f "$DB_PATH"
  "$PYTHON" -m tideline.seed --db "$DB_PATH" >/dev/null
  ok "seeded 147 translations into $DB_PATH"
fi

# --- 4. prime cluster engine -------------------------------------------

if [ "${SKIP_PRIME:-0}" = "1" ]; then
  step "Skip cluster priming (SKIP_PRIME=1)"
  ok "using existing cluster state"
else
  step "Prime cluster engine — vote, rebuild, name (~90s on real model)"
  if [ "$RUNTIME" = "llama_cpp" ]; then
    echo "    ${C_DIM}(this is the slow step — please wait)${C_RESET}"
  fi
  "$PYTHON" -m tideline.cluster \
      --db "$DB_PATH" --runtime "$RUNTIME" \
      --compare 200 --rebuild --name-clusters 2>/dev/null | \
    sed 's/^/    /'
  ok "cluster priming done"
fi

# --- 5. start web server (background) ----------------------------------

step "Start web server on $URL"
LOG=$(mktemp -t tideline-web-XXXXXX.log)
"$PYTHON" -m tideline.web \
    --runtime "$RUNTIME" \
    --db "$DB_PATH" \
    --host 127.0.0.1 --port "$PORT" >"$LOG" 2>&1 &
UVICORN_PID=$!

# trap so Ctrl+C drops the server cleanly. We rely on EXIT for the
# actual teardown; INT/TERM handlers just exit explicitly so the EXIT
# trap fires (bash `wait` doesn't always unblock on signal alone).
TAIL_PID=""
cleanup() {
  if [ -n "$TAIL_PID" ] && kill -0 "$TAIL_PID" 2>/dev/null; then
    kill "$TAIL_PID" 2>/dev/null || true
  fi
  if kill -0 "$UVICORN_PID" 2>/dev/null; then
    echo
    echo "${C_DIM}stopping web server (pid $UVICORN_PID)…${C_RESET}"
    kill -TERM "$UVICORN_PID" 2>/dev/null || true
    # Give uvicorn ~3s to drain; force-kill if it lingers.
    for _ in 1 2 3; do
      kill -0 "$UVICORN_PID" 2>/dev/null || break
      sleep 1
    done
    kill -KILL "$UVICORN_PID" 2>/dev/null || true
  fi
  rm -f "$LOG"
}
trap cleanup EXIT
trap 'exit 0' INT TERM

# --- 6. wait for readiness ---------------------------------------------

step "Wait for web server ready"
for i in $(seq 1 30); do
  if curl -s -o /dev/null -w "%{http_code}" "$URL/" 2>/dev/null | grep -q "200"; then
    ok "$URL responding (took ${i}s)"
    break
  fi
  if ! kill -0 "$UVICORN_PID" 2>/dev/null; then
    echo
    echo "${C_RED}web server died during startup:${C_RESET}"
    tail -20 "$LOG"
    exit 1
  fi
  sleep 1
done

if ! curl -s -o /dev/null -w "%{http_code}" "$URL/" 2>/dev/null | grep -q "200"; then
  echo
  echo "${C_RED}web server didn't respond within 30s${C_RESET}"
  tail -20 "$LOG"
  exit 1
fi

# --- 7. open browser ---------------------------------------------------

if [ "${NO_BROWSER:-0}" = "1" ]; then
  step "Skip browser open (NO_BROWSER=1)"
else
  step "Open browser"
  case "$(uname -s)" in
    Darwin) open "$URL" ;;
    Linux)
      if command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$URL" >/dev/null 2>&1 &
      else
        warn "xdg-open not found — open $URL manually"
      fi ;;
    *) warn "unknown OS $(uname -s) — open $URL manually" ;;
  esac
  ok "browser invoked"
fi

# --- 8. foreground loop ------------------------------------------------

echo
echo "${C_GREEN}${C_BOLD}Tideline demo running.${C_RESET}"
echo
echo "    Open ${C_BOLD}$URL${C_RESET} in your browser (or use the auto-opened tab)."
echo "    Translator on home, learnings panel at $URL/learnings."
echo
echo "    Try translating ${C_BOLD}sushi${C_RESET} to Chinese, then visit /learnings"
echo "    to see clusters already shaped from the seeded corpus."
echo
echo "    Press ${C_BOLD}Ctrl+C${C_RESET} to stop the server."
echo

# Tail the uvicorn log so judges see request activity while they click around.
tail -f "$LOG" &
TAIL_PID=$!

wait "$UVICORN_PID"
