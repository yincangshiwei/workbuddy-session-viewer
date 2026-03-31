from __future__ import annotations

import json
from typing import Any

from app.core.settings import MODELS_JSON_PATH


def _normalize_models(models: Any) -> list[dict[str, Any]]:
    if not isinstance(models, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in models:
        if isinstance(item, dict):
            normalized.append(item)
    return normalized


def load_models_config() -> dict[str, Any]:
    path = MODELS_JSON_PATH
    if not path.exists():
        config: dict[str, Any] = {"models": []}
        return {
            "path": str(path),
            "config": config,
            "models": config["models"],
        }

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"读取模型配置失败: {exc}") from exc

    config = raw if isinstance(raw, dict) else {"models": []}
    models = _normalize_models(config.get("models", []))
    config["models"] = models
    return {
        "path": str(path),
        "config": config,
        "models": models,
    }


def save_models_config(models: list[dict[str, Any]], config_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    path = MODELS_JSON_PATH
    normalized_models = _normalize_models(models)

    if isinstance(config_payload, dict):
        config = dict(config_payload)
    elif path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            config = existing if isinstance(existing, dict) else {}
        except Exception:
            config = {}
    else:
        config = {}

    config["models"] = normalized_models

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "path": str(path),
        "config": config,
        "models": normalized_models,
    }
