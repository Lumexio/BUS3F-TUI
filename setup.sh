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
echo "[1/6] Detecting distribution & package manager..."
DISTRO="unknown"
[ -f /etc/os-release ] && . /etc/os-release && DISTRO="${ID:-unknown}"

if command -v pacman >/dev/null 2>&1 || [ "$DISTRO" = "arch" ] || [ "${ID_LIKE:-}" = "arch" ]; then
    echo "  → Arch Linux detected (${DISTRO})"
    sudo pacman -S --needed --noconfirm git curl cmake base-devel python python-pip
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
echo "[2/6] Checking llama-server binary..."
LLAMA_BIN="${HOME}/llama.cpp/build/bin/llama-server"
if [ ! -x "${LLAMA_BIN}" ] && ! command -v llama-server >/dev/null 2>&1; then
    echo "llama-server not found. Building llama.cpp..."
    [ -d "${HOME}/llama.cpp" ] || git clone --depth 1 https://github.com/ggerganov/llama.cpp "${HOME}/llama.cpp"
    CUDA_OPT=""
    command -v nvcc >/dev/null 2>&1 && CUDA_OPT="-DGGML_CUDA=ON"
    cmake -B "${HOME}/llama.cpp/build" "${HOME}/llama.cpp" ${CUDA_OPT}
    cmake --build "${HOME}/llama.cpp/build" --config Release -j "$(nproc)" --target llama-server
fi

# 3. Virtual environment setup (optional, fallback to system python)
echo "[3/6] Setting up Python venv..."
if [ ! -f "${DIR}/venv/bin/python" ]; then
    python3 -m venv "${DIR}/venv" 2>/dev/null || true
fi
if [ -x "${DIR}/venv/bin/pip" ]; then
    "${DIR}/venv/bin/pip" install --quiet prompt_toolkit pygments tree-sitter tree-sitter-c-sharp pyyaml || true
fi

# 4. Create global 'bus3f-tui' command
echo "[4/6] Installing 'bus3f-tui' launcher..."
cat << 'EOF' > "${BIN_DIR}/bus3f-tui"
#!/usr/bin/env bash
TEAM_DIR="${HOME}/agent_team"
PYTHON_BIN="${TEAM_DIR}/venv/bin/python"
if [ ! -x "${PYTHON_BIN}" ]; then
    PYTHON_BIN="$(command -v python3 || command -v python)"
fi
exec "${PYTHON_BIN}" "${TEAM_DIR}/cli.py" "$@"
EOF
chmod +x "${BIN_DIR}/bus3f-tui"

# 5. Ensure ~/.local/bin is in PATH
echo "[5/6] Configuring PATH..."
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
echo "[6/6] Checking LLM models in ~/models..."
MODEL_DIR="${HOME}/models"
mkdir -p "${MODEL_DIR}"
MODEL_FILE="${MODEL_DIR}/qwen2.5-coder-7b-instruct-q4_k_m.gguf"

if [ ! -f "${MODEL_FILE}" ] && [ -z "$(ls -A "${MODEL_DIR}"/*.gguf 2>/dev/null)" ]; then
    echo ""
    echo "No GGUF models found in ${MODEL_DIR}."
    echo "  1) Qwen2.5-Coder-7B-Instruct Q4_K_M (~4.7 GB, recommended)"
    echo "  2) Qwen2.5-Coder-3B-Instruct Q4_K_M (~2.0 GB, lightweight)"
    echo "  3) Skip (download later via /new-model)"
    read -rp "Select option [1-3, default 1]: " M_CHOICE
    M_CHOICE="${M_CHOICE:-1}"
    case "${M_CHOICE}" in
        1)
            echo "Downloading Qwen2.5-Coder-7B..."
            curl -L -C - --http1.1 --retry 5 --retry-delay 2 --progress-bar -o "${MODEL_FILE}" "https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct-GGUF/resolve/main/qwen2.5-coder-7b-instruct-q4_k_m.gguf"
            ;;
        2)
            echo "Downloading Qwen2.5-Coder-3B..."
            curl -L -C - --http1.1 --retry 5 --retry-delay 2 --progress-bar -o "${MODEL_DIR}/qwen2.5-coder-3b-instruct-q4_k_m.gguf" "https://huggingface.co/Qwen/Qwen2.5-Coder-3B-Instruct-GGUF/resolve/main/qwen2.5-coder-3b-instruct-q4_k_m.gguf"
            ;;
        *)
            echo "Skipping model download. You can run /new-model inside bus3f-tui later."
            ;;
    esac
fi

echo ""
echo "✓ Setup complete! Run 'source ~/.bashrc' or open a new terminal,"
echo "  then simply type: bus3f-tui"
