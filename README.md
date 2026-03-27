# Lab Bots (Knowledge + Python) — Step-by-step Setup

This guide is tuned for your setup and issues encountered.

## 0) Prerequisites and versions

- **Python:** use modern Python (recommended 3.11–3.13).
- If old Conda Python (e.g. 3.8.x) breaks deps, remove/avoid it and use system Python.
- **Docker:** if `docker-compose-plugin` install fails but Docker already works, you can continue with your existing Docker/Compose setup.

Check:

```bash
python3 --version
docker --version
docker compose version
```

---

## 1) Install system packages (if needed)

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip docker.io docker-compose-plugin numactl
```

If docker-compose-plugin is unavailable on your distro, keep using your existing Docker installation if `docker compose` works.

---

## 2) Clone repo and create environment

```bash
git clone <your-repo-url> lab-bots
cd lab-bots
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install "huggingface_hub[cli]"
```

> The app now also calls `load_dotenv()` internally, so `.env` values are auto-loaded.

---

## 3) Hugging Face login (token)

You need an HF account + token for downloads:

```bash
huggingface-cli login
```

Paste your free token when prompted.

---

## 4) Download chat + code models (GGUF)

```bash
CHAT_REPO='bartowski/Meta-Llama-3.1-8B-Instruct-GGUF' \
CHAT_FILE='Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf' \
CODE_REPO='bartowski/deepseek-coder-6.7b-instruct-GGUF' \
CODE_FILE='deepseek-coder-6.7b-instruct-Q4_K_M.gguf' \
bash scripts/download_models.sh
```

---

## 5) Start Qdrant

```bash
docker compose up -d qdrant
docker ps | grep qdrant
```

If you already had Qdrant running, this is still safe and helps ensure consistent container config.

---

## 6) Start llama servers (thread guidance included)

### Thread guidance for 128 CPUs

- If **only one model** runs most of the time: use `THREADS=96~112`.
- If **both models** run at once: split threads, e.g. `THREADS=72` each.
- Keep some headroom for OS + embeddings + bots.

### Chat model server (8081)

```bash
MODEL_PATH=models/chat/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf \
PORT=8081 THREADS=104 NUMA_NODE=0 \
bash scripts/run_llama_server.sh
```

### Code model server (8082)

Open another terminal:

```bash
MODEL_PATH=models/code/deepseek-coder-6.7b-instruct-Q4_K_M.gguf \
PORT=8082 THREADS=72 NUMA_NODE=0 \
bash scripts/run_llama_server.sh
```

(Adjust up/down based on observed latency.)

---

## 7) Configure `.env`

```bash
cp .env.example .env
```

Important vars:

- `CHAT_LLM_URL=http://127.0.0.1:8081/v1/chat/completions`
- `CODE_LLM_URL=http://127.0.0.1:8082/v1/chat/completions`
- `CHAT_LLM_MODEL_NAME=llama-3.1-8b-instruct`
- `CODE_LLM_MODEL_NAME=deepseek-coder-6.7b-instruct`
- `DISCORD_TOKEN=<knowledge-bot-token>`
- `PY_BOT_TOKEN=<python-bot-token>`

No manual `source .env` needed if you run bots from repo root (dotenv is loaded in code).

---

## 8) Ingest knowledge

```bash
python -m app.ingest
```

---

## 9) Start bots (module mode)

Use module mode (recommended):

```bash
python -m app.discord_bot
python -m app.python_helper_bot
```

---

## 10) Quick Discord commands

### Knowledge bot
- `!ask <question>`
- `!memory`
- `!reset`

### Python bot
- `!py print(2+2)`
- `!autopy build a quick plot of sin(x) and save result.png`

### CSV analysis
Attach CSV and run:

```text
!py import pandas as pd

df = pd.read_csv("data.csv")
print(df.describe())
```

After the first upload in a channel, CSV is cached for that channel, so you can ask follow-up plotting/analysis commands without re-uploading.

To clear cached CSV in that channel:

```text
!csvclear
```


---

## Quick restart sequence (daily normal start)

Use this after reboot / after stopping services (no reinstall needed):

```bash
cd lab-bots
source .venv/bin/activate

docker compose up -d qdrant

# Terminal A: chat model
MODEL_PATH=models/chat/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf PORT=8081 THREADS=104 NUMA_NODE=0 bash scripts/run_llama_server.sh

# Terminal B: code model
MODEL_PATH=models/code/deepseek-coder-6.7b-instruct-Q4_K_M.gguf PORT=8082 THREADS=72 NUMA_NODE=0 bash scripts/run_llama_server.sh

# Terminal C: knowledge bot
python -m app.discord_bot

# Terminal D: python bot
python -m app.python_helper_bot
```

If you added/changed docs, run ingestion once before starting the knowledge bot:

```bash
python -m app.ingest
```

---

## Ingestion behavior (important)

You do **not** need a full rebuild every time.

Current default is **incremental upsert**:

- re-ingesting existing documents updates/replaces matching chunks by stable IDs
- new documents are added
- this is efficient for normal updates

If you want a clean rebuild (e.g., many deletions/renames), set:

```bash
export FULL_REBUILD=true
python -m app.ingest
```

Then set it back to false (or unset) for regular use.

---

## Do you need summary/index notes for every document?

Not strictly required.

- You can upload raw PDFs directly and they will still be indexed.
- But summaries/index notes are **recommended** for better answer quality and faster retrieval grounding.

Best practice:

- keep raw PDFs for full detail
- add short companion notes for key docs (title, year, topic, key findings, limits)

This helps the bot answer quickly and consistently, especially for broad questions.
