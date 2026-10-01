# ~/agent_team/scripts/setup.sh
#!/usr/bin/env bash
# Full setup: build llama.cpp with CUDA, download models, verify endpoint
set -euo pipefail

MODELS_DIR="${HOME}/models"
LLAMA_DIR="${HOME}/llama.cpp"
AGENT_DIR="${HOME}/agent_team"

echo "=== [1/6] Installing system dependencies ==="
sudo apt-get update -qq
sudo apt-get install -y -qq \
    build-essential cmake git curl wget python3-pip python3-venv \
    libcurl4-openssl-dev libssl-dev pkg-config

echo "=== [2/6] Building llama.cpp with CUDA ==="
if [[ ! -d "${LLAMA_DIR}" ]]; then
    git clone https://github.com/ggerganov/llama.cpp "${LLAMA_DIR}"
fi
cd "${LLAMA_DIR}"
git pull --ff-only

cmake -B build \
    -DGGML_CUDA=ON \
    -DCMAKE_CUDA_ARCHITECTURES=61 \
    -DCMAKE_BUILD_TYPE=Release \
    -DLLAMA_CURL=ON
cmake --build build --config Release -j"$(nproc)"
echo "llama-server built: $(./build/bin/llama-server --version 2>&1 | head -1)"

echo "=== [3/6] Creating directory structure ==="
mkdir -p \
    "${MODELS_DIR}" \
    "${AGENT_DIR}"/{grammars,harness,tools,agents,data,tests,logs,scripts} \
    "${HOME}/projects/godot_game/scripts" \
    "${HOME}/projects/unity_game/Assets/Scripts"

echo "=== [4/6] Downloading models ==="
# Using Hugging Face CLI — install if not present
pip3 install --quiet huggingface_hub

MODEL_7B="${MODELS_DIR}/qwen2.5-coder-7b-instruct-q4_k_m.gguf"
MODEL_3B="${MODELS_DIR}/qwen2.5-coder-3b-instruct-q4_k_m.gguf"

if [[ ! -f "${MODEL_7B}" ]]; then
    echo "Downloading Qwen2.5-Coder-7B Q4_K_M..."
    python3 -c "
from huggingface_hub import hf_hub_download
hf_hub_download(
    repo_id='Qwen/Qwen2.5-Coder-7B-Instruct-GGUF',
    filename='qwen2.5-coder-7b-instruct-q4_k_m.gguf',
    local_dir='${MODELS_DIR}'
)
print('7B model downloaded.')
"
fi

if [[ ! -f "${MODEL_3B}" ]]; then
    echo "Downloading Qwen2.5-Coder-3B Q4_K_M..."
    python3 -c "
from huggingface_hub import hf_hub_download
hf_hub_download(
    repo_id='Qwen/Qwen2.5-Coder-3B-Instruct-GGUF',
    filename='qwen2.5-coder-3b-instruct-q4_k_m.gguf',
    local_dir='${MODELS_DIR}'
)
print('3B model downloaded.')
"
fi

echo "=== [5/6] Installing Python dependencies ==="
cd "${AGENT_DIR}"
python3 -m venv .venv
source .venv/bin/activate
pip install --quiet requests pyyaml pytest

echo "=== [6/6] Launching server and verifying endpoint ==="
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
    2>&1)

if echo "${RESPONSE}" | grep -q "content"; then
    echo "✓ Endpoint verified. Setup complete."
else
    echo "✗ Endpoint check failed. Response: ${RESPONSE}"
    kill ${SERVER_PID} 2>/dev/null || true
    exit 1
fi

echo ""
echo "To start the agent team:"
echo "  cd ~/agent_team && source .venv/bin/activate && python main.py"
