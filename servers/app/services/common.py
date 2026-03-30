from __future__ import annotations

import base64
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.settings import TRANSCRIPTS_BASE


def ts_to_text(ts: int | float | None) -> str:
    if not ts:
        return ""
    return datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M")


def safe_json(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def diff_html(diff_text: str) -> str:
    if not diff_text:
        return ""
    out: list[str] = []
    lines = diff_text.split("\n")
    for line in lines[:200]:
        esc = (
            line.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )
        if line.startswith("+++") or line.startswith("---"):
            out.append(f'<span style="color:#63b3ed;font-weight:600">{esc}</span>')
        elif line.startswith("+"):
            out.append(f'<span style="color:#68d391">{esc}</span>')
        elif line.startswith("-"):
            out.append(f'<span style="color:#fc8181">{esc}</span>')
        elif line.startswith("@@"):
            out.append(f'<span style="color:#f6ad55">{esc}</span>')
        else:
            out.append(f'<span style="color:#a0aec0">{esc}</span>')
    if len(lines) > 200:
        out.append(f'<span style="color:#718096">... 还有 {len(lines)-200} 行 ...</span>')
    return "\n".join(out)


def decode_history_dir_name(name: str) -> str:
    try:
        b64 = name.replace("_", "/").replace("-", "+")
        while len(b64) % 4:
            b64 += "="
        return base64.b64decode(b64).decode("utf-8", errors="replace").rstrip("\x00").rstrip("?")
    except Exception:
        return ""


def resolve_transcript_index(cid: str) -> Path | None:
    if not cid or not TRANSCRIPTS_BASE.exists():
        return None

    candidates: list[tuple[int, Path]] = []
    try:
        for p in TRANSCRIPTS_BASE.rglob("index.json"):
            if p.parent.name != cid:
                continue

            s = str(p).replace("\\", "/").lower()
            score = 0
            if "/history/" in s:
                score += 20
            if "/check-point/" in s or "/checkpoint/" in s:
                score -= 10

            msg_dir = p.parent / "messages"
            if msg_dir.is_dir():
                score += 10
                try:
                    if next(msg_dir.glob("*.json"), None):
                        score += 5
                except Exception:
                    pass

            candidates.append((score, p))
    except Exception:
        return None

    if not candidates:
        return None

    candidates.sort(key=lambda x: (x[0], -len(str(x[1]))), reverse=True)
    return candidates[0][1]


def parse_message_content(blocks: list[dict[str, Any]]) -> dict[str, Any]:
    chunks: list[str] = []
    tool_events: list[dict[str, Any]] = []

    for block in blocks:
        btype = str(block.get("type", ""))
        if btype == "text":
            text = str(block.get("text", "")).strip()
            if text:
                chunks.append(text)
            continue

        if btype == "tool-call":
            tool_events.append(
                {
                    "type": btype,
                    "toolName": str(block.get("toolName", "")),
                    "toolCallId": str(block.get("toolCallId", "")),
                    "args": block.get("args"),
                }
            )
            continue

        if btype == "tool-result":
            tool_events.append(
                {
                    "type": btype,
                    "toolName": str(block.get("toolName", "")),
                    "toolCallId": str(block.get("toolCallId", "")),
                    "result": block.get("result"),
                    "isError": bool(block.get("isError", False)),
                }
            )
            continue

        if btype:
            chunks.append(f"[{btype}]")

    return {
        "text": "\n\n".join(x for x in chunks if x).strip(),
        "toolEvents": tool_events,
    }


def escape_html(s: str) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )
