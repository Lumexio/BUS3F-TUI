#!/usr/bin/env bash
set -e

[ -z "$BASH_VERSION" ] && exec bash "$0" "$@"
DIR="$(cd "$(dirname "$0")" && pwd)"
BIN_DIR="${HOME}/.local/bin"
mkdir -p "${BIN_DIR}"

echo "=========================================="
echo "      bus3f-tui One-Time Installer        "
echo "=========================================="
# 1. Automatic OS & Package Manager Detection
echo "[1/7] Detecting distribution & package manager..."
DISTRO="unknown"
[ -f /etc/os-release ] && . /etc/os-release && DISTRO="${ID:-unknown}"

if command -v pacman >/dev/null 2>&1 || [ "$DISTRO" = "arch" ] || [ "${ID_LIKE:-}" = "arch" ]; then
    echo "  → Arch Linux detected (${DISTRO})"
    sudo pacman -S --needed --noconfirm git curl cmake base-devel python python-pip python-requests python-prompt_toolkit python-pygments python-yaml
elif command -v apt-get >/dev/null 2>&1 || [ "$DISTRO" = "ubuntu" ] || [ "$DISTRO" = "debian" ]; then
    echo "  → Debian/Ubuntu detected (${DISTRO})"
    PKGS="git curl cmake build-essential"
    command -v python3 >/dev/null 2>&1 || PKGS="python3 python3-venv ${PKGS}"
    sudo apt-get update -qq && sudo apt-get install -y -qq ${PKGS}
elif command -v dnf >/dev/null 2>&1; then
    echo "  → Fedora/RHEL detected (${DISTRO})"
    sudo dnf install -y git curl cmake gcc-c++ python3 python3-pip
else
    echo "  → Generic Linux (${DISTRO}); skipping system package install"
fi

# 2. llama.cpp setup
echo "[2/7] Checking llama-server binary..."
LLAMA_BIN="${HOME}/llama.cpp/build/bin/llama-server"
if [ ! -x "${LLAMA_BIN}" ] && ! command -v llama-server >/dev/null 2>&1; then
    echo "llama-server not found. Building llama.cpp..."
    [ -d "${HOME}/llama.cpp" ] || git clone --depth 1 https://github.com/ggerganov/llama.cpp "${HOME}/llama.cpp"
    CUDA_OPT=""
    command -v nvcc >/dev/null 2>&1 && CUDA_OPT="-DGGML_CUDA=ON"
    cmake -B "${HOME}/llama.cpp/build" "${HOME}/llama.cpp" ${CUDA_OPT}
    cmake --build "${HOME}/llama.cpp/build" --config Release -j "$(python3 -c 'import os; print(os.cpu_count() or 4)')" --target llama-server
fi

# 3. Virtual environment setup (optional, fallback to system python)
echo "[3/7] Setting up Python venv..."
if [ ! -f "${DIR}/venv/bin/python" ]; then
    python3 -m venv --system-site-packages "${DIR}/venv" 2>/dev/null || python3 -m venv "${DIR}/venv" 2>/dev/null || true
fi
if [ -x "${DIR}/venv/bin/pip" ]; then
    "${DIR}/venv/bin/pip" install --quiet requests prompt_toolkit pygments tree-sitter tree-sitter-c-sharp || true
fi

# 4. Create global 'bus3f-tui' command
echo "[4/7] Installing 'bus3f-tui' launcher..."
cat << EOF > "${BIN_DIR}/bus3f-tui"
#!/usr/bin/env bash
TEAM_DIR="${DIR}"
PYTHON_BIN="\${TEAM_DIR}/venv/bin/python"
if [ ! -x "\${PYTHON_BIN}" ]; then
    PYTHON_BIN="\$(command -v python3 || command -v python)"
fi
# Auto-start llama-server if not running and models exist
if [ -n "\$(ls -A "\${HOME}/models"/*.gguf 2>/dev/null)" ] && ! curl -s http://localhost:8080/health >/dev/null 2>&1; then
    if [ -f "\${TEAM_DIR}/scripts/launch_server.sh" ]; then
        nohup bash "\${TEAM_DIR}/scripts/launch_server.sh" >/dev/null 2>&1 &
        for i in {1..15}; do
            curl -s http://localhost:8080/health >/dev/null 2>&1 && break
            sleep 1
        done
    fi
fi
exec "\${PYTHON_BIN}" "\${TEAM_DIR}/cli.py" "\$@"
EOF
chmod +x "${BIN_DIR}/bus3f-tui"

# 5. Ensure ~/.local/bin is in PATH
echo "[5/7] Configuring PATH..."
for RC in "${HOME}/.bashrc" "${HOME}/.zshrc"; do
    if [ -f "${RC}" ] && ! grep -q 'PATH=.*\.local/bin' "${RC}"; then
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> "${RC}"
    fi
done

