#!/usr/bin/env bash
set -euo pipefail

# Example usage:
# CHAT_REPO='bartowski/Meta-Llama-3.1-8B-Instruct-GGUF' CHAT_FILE='Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf' \
# CODE_REPO='bartowski/deepseek-coder-6.7b-instruct-GGUF' CODE_FILE='deepseek-coder-6.7b-instruct-Q4_K_M.gguf' \
# bash scripts/download_models.sh

MODELS_DIR="${MODELS_DIR:-models}"
CHAT_REPO="${CHAT_REPO:-}"
CHAT_FILE="${CHAT_FILE:-}"
CODE_REPO="${CODE_REPO:-}"
CODE_FILE="${CODE_FILE:-}"

if [[ -z "$CHAT_REPO" || -z "$CHAT_FILE" || -z "$CODE_REPO" || -z "$CODE_FILE" ]]; then
  echo "Please set CHAT_REPO, CHAT_FILE, CODE_REPO, CODE_FILE"
  exit 1
fi

mkdir -p "$MODELS_DIR/chat" "$MODELS_DIR/code"

if ! command -v huggingface-cli >/dev/null 2>&1; then
  echo "huggingface-cli not found. Install with: pip install huggingface_hub[cli]"
  exit 1
fi

echo "Downloading chat model..."
huggingface-cli download "$CHAT_REPO" "$CHAT_FILE" --local-dir "$MODELS_DIR/chat"

echo "Downloading code model..."
huggingface-cli download "$CODE_REPO" "$CODE_FILE" --local-dir "$MODELS_DIR/code"

echo "Done."
echo "Chat model: $MODELS_DIR/chat/$CHAT_FILE"
echo "Code model: $MODELS_DIR/code/$CODE_FILE"
