from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException

from app.services.common import parse_message_content, resolve_transcript_index, safe_json, ts_to_text


def _extract_model_meta(extra_obj: dict[str, Any]) -> dict[str, str]:
    model_id = str(extra_obj.get("modelId", "") or "")
    model_name = str(extra_obj.get("modelName", "") or "")
    mode = ""

    source_blocks = extra_obj.get("sourceContentBlocks", [])
    if isinstance(source_blocks, list):
        for block in source_blocks:
            if not isinstance(block, dict):
                continue
            meta = block.get("_meta", {})
            if not isinstance(meta, dict):
                continue
            ai_meta = meta.get("codebuddy.ai", {})
            if not isinstance(ai_meta, dict):
                continue
            if not model_id:
                model_id = str(ai_meta.get("model", "") or "")
            if not mode:
                mode = str(ai_meta.get("mode", "") or "")
            if model_id and mode:
                break

    return {
        "requestId": str(extra_obj.get("requestId", "") or ""),
        "modelId": model_id,
        "modelName": model_name,
        "mode": mode,
    }


def load_conversation_chat(cid: str) -> dict[str, Any]:
    idx = resolve_transcript_index(cid)
    if not idx:
        raise HTTPException(status_code=404, detail="chat transcript not found")

    data = safe_json(idx)
    if not data:
        raise HTTPException(status_code=500, detail="invalid transcript index")

    msg_dir = idx.parent / "messages"
    out_messages: list[dict[str, Any]] = []
    for meta in data.get("messages", []):
        mid = str(meta.get("id", ""))
        role = str(meta.get("role", ""))
        mtype = str(meta.get("type", ""))
        msg_file = msg_dir / f"{mid}.json" if mid else None
        created_at_ts = 0
        if msg_file and msg_file.exists():
            try:
                created_at_ts = int(msg_file.stat().st_ctime * 1000)
            except Exception:
                created_at_ts = 0

        item: dict[str, Any] = {
            "id": mid,
            "role": role,
            "type": mtype,
            "isComplete": bool(meta.get("isComplete", False)),
            "text": "",
            "toolEvents": [],
            "createdAtTs": created_at_ts,
            "createdAt": ts_to_text(created_at_ts),
            "messagePath": str(msg_file) if msg_file else "",
            "raw": None,
            "requestId": "",
            "modelId": "",
            "modelName": "",
            "mode": "",
        }

        if mid and msg_file:
            raw = safe_json(msg_file)
            if raw:
                extra_raw = raw.get("extra")
                extra_obj: dict[str, Any] = {}
                if isinstance(extra_raw, str) and extra_raw.strip():
                    try:
                        loaded = json.loads(extra_raw)
                        if isinstance(loaded, dict):
                            extra_obj = loaded
                    except Exception:
                        extra_obj = {}
                elif isinstance(extra_raw, dict):
                    extra_obj = extra_raw

                if extra_obj:
                    item.update(_extract_model_meta(extra_obj))

            if raw and isinstance(raw.get("message"), str):
                try:
                    msg_obj = json.loads(raw["message"])
                    item["raw"] = msg_obj
                    content = msg_obj.get("content", [])
                    if isinstance(content, list):
                        parsed = parse_message_content(content)
                        item["text"] = parsed.get("text", "")
                        item["toolEvents"] = parsed.get("toolEvents", [])
                except Exception:
                    item["text"] = raw["message"]


        out_messages.append(item)

    return {
        "conversationId": cid,
        "indexPath": str(idx),
        "messageCount": len(out_messages),
        "messages": out_messages,
        "requests": data.get("requests", []),
    }
