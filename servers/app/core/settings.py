from __future__ import annotations

import os
from pathlib import Path


def resolve_appdata() -> Path:
    env_appdata = os.getenv("APPDATA")
    if env_appdata:
        return Path(env_appdata)
    return Path.home() / "AppData" / "Roaming"


def resolve_localappdata() -> Path:
    env_local = os.getenv("LOCALAPPDATA")
    if env_local:
        return Path(env_local)
    return Path.home() / "AppData" / "Local"


APPDATA = resolve_appdata()
LOCALAPPDATA = resolve_localappdata()
USERPROFILE = Path(os.getenv("USERPROFILE", Path.home()))
WORKBUDDY_BASE = Path(os.getenv("WORKBUDDY_BASE", APPDATA / "WorkBuddy"))
STORAGE_BASE = WORKBUDDY_BASE / "User" / "globalStorage" / "tencent-cloud.coding-copilot"
TRANSCRIPTS_BASE = Path(
    os.getenv(
        "WORKBUDDY_TRANSCRIPTS_BASE",
        LOCALAPPDATA / "WorkBuddyExtension" / "Data",
    )
)

SESSIONS_DB = Path(os.getenv("WORKBUDDY_SESSIONS_DB", WORKBUDDY_BASE / "codebuddy-sessions.vscdb"))
TODOS_BASE = Path(os.getenv("WORKBUDDY_TODOS_BASE", STORAGE_BASE / "todos"))
FC_BASE = Path(os.getenv("WORKBUDDY_FILE_CHANGES_BASE", STORAGE_BASE / "file-changes"))
HISTORY_BASE = Path(os.getenv("WORKBUDDY_HISTORY_BASE", STORAGE_BASE / "genie-history"))
MEDIA_BASE = Path(os.getenv("WORKBUDDY_MEDIA_BASE", STORAGE_BASE / "media-index"))
SHARE_BASE = Path(os.getenv("WORKBUDDY_SHARE_BASE", LOCALAPPDATA / "WorkBuddySessionViewer" / "shared"))
MODELS_JSON_PATH = Path(os.getenv("WORKBUDDY_MODELS_JSON", USERPROFILE / ".workbuddy" / "models.json"))


