from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

import discord
import httpx

PY_BOT_TOKEN = os.getenv("PY_BOT_TOKEN", "")
PY_TIMEOUT_SECONDS = int(os.getenv("PY_TIMEOUT_SECONDS", "20"))
AUTOPY_MAX_ITERS = int(os.getenv("AUTOPY_MAX_ITERS", "3"))
LLM_URL = os.getenv("CODE_LLM_URL", os.getenv("LLM_URL", "http://127.0.0.1:8081/v1/chat/completions"))
LLM_MODEL_NAME = os.getenv("CODE_LLM_MODEL_NAME", os.getenv("LLM_MODEL_NAME", "local-gguf"))

ALLOWED_USER_IDS = {
    int(x.strip())
    for x in os.getenv("PYLAB_USER_IDS", "").split(",")
    if x.strip().isdigit()
}
ALLOWED_CHANNEL_IDS = {
    int(x.strip())
    for x in os.getenv("PYLAB_CHANNEL_IDS", "").split(",")
    if x.strip().isdigit()
}


def is_allowed(user_id: int, channel_id: int) -> bool:
    user_ok = not ALLOWED_USER_IDS or user_id in ALLOWED_USER_IDS
    channel_ok = not ALLOWED_CHANNEL_IDS or channel_id in ALLOWED_CHANNEL_IDS
    return user_ok and channel_ok


def extract_code(text: str) -> str:
    raw = text[3:].strip()
    if raw.startswith("```") and raw.endswith("```"):
        raw = raw[3:-3].strip()
        if raw.lower().startswith("python"):
            raw = raw[6:].lstrip("\n").strip()
    return raw


async def extract_csv_attachment(message: discord.Message) -> tuple[bytes | None, str | None]:
    if not message.attachments:
        return None, None

    for a in message.attachments:
        if (a.filename or "").lower().endswith(".csv"):
            content = await a.read()
            return content, "data.csv"

    return None, None


def run_python_snippet(code: str, csv_bytes: bytes | None = None, csv_name: str | None = None) -> tuple[int, str, Path | None]:
    with tempfile.TemporaryDirectory(prefix="lab_pybot_") as tmpdir:
        workdir = Path(tmpdir)

        if csv_bytes is not None and csv_name:
            (workdir / csv_name).write_bytes(csv_bytes)

        script_path = workdir / "snippet.py"
        script_path.write_text(
            """
import matplotlib
matplotlib.use('Agg')

# If a CSV attachment was provided, it is available as './data.csv'.
# User code starts below
"""
            + code,
            encoding="utf-8",
        )

        proc = subprocess.run(
            ["python3", str(script_path)],
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=PY_TIMEOUT_SECONDS,
        )

        out = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
        out = out.strip() or "(no text output)"

        png_files = sorted(workdir.glob("*.png"))
        if png_files:
            export = Path(tempfile.gettempdir()) / f"lab_pybot_{os.getpid()}_result.png"
            export.write_bytes(png_files[0].read_bytes())
            return proc.returncode, out, export

        return proc.returncode, out, None


async def generate_code(
    prompt: str,
    previous_code: str = "",
    last_error: str = "",
    csv_available: bool = False,
) -> str:
    system = (
        "You are a precise Python coding assistant. Return ONLY runnable Python code, no markdown. "
        "Prefer short scripts. If plotting is requested, save plot as 'result.png'."
    )
    data_hint = "CSV file is available at './data.csv'. Use pandas read_csv if needed." if csv_available else ""
    user = (
        f"Task:\n{prompt}\n\n"
        f"{data_hint}\n\n"
        f"Previous code (may be empty):\n{previous_code}\n\n"
        f"Last runtime error/output (may be empty):\n{last_error}\n\n"
        "Now provide improved Python code only."
    )
    payload = {
        "model": LLM_MODEL_NAME,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
        "max_tokens": 900,
    }

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(LLM_URL, json=payload)
        resp.raise_for_status()
        data = resp.json()

    text = data["choices"][0]["message"]["content"].strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("python"):
            text = text[6:].lstrip("\n")
    return text.strip()


