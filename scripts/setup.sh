#!/usr/bin/env bash
# Full setup: build llama.cpp with CUDA, download models, verify endpoint
set -euo pipefail

# Edge case fix: Automatically detect where the repo actually is instead of hardcoding ~/agent_team
AGENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODELS_DIR="${HOME}/models"
LLAMA_DIR="${HOME}/llama.cpp"

echo "=== [1/6] Installing system dependencies ==="
if [[ -f /etc/arch-release ]]; then
    sudo pacman -Syu --noconfirm --needed \
        base-devel cmake git curl wget python-pip python-virtualenv \
        openssl pkgconf
elif command -v apt-get &> /dev/null; then
    sudo apt-get update -qq
    sudo apt-get install -y -qq \
        build-essential cmake git curl wget python3-pip python3-venv \
        libcurl4-openssl-dev libssl-dev pkg-config
else
    echo "Unsupported package manager. Please install dependencies manually."
fi

echo "=== [2/6] Building llama.cpp with CUDA ==="
if [[ ! -d "${LLAMA_DIR}" ]]; then
    git clone https://github.com/ggerganov/llama.cpp "${LLAMA_DIR}"
fi
cd "${LLAMA_DIR}"
# Edge case fix: Ignore git pull errors if local changes exist
git pull --ff-only || true

cmake -B build -DGGML_CUDA=OFF -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release -j"$(nproc)"
# Edge case fix: Depending on cmake version, binary might be in build/bin or build/
SERVER_BIN="$(find build -name llama-server -type f -executable | head -n 1)"
echo "llama-server built: $(${SERVER_BIN} --version 2>&1 | head -1)"

echo "=== [3/6] Creating directory structure ==="
mkdir -p \
    "${MODELS_DIR}" \
    "${AGENT_DIR}"/{grammars,harness,tools,agents,data,tests,logs,scripts} \
    "${HOME}/projects/godot_game/scripts" \
    "${HOME}/projects/unity_game/Assets/Scripts"

echo "=== [4/6] Downloading models ==="
# Ponytail: Do not use pip to install huggingface_hub globally. 
# It will crash on Ubuntu 24.04+ and Arch with "externally managed environment" (PEP 668).
# The standard library (or curl) can do this in one line.
download_gguf() {
    local filename="$1"
    local repo_id="$2"
    local out_path="${MODELS_DIR}/${filename}"
    if [[ ! -f "${out_path}" ]]; then
        echo "Downloading ${filename}..."
        curl -L -o "${out_path}" "https://huggingface.co/${repo_id}/resolve/main/${filename}"
    else
        echo "${filename} already exists."
    fi
}

download_gguf "qwen2.5-coder-7b-instruct-q4_k_m.gguf" "Qwen/Qwen2.5-Coder-7B-Instruct-GGUF"
download_gguf "qwen2.5-coder-3b-instruct-q4_k_m.gguf" "Qwen/Qwen2.5-Coder-3B-Instruct-GGUF"

echo "=== [5/6] Installing Python dependencies ==="
cd "${AGENT_DIR}"
python3 -m venv .venv
source .venv/bin/activate
pip install --quiet requests pyyaml pytest

echo "=== [6/6] Launching server and verifying endpoint ==="
# Edge case fix: Relying on the dynamic AGENT_DIR instead of a hardcoded path.
bash "${AGENT_DIR}/scripts/launch_server.sh" &
SERVER_PID=$!
echo "Server PID: ${SERVER_PID}"

# Wait for server to be ready
echo "Waiting for server..."
for i in $(seq 1 30); do
    if curl -sf http://localhost:8080/health > /dev/null 2>&1; then
        echo "Server ready after ${i}s"
        break
    fi
    sleep 1
done

# Smoke test
RESPONSE=$(curl -sf http://localhost:8080/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d '{"model":"qwen","messages":[{"role":"user","content":"Say OK"}],"max_tokens":5}' \
    2>&1 || true)

if echo "${RESPONSE}" | grep -q "content"; then
    echo "✓ Endpoint verified. Setup complete."
else
    echo "✗ Endpoint check failed. Response: ${RESPONSE}"
    kill ${SERVER_PID} 2>/dev/null || true
    exit 1
fi

echo ""
echo "To start the agent team:"
echo "  cd ${AGENT_DIR} && source .venv/bin/activate && python main.py"
