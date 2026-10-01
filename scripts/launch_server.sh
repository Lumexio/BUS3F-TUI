# ~/agent_team/scripts/launch_server.sh
#!/usr/bin/env bash
set -euo pipefail

MODEL_DIR="${HOME}/models"
MODEL_7B="${MODEL_DIR}/qwen2.5-coder-7b-instruct-q4_k_m.gguf"
MODEL_3B="${MODEL_DIR}/qwen2.5-coder-3b-instruct-q4_k_m.gguf"

# Default: active model from config.json, or 7B default
MODEL="${MODEL_7B}"
if [ -f "${HOME}/agent_team/config.json" ]; then
  CFG_MODEL="$(grep -o '"active_model": *"[^"]*"' "${HOME}/agent_team/config.json" | cut -d'"' -f4 || true)"
  if [ -n "${CFG_MODEL}" ] && [ -f "${MODEL_DIR}/${CFG_MODEL}" ]; then
    MODEL="${MODEL_DIR}/${CFG_MODEL}"
  elif [ -n "${CFG_MODEL}" ] && [ -f "${CFG_MODEL}" ]; then
    MODEL="${CFG_MODEL}"
  fi
fi

if [[ "${1:-}" == "--small" ]]; then
  MODEL="${MODEL_3B}"
  echo "[launch] Using 3B fallback model"
fi

# Flags:
#   -ngl 99        : offload all layers to GPU (P4000 has enough for 7B Q4_K_M)
#   -c 4096        : context window (KV cache fits in remaining VRAM)
#   -t 8           : CPU threads (matches Ryzen 7700X physical cores)
#   --kv-cache-type q8_0 : halves KV cache VRAM from ~1.5GB to ~0.75GB
#   --no-mmap      : WSL2 mmap is unreliable with large GGUF
#   -b 512         : batch size — balanced for single-user inference
#   --host 0.0.0.0 : listen on all interfaces inside WSL

LLAMA_BIN="${HOME}/llama.cpp/build/bin/llama-server"
[ ! -x "${LLAMA_BIN}" ] && LLAMA_BIN="$(command -v llama-server || true)"
if [ -z "${LLAMA_BIN}" ] || [ ! -x "${LLAMA_BIN}" ]; then
  echo "[launch] Error: llama-server not found. Run ./setup.sh to build it." >&2
  exit 1
fi

exec "${LLAMA_BIN}" \
  --model "${MODEL}" \
  -ngl 99 \
  -c 4096 \
  -np 2 \
  -t 8 \
  -b 512 \
  --kv-cache-type q8_0 \
  --no-mmap \
  --host 0.0.0.0 \
  --port 8080 \
  --log-disable \
  2>&1 | tee "${HOME}/agent_team/logs/server.log"
