#!/usr/bin/env bash
set -euo pipefail

MODEL_PATH="${MODEL_PATH:-models/model.gguf}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8081}"
THREADS="${THREADS:-112}"
CTX="${CTX:-8192}"
BATCH="${BATCH:-1024}"
NUMA_NODE="${NUMA_NODE:-0}"
LLAMA_SERVER_BIN="${LLAMA_SERVER_BIN:-./llama.cpp/build/bin/llama-server}"

if [[ ! -f "$MODEL_PATH" ]]; then
  echo "Model not found at $MODEL_PATH"
  exit 1
fi

if [[ ! -x "$LLAMA_SERVER_BIN" ]]; then
  echo "llama-server binary not found/executable at $LLAMA_SERVER_BIN"
  echo "Build llama.cpp first, e.g.:"
  echo "  git clone https://github.com/ggerganov/llama.cpp"
  echo "  cmake -S llama.cpp -B llama.cpp/build -DGGML_OPENBLAS=ON"
  echo "  cmake --build llama.cpp/build -j"
  exit 1
fi

echo "Starting llama-server on ${HOST}:${PORT} with ${THREADS} threads on NUMA node ${NUMA_NODE}"
exec numactl --cpunodebind="$NUMA_NODE" --membind="$NUMA_NODE" \
  "$LLAMA_SERVER_BIN" \
  --model "$MODEL_PATH" \
  --host "$HOST" \
  --port "$PORT" \
  --threads "$THREADS" \
  --ctx-size "$CTX" \
  --batch-size "$BATCH" \
  --n-gpu-layers 0
