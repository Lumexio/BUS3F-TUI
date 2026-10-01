#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "$0")/.." && pwd)"
MODEL_DIR="${HOME}/models"
DEFAULT_MODEL="${MODEL_DIR}/qwen2.5-coder-7b-instruct-q4_k_m.gguf"
mkdir -p "${DIR}/logs"

# Resolve active model from CLI arg, config.json, or default 7B
MODEL="${DEFAULT_MODEL}"
if [ -n "${1:-}" ]; then
  if [ -f "$1" ]; then
    MODEL="$1"
  elif [ -f "${MODEL_DIR}/$1" ]; then
    MODEL="${MODEL_DIR}/$1"
  fi
else
  CFG_FILE="${DIR}/config.json"
  [ ! -f "${CFG_FILE}" ] && CFG_FILE="${HOME}/agent_team/config.json"
  if [ -f "${CFG_FILE}" ]; then
    CFG_MODEL="$(python3 -c "import json; print(json.load(open('${CFG_FILE}')).get('active_model', ''))" 2>/dev/null || true)"
    if [ -n "${CFG_MODEL}" ] && [ -f "${MODEL_DIR}/${CFG_MODEL}" ]; then
      MODEL="${MODEL_DIR}/${CFG_MODEL}"
    elif [ -n "${CFG_MODEL}" ] && [ -f "${CFG_MODEL}" ]; then
      MODEL="${CFG_MODEL}"
    fi
  fi
fi

if [ ! -f "${MODEL}" ]; then
  FIRST_GGUF="$(ls "${MODEL_DIR}"/*.gguf 2>/dev/null | head -n 1 || true)"
  [ -n "${FIRST_GGUF}" ] && [ -f "${FIRST_GGUF}" ] && MODEL="${FIRST_GGUF}"
fi

if [ ! -f "${MODEL}" ]; then
  echo "[launch] Error: No GGUF model found in ${MODEL_DIR}. Run setup.sh or download via /new-model." >&2
  exit 1
fi

LLAMA_BIN="${HOME}/llama.cpp/build/bin/llama-server"
[ ! -x "${LLAMA_BIN}" ] && LLAMA_BIN="$(command -v llama-server || true)"
if [ -z "${LLAMA_BIN}" ] || [ ! -x "${LLAMA_BIN}" ]; then
  echo "[launch] Error: llama-server not found. Run ./setup.sh to build it." >&2
  exit 1
fi

THREADS="${LLAMA_THREADS:-$(python3 -c 'import os; print(os.cpu_count() or 4)')}"
PORT="${LLAMA_PORT:-8080}"

exec "${LLAMA_BIN}" \
  --model "${MODEL}" \
  -ngl 99 \
  -c 16384 \
  -np 2 \
  -t "${THREADS}" \
  -b 512 \
  --host 0.0.0.0 \
  --port "${PORT}" \
  2>&1 | tee "${DIR}/logs/server.log"