async def autopy_loop(task_prompt: str, csv_bytes: bytes | None = None) -> tuple[str, int, int, str, Path | None]:
    code = ""
    last_output = ""
    image_path: Path | None = None
    rc = 1

    for i in range(1, AUTOPY_MAX_ITERS + 1):
        code = await generate_code(
            task_prompt,
            previous_code=code,
            last_error=last_output,
            csv_available=csv_bytes is not None,
        )
        try:
            rc, last_output, image_path = run_python_snippet(code, csv_bytes=csv_bytes, csv_name="data.csv")
        except subprocess.TimeoutExpired:
            rc = 124
            last_output = f"Execution timed out after {PY_TIMEOUT_SECONDS}s"
            image_path = None

        if rc == 0:
            return code, i, rc, last_output, image_path

    return code, AUTOPY_MAX_ITERS, rc, last_output, image_path


intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)


@client.event
async def on_ready() -> None:
    print(f"Python helper bot online as {client.user}")


@client.event
async def on_message(message: discord.Message) -> None:
    if message.author.bot:
        return

    if not isinstance(message.channel, (discord.TextChannel, discord.Thread, discord.DMChannel)):
        return

    if not is_allowed(message.author.id, message.channel.id):
        return

    text = (message.content or "").strip()
    csv_bytes, csv_name = await extract_csv_attachment(message)

    if text.lower().startswith("!autopy"):
        prompt = text[7:].strip()
        if not prompt:
            await message.reply("Usage: `!autopy <task description>` (optionally attach a CSV file)")
            return

        async with message.channel.typing():
            try:
                code, iterations, rc, output, image_path = await autopy_loop(prompt, csv_bytes=csv_bytes)
            except Exception as exc:  # noqa: BLE001
                await message.reply(f"Auto coding error: {exc}")
                return

        header = f"AutoPy finished in {iterations} iteration(s), return code={rc}."
        if csv_bytes is not None:
            header += " CSV attachment detected as ./data.csv."
        code_preview = f"```python\n{code[:1200]}\n```"
        out_preview = f"```\n{output[:1200]}\n```"
        reply_text = f"{header}\n\nGenerated code:\n{code_preview}\n\nOutput:\n{out_preview}"
        if image_path and image_path.exists():
            await message.reply(reply_text[:1800], file=discord.File(str(image_path), filename="result.png"))
        else:
            await message.reply(reply_text[:1900])
        return

    if not text.lower().startswith("!py"):
        return

    code = extract_code(text)
    if not code:
        await message.reply(
            "Usage: `!py <python code>` or fenced block.\n"
            "You may attach one CSV; it will be available as `data.csv`.\n"
            "Example: `!py import pandas as pd; print(pd.read_csv(\"data.csv\").head())`\n"
            "Auto mode: `!autopy <what you want>`"
        )
        return

    async with message.channel.typing():
        try:
            rc, output, image_path = run_python_snippet(code, csv_bytes=csv_bytes, csv_name=csv_name)
        except subprocess.TimeoutExpired:
            await message.reply(f"Execution timed out after {PY_TIMEOUT_SECONDS}s")
            return
        except Exception as exc:  # noqa: BLE001
            await message.reply(f"Execution error: {exc}")
            return

    prefix = f"exit_code={rc}\n"
    if csv_bytes is not None:
        prefix += "csv=data.csv\n"
    reply_text = f"```\n{prefix}{output[:1650]}\n```"
    if image_path and image_path.exists():
        await message.reply(reply_text, file=discord.File(str(image_path), filename="result.png"))
    else:
        await message.reply(reply_text)


def main() -> None:
    if not PY_BOT_TOKEN:
        raise RuntimeError("Missing PY_BOT_TOKEN env var")
    client.run(PY_BOT_TOKEN)


if __name__ == "__main__":
    main()
