from __future__ import annotations

import os

from dotenv import load_dotenv
import sqlite3
from pathlib import Path

import discord

from app.rag_engine import RagEngine

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
CORPUS_MODE = os.getenv("DISCORD_CORPUS", "all")
TOPIC_MODE = os.getenv("DISCORD_TOPIC", "")
HISTORY_TURNS = int(os.getenv("DISCORD_HISTORY_TURNS", "8"))

ALLOWED_USER_IDS = {
    int(x.strip())
    for x in os.getenv("LAB_USER_IDS", "").split(",")
    if x.strip().isdigit()
}
ALLOWED_CHANNEL_IDS = {
    int(x.strip())
    for x in os.getenv("LAB_CHANNEL_IDS", "").split(",")
    if x.strip().isdigit()
}

DB_PATH = Path(os.getenv("DISCORD_HISTORY_DB", "data/discord_history.db"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
engine = RagEngine()


def init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS history (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              channel_id TEXT NOT NULL,
              role TEXT NOT NULL,
              content TEXT NOT NULL,
              created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


def add_history(channel_id: str, role: str, content: str) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO history (channel_id, role, content) VALUES (?, ?, ?)",
            (channel_id, role, content),
        )


def get_recent_history(channel_id: str, turns: int) -> list[tuple[str, str]]:
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT role, content
            FROM history
            WHERE channel_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (channel_id, turns * 2),
        ).fetchall()
    return list(reversed(rows))


def clear_history(channel_id: str) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM history WHERE channel_id = ?", (channel_id,))


def count_history(channel_id: str) -> int:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM history WHERE channel_id = ?",
            (channel_id,),
        ).fetchone()
    return int(row[0]) if row else 0


def is_allowed(user_id: int, channel_id: int) -> bool:
    user_ok = not ALLOWED_USER_IDS or user_id in ALLOWED_USER_IDS
    channel_ok = not ALLOWED_CHANNEL_IDS or channel_id in ALLOWED_CHANNEL_IDS
    return user_ok and channel_ok


async def run_rag(question: str) -> tuple[str, list[str]]:
    context, sources = engine.retrieve_context(question=question, topic=TOPIC_MODE or None, corpus=CORPUS_MODE)
    if not context:
        return (
            "I don't have enough indexed information for that yet. "
            "Please add/update documents and re-run ingestion.",
            [],
        )

    answer = await engine.generate_answer(question=question, context=context, corpus=CORPUS_MODE)
    return answer, sorted(set(sources))


intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)


@client.event
async def on_ready() -> None:
    print(f"Knowledge bot online as {client.user}")


@client.event
async def on_message(message: discord.Message) -> None:
    if message.author.bot:
        return

    if not isinstance(message.channel, (discord.TextChannel, discord.Thread, discord.DMChannel)):
        return

    if not is_allowed(message.author.id, message.channel.id):
        return

    text = (message.content or "").strip()
    if not text:
        return

    channel_id = str(message.channel.id)

    if text.lower().startswith("!reset"):
        clear_history(channel_id)
        await message.reply("Channel memory has been cleared.")
        return

    if text.lower().startswith("!memory"):
        total = count_history(channel_id)
        await message.reply(f"Stored messages in this channel session: {total}")
        return

    if not text.lower().startswith("!ask"):
        return

    user_question = text[4:].strip()
    if not user_question:
        await message.reply("Usage: `!ask <your question>`")
        return

    author = getattr(message.author, "display_name", str(message.author))
    tagged_question = f"{author}: {user_question}"

    history = get_recent_history(channel_id, HISTORY_TURNS)
    history_text = "\n".join(f"{role.upper()}: {content}" for role, content in history)
    full_question = (
        f"Conversation history (same channel, shared among members):\n{history_text}\n\n"
        f"New user question:\n{tagged_question}"
    )

    async with message.channel.typing():
        try:
            answer, sources = await run_rag(full_question)
        except Exception as exc:  # noqa: BLE001
            await message.reply(f"Chat service error: {exc}")
            return

    add_history(channel_id, "user", tagged_question)
    add_history(channel_id, "assistant", answer)

    source_text = f"\n\nSources: {', '.join(sources)}" if sources else ""
    await message.reply(answer[:1800] + source_text[:150])


def main() -> None:
    if not DISCORD_TOKEN:
        raise RuntimeError("Missing DISCORD_TOKEN env var")
    init_db()
    client.run(DISCORD_TOKEN)


if __name__ == "__main__":
    main()
