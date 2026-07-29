#!/usr/bin/env bash
set -Eeuo pipefail

ACTION="${1:-}"
BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="$(cd "$BACKEND_DIR/.." && pwd)"
RUN_DIR="${QUANTAGENT_RUN_DIR:-$APP_DIR/.run}"
PYTHON="${QUANTAGENT_BACKEND_PYTHON:-$BACKEND_DIR/.venv/bin/python}"
LAUNCHER="$BACKEND_DIR/scripts/run_email_delivery_worker.py"
PID_FILE="$RUN_DIR/email-worker.pid"
LOG_FILE="$RUN_DIR/email-worker.log"
START_LOCK="$RUN_DIR/email-worker.start.lock"
PROC_ROOT="${QUANTAGENT_PROC_ROOT:-/proc}"

mkdir -p "$RUN_DIR"
test -x "$PYTHON"
test -f "$LAUNCHER"

read_managed_pid() {
  [[ -s "$PID_FILE" ]] || return 1
  local pid
  IFS= read -r pid < "$PID_FILE" || return 1
  [[ "$pid" =~ ^[1-9][0-9]*$ ]] || return 1
  printf '%s\n' "$pid"
}

process_is_running() {
  local pid="$1"
  if [[ "$PROC_ROOT" != "/proc" ]]; then
    [[ -d "$PROC_ROOT/$pid" ]]
    return
  fi
  kill -0 "$pid" 2>/dev/null
}

process_is_canonical_worker() {
  local pid="$1"
  local cmdline="$PROC_ROOT/$pid/cmdline"
  local arg
  local -a args=()

  process_is_running "$pid" || return 1
  [[ -r "$cmdline" ]] || return 2
  while IFS= read -r -d '' arg; do
    args+=("$arg")
  done < "$cmdline"
  process_is_running "$pid" || return 1
  ((${#args[@]} >= 3)) || return 1
  [[ "${args[1]}" == "$LAUNCHER" ]] || return 1
  for arg in "${args[@]:2}"; do
    [[ "$arg" == "--loop" ]] && return 0
  done
  return 1
}

owned_process_ids() {
  if [[ "$PROC_ROOT" != "/proc" ]]; then
    local entry
    for entry in "$PROC_ROOT"/[0-9]*; do
      [[ -d "$entry" ]] || continue
      basename "$entry"
    done
    return 0
  fi
  ps -u "$(id -u)" -o pid=
}

scan_canonical_workers() {
  local process_ids
  local pid
  local result
  CANONICAL_WORKER_COUNT=0
  process_ids="$(owned_process_ids)" || return 2
  while IFS= read -r pid; do
    pid="${pid//[[:space:]]/}"
    [[ "$pid" =~ ^[1-9][0-9]*$ ]] || continue
    if process_is_canonical_worker "$pid"; then
      CANONICAL_WORKER_COUNT=$((CANONICAL_WORKER_COUNT + 1))
      continue
    else
      result="$?"
    fi
    if [[ "$result" -eq 2 ]]; then
      return 2
    fi
  done <<< "$process_ids"
}

assert_worker_absent() {
  if ! scan_canonical_workers; then
    echo "email_worker_absence_ambiguous" >&2
    return 1
  fi
  if [[ "$CANONICAL_WORKER_COUNT" -ne 0 ]]; then
    echo "email_worker_process_present" >&2
    return 1
  fi
  echo "email_worker_absent"
}

readiness() {
  cd "$BACKEND_DIR"
  "$PYTHON" "$LAUNCHER" --check --require-send-ready
}

case "$ACTION" in
  check)
    readiness
    ;;
  start)
    if ! mkdir "$START_LOCK" 2>/dev/null; then
      echo "email_worker_start_locked" >&2
      exit 1
    fi
    trap 'rmdir "$START_LOCK" 2>/dev/null || true' EXIT
    if pid="$(read_managed_pid)"; then
      if process_is_running "$pid"; then
        if process_is_canonical_worker "$pid"; then
          echo "email_worker_already_running" >&2
          exit 1
        else
          result="$?"
        fi
        if [[ "$result" -eq 2 ]]; then
          echo "email_worker_state_ambiguous" >&2
          exit 1
        fi
      fi
    fi
    rm -f "$PID_FILE"
    assert_worker_absent >/dev/null
    readiness >/dev/null
    cd "$BACKEND_DIR"
    nohup "$PYTHON" "$LAUNCHER" --loop >>"$LOG_FILE" 2>&1 &
    pid="$!"
    printf '%s\n' "$pid" >"$PID_FILE"
    sleep 2
    if ! process_is_canonical_worker "$pid"; then
      rm -f "$PID_FILE"
      echo "email_worker_start_failed" >&2
      exit 1
    fi
    echo "email_worker_started"
    ;;
  stop)
    if pid="$(read_managed_pid)"; then
      if process_is_running "$pid"; then
        if process_is_canonical_worker "$pid"; then
          kill "$pid"
          for _ in $(seq 1 30); do
            if ! process_is_running "$pid"; then
              break
            fi
            sleep 1
          done
          if process_is_running "$pid"; then
            echo "email_worker_stop_timeout" >&2
            exit 1
          fi
        else
          result="$?"
          if [[ "$result" -eq 2 ]]; then
            echo "email_worker_state_ambiguous" >&2
            exit 1
          fi
        fi
      fi
    fi
    rm -f "$PID_FILE"
    assert_worker_absent >/dev/null
    echo "email_worker_stopped"
    ;;
  status)
    if ! scan_canonical_workers; then
      echo "email_worker_state_ambiguous" >&2
      exit 2
    fi
    if [[ "$CANONICAL_WORKER_COUNT" -eq 0 ]]; then
      echo "email_worker_stopped"
      exit 1
    fi
    if [[ "$CANONICAL_WORKER_COUNT" -ne 1 ]] || ! pid="$(read_managed_pid)"; then
      echo "email_worker_unmanaged_process" >&2
      exit 2
    fi
    if process_is_canonical_worker "$pid"; then
      echo "email_worker_running"
    else
      echo "email_worker_unmanaged_process" >&2
      exit 2
    fi
    ;;
  verify-stopped)
    assert_worker_absent
    ;;
  *)
    echo "usage: manage_email_delivery_worker.sh {check|start|stop|status|verify-stopped}" >&2
    exit 2
    ;;
esac
