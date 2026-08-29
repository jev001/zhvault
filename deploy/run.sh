#!/usr/bin/env bash
# Read deploy/zhvault.ini, take a single-flight lock under data/run/{job}.pid, run zhvault.
# Usage: ./deploy/run.sh <job>   e.g. backup | resume | status
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
INI="${ZHVAULT_INI:-$ROOT/deploy/zhvault.ini}"
JOB="${1:-}"

if [[ -z "$JOB" || "$JOB" == "-h" || "$JOB" == "--help" ]]; then
  echo "Usage: $0 <job>"
  echo "INI: $INI"
  if [[ -f "$INI" ]]; then
    echo "Jobs:"
    grep -E '^\[run\.' "$INI" | sed 's/^\[run\./  /;s/\]$//'
  fi
  exit 0
fi

if [[ ! -f "$INI" ]]; then
  echo "error: ini not found: $INI" >&2
  exit 2
fi

# Print: LOCK_DIR DATA_DIR ENGINE JSON COOKIE XZSE CMD SOURCE FULL (tab-separated extras as KEY=VAL)
eval "$(
  python3 - "$INI" "$JOB" <<'PY'
import configparser
import shlex
import sys
from pathlib import Path

ini_path, job = sys.argv[1], sys.argv[2]
cp = configparser.ConfigParser()
if not cp.read(ini_path):
    print("echo error: failed to read ini >&2; exit 2")
    sys.exit(0)
sec = f"run.{job}"
if sec not in cp:
    print(f"echo error: missing section [{sec}] >&2; exit 2")
    sys.exit(0)

def g(section: str, key: str, default: str = "") -> str:
    if cp.has_option(section, key):
        return cp.get(section, key).strip()
    if cp.has_option("common", key):
        return cp.get("common", key).strip()
    return default

lock_dir = g("lock", "dir", "data/run")
data_dir = g(sec, "data_dir", g("common", "data_dir", "data"))
engine = g(sec, "engine", g("common", "engine", "sqlite"))
json_flag = g(sec, "json", g("common", "json", "true")).lower() in ("1", "true", "yes", "on")
cookie = g(sec, "cookie_file", g("common", "cookie_file", ""))
xzse = g(sec, "x_zse_96", g("common", "x_zse_96", ""))
cmd = g(sec, "cmd", "")
source = g(sec, "source", "")
full = g(sec, "full", "false").lower() in ("1", "true", "yes", "on")
if not cmd:
    print(f"echo error: [{sec}] missing cmd= >&2; exit 2")
    sys.exit(0)

exports = {
    "LOCK_DIR": lock_dir,
    "DATA_DIR": data_dir,
    "ENGINE": engine,
    "JSON_FLAG": "1" if json_flag else "0",
    "COOKIE_FILE": cookie,
    "X_ZSE_96": xzse,
    "ZH_CMD": cmd,
    "SOURCE": source,
    "FULL_FLAG": "1" if full else "0",
}
for k, v in exports.items():
    print(f"{k}={shlex.quote(v)}")
PY
)"

LOCK_DIR_ABS="$ROOT/$LOCK_DIR"
mkdir -p "$LOCK_DIR_ABS"
PIDFILE="$LOCK_DIR_ABS/${JOB}.pid"

if [[ -f "$PIDFILE" ]]; then
  old="$(tr -d '[:space:]' <"$PIDFILE" || true)"
  if [[ -n "$old" ]] && kill -0 "$old" 2>/dev/null; then
    echo "error: job '$JOB' already running (pid=$old, lock=$PIDFILE)" >&2
    exit 1
  fi
  echo "info: removing stale lock $PIDFILE (pid=$old)" >&2
  rm -f "$PIDFILE"
fi

echo $$ >"$PIDFILE"
cleanup() { rm -f "$PIDFILE"; }
trap cleanup EXIT INT TERM

cd "$ROOT"

if command -v uv >/dev/null 2>&1; then
  RUN=(uv run zhvault)
elif command -v zhvault >/dev/null 2>&1; then
  RUN=(zhvault)
else
  echo "error: neither uv nor zhvault on PATH; run make sync first" >&2
  exit 127
fi

ARGS=("$ZH_CMD" --data-dir "$DATA_DIR" --engine "$ENGINE")
[[ "$JSON_FLAG" == "1" ]] && ARGS+=(--json)
[[ -n "$COOKIE_FILE" ]] && ARGS+=(--cookie-file "$COOKIE_FILE")
[[ -n "$X_ZSE_96" ]] && ARGS+=(--x-zse-96 "$X_ZSE_96")
[[ -n "$SOURCE" ]] && ARGS+=(--source "$SOURCE")
[[ "$FULL_FLAG" == "1" ]] && ARGS+=(--full)

echo "info: start job=$JOB cmd=${RUN[*]} ${ARGS[*]} lock=$PIDFILE" >&2
"${RUN[@]}" "${ARGS[@]}"
ec=$?
echo "info: done job=$JOB exit=$ec" >&2
exit "$ec"
