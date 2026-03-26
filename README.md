# Lab Bots (Knowledge + Python) — Step-by-step Setup

This guide sets up everything on your Linux host (CPU-only), including model downloads.

## 0) Hardware assumptions

- Linux machine with many CPUs (your 128-core host is great)
- No GPU
- ~265 GB RAM

---

## 1) Install system packages

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip docker.io docker-compose-plugin numactl
```

---

## 2) Clone repo and install Python deps

```bash
git clone <your-repo-url> lab-bots
cd lab-bots
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install "huggingface_hub[cli]"
```

---

## 3) Download chat + code models (GGUF)

Use the helper script:

```bash
CHAT_REPO='bartowski/Meta-Llama-3.1-8B-Instruct-GGUF' \
CHAT_FILE='Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf' \
CODE_REPO='bartowski/deepseek-coder-6.7b-instruct-GGUF' \
CODE_FILE='deepseek-coder-6.7b-instruct-Q4_K_M.gguf' \
bash scripts/download_models.sh
```

This creates:

- `models/chat/<chat-model>.gguf`
- `models/code/<code-model>.gguf`

---

## 4) Start Qdrant

```bash
docker compose up -d qdrant
```

---

## 5) Start two llama.cpp servers (one per bot)

### 5a) Chat model server on port 8081

```bash
MODEL_PATH=models/chat/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf \
PORT=8081 THREADS=96 NUMA_NODE=0 \
bash scripts/run_llama_server.sh
```

### 5b) Code model server on port 8082

Open another terminal:

```bash
MODEL_PATH=models/code/deepseek-coder-6.7b-instruct-Q4_K_M.gguf \
PORT=8082 THREADS=96 NUMA_NODE=0 \
bash scripts/run_llama_server.sh
```

---

## 6) Prepare env vars

Copy and edit:

```bash
cp .env.example .env
```

Important values:

- `CHAT_LLM_URL=http://127.0.0.1:8081/v1/chat/completions`
- `CODE_LLM_URL=http://127.0.0.1:8082/v1/chat/completions`
- `CHAT_LLM_MODEL_NAME=llama-3.1-8b-instruct`
- `CODE_LLM_MODEL_NAME=deepseek-coder-6.7b-instruct`
- `DISCORD_TOKEN=<knowledge-bot-token>`
- `PY_BOT_TOKEN=<python-bot-token>`

Load env:

```bash
set -a
source .env
set +a
```

---

## 7) Ingest your knowledge base

Put docs into `data/knowledge/` (`.md`, `.txt`, `.pdf`) then run:

```bash
python app/ingest.py
```

---

## 8) Start bots

### Knowledge bot

```bash
python app/discord_bot.py
```

### Python helper bot

In another terminal (same env loaded):

```bash
python app/python_helper_bot.py
```

---

## 9) Quick Discord usage

### Knowledge bot
- `!ask <question>`
- `!memory`
- `!reset`

### Python bot
- `!py print(2+2)`
- `!autopy build a quick plot of sin(x) and save result.png`

### CSV analysis
Attach a CSV file and run:

```text
!py import pandas as pd

df = pd.read_csv("data.csv")
print(df.describe())
```

Or auto mode:

```text
!autopy analyze the attached csv and plot Voltage vs Time into result.png
```

