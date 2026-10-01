#!/usr/bin/env bash
set -euo pipefail

AGENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODEL_DIR="${HOME}/models"
MODEL_7B="${MODEL_DIR}/qwen2.5-coder-7b-instruct-q4_k_m.gguf"
MODEL_3B="${MODEL_DIR}/qwen2.5-coder-3b-instruct-q4_k_m.gguf"

# Default: 7B. Pass --small to use 3B.
MODEL="${MODEL_7B}"
if [[ "${1:-}" == "--small" ]]; then
  MODEL="${MODEL_3B}"
  echo "[launch] Using 3B fallback model"
fi

# Dynamically locate llama-server based on CMake version
if [[ -x "${HOME}/llama.cpp/build/bin/llama-server" ]]; then
    SERVER_BIN="${HOME}/llama.cpp/build/bin/llama-server"
elif [[ -x "${HOME}/llama.cpp/build/llama-server" ]]; then
    SERVER_BIN="${HOME}/llama.cpp/build/llama-server"
else
    SERVER_BIN="$(find "${HOME}/llama.cpp/build" -name llama-server -type f -executable 2>/dev/null | head -n 1 || true)"
fi

if [[ -z "${SERVER_BIN}" ]]; then
    echo "Could not find llama-server executable."
    exit 1
fi

# ponytail: Removed deprecated --kv-cache-type q8_0 (YAGNI, fits in 8GB VRAM fine with f16 defaults)
# ponytail: Dynamically point tee to AGENT_DIR instead of hardcoded ~/agent_team
exec "${SERVER_BIN}" \
  --model "${MODEL}" \
  -c 4096 \
  -t 8 \
  -b 512 \
  --host 0.0.0.0 \
  --port 8080 \
  --log-disable \
  2>&1 | tee "${AGENT_DIR}/logs/server.log"