# Optional: Windows CMD launcher when on WSL
if [ -d "/mnt/c/Users" ]; then
    WIN_USER=$(cmd.exe /c "echo %USERNAME%" 2>/dev/null | tr -d '\r\n')
    if [ -n "${WIN_USER}" ] && [ -d "/mnt/c/Users/${WIN_USER}" ]; then
        WIN_BAT="/mnt/c/Users/${WIN_USER}/bus3f-tui.bat"
        cat << 'EOF' > "${WIN_BAT}"
@echo off
wsl.exe -e bash -lic "bus3f-tui %*"
EOF
        echo "Created Windows launcher: C:\Users\\${WIN_USER}\bus3f-tui.bat"
    fi
fi

# 6. GGUF Model Setup
echo "[6/7] Checking LLM models in ~/models..."
MODEL_DIR="${HOME}/models"
mkdir -p "${MODEL_DIR}"
MODEL_FILE="${MODEL_DIR}/qwen2.5-coder-7b-instruct-q4_k_m.gguf"

if [ ! -f "${MODEL_FILE}" ] && [ -z "$(ls -A "${MODEL_DIR}"/*.gguf 2>/dev/null)" ]; then
    echo ""
    echo "No GGUF models found in ${MODEL_DIR}."
    echo "  1) Qwen2.5-Coder-7B-Instruct Q4_K_M (~4.7 GB, recommended balanced)"
    echo "  2) DeepSeek-Coder-V2-Lite-Instruct Q4_K_M (~8.9 GB, MoE deep reasoning)"
    echo "  3) Qwen2.5-Coder-3B-Instruct Q4_K_M (~2.0 GB, lightweight fast)"
    echo "  4) Developer Team 3-Pack (~15.6 GB, all three models for tiered multi-agent)"
    echo "  5) Skip (download later via /new-model)"
    URL_7B="https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct-GGUF/resolve/main/qwen2.5-coder-7b-instruct-q4_k_m.gguf"
    URL_DEEPSEEK="https://huggingface.co/bartowski/DeepSeek-Coder-V2-Lite-Instruct-GGUF/resolve/main/DeepSeek-Coder-V2-Lite-Instruct-Q4_K_M.gguf"
    URL_3B="https://huggingface.co/Qwen/Qwen2.5-Coder-3B-Instruct-GGUF/resolve/main/qwen2.5-coder-3b-instruct-q4_k_m.gguf"
    FILE_DEEPSEEK="${MODEL_DIR}/DeepSeek-Coder-V2-Lite-Instruct-Q4_K_M.gguf"
    FILE_3B="${MODEL_DIR}/qwen2.5-coder-3b-instruct-q4_k_m.gguf"

    dl_model() {
        echo "Downloading $1..."
        curl -L -C - --http1.1 --retry 5 --retry-delay 2 --progress-bar -o "$2" "$3"
    }

    read -rp "Select option [1-5, default 1]: " M_CHOICE
    M_CHOICE="${M_CHOICE:-1}"
    case "${M_CHOICE}" in
        1) dl_model "Qwen2.5-Coder-7B" "${MODEL_FILE}" "${URL_7B}" ;;
        2) dl_model "DeepSeek-Coder-V2-Lite" "${FILE_DEEPSEEK}" "${URL_DEEPSEEK}" ;;
        3) dl_model "Qwen2.5-Coder-3B" "${FILE_3B}" "${URL_3B}" ;;
        4)
            echo "Downloading Developer Team 3-Pack (~15.6 GB)..."
            dl_model "Qwen2.5-Coder-7B [1/3]" "${MODEL_FILE}" "${URL_7B}"
            dl_model "DeepSeek-Coder-V2-Lite [2/3]" "${FILE_DEEPSEEK}" "${URL_DEEPSEEK}"
            dl_model "Qwen2.5-Coder-3B [3/3]" "${FILE_3B}" "${URL_3B}"
            ;;
        *)
            echo "Skipping model download. You can run /new-model inside bus3f-tui later."
            ;;
    esac
fi

# 7. Start llama-server background daemon
echo "[7/7] Starting llama-server background service..."
if [ -z "$(ls -A "${MODEL_DIR}"/*.gguf 2>/dev/null)" ]; then
    echo "  → No models installed yet. Run 'bus3f-tui' to set up your model."
elif ! curl -s http://localhost:8080/health >/dev/null 2>&1; then
    if [ -f "${DIR}/scripts/launch_server.sh" ]; then
        nohup bash "${DIR}/scripts/launch_server.sh" >/dev/null 2>&1 &
        printf "  → Loading model into llama-server"
        SERVER_OK=false
        for i in {1..20}; do
            if curl -s http://localhost:8080/health >/dev/null 2>&1; then
                SERVER_OK=true
                break
            fi
            printf "."
            sleep 1
        done
        if [ "$SERVER_OK" = true ]; then
            echo -e "\n  ✓ llama-server ready on :8080"
        else
            echo -e "\n  ✗ llama-server failed to start. Last log lines:"
            tail -n 8 "${DIR}/logs/server.log" 2>/dev/null || true
        fi
    fi
else
    echo "  ✓ llama-server already running on :8080"
fi

echo ""
echo "✓ Setup complete! Run 'source ~/.bashrc' or open a new terminal,"
echo "  then simply type: bus3f-tui"
