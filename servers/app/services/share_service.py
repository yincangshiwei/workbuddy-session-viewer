from __future__ import annotations

import io
import ipaddress
import os
import secrets
import shutil
import threading
import time
import zipfile
from urllib.parse import urlparse

from app.core.settings import SHARE_BASE
from app.services.export_service import build_share_html_zip


try:
    from pyngrok import conf, ngrok
except Exception:  # pragma: no cover
    conf = None
    ngrok = None


_SHARED_DIR = SHARE_BASE
_SHARE_TTL_SECONDS = max(300, int(os.getenv("WORKBUDDY_SHARE_TTL_SECONDS", "86400")))

_tunnel_lock = threading.Lock()
_tunnel_public_url: str | None = None
_tunnel_port: int | None = None


def _cleanup_expired_shares(now_ts: float) -> None:
    if not _SHARED_DIR.exists():
        return
    for child in _SHARED_DIR.iterdir():
        if not child.is_dir():
            continue
        try:
            if now_ts - child.stat().st_mtime > _SHARE_TTL_SECONDS:
                shutil.rmtree(child, ignore_errors=True)
        except Exception:
            continue


def _resolve_server_port(base_url: str) -> int:
    configured = os.getenv("WORKBUDDY_SHARE_PORT", "").strip()
    if configured.isdigit():
        return int(configured)

    parsed = urlparse(base_url)
    if parsed.port:
        return int(parsed.port)
    if parsed.scheme == "https":
        return 443
    return 80


def _is_private_or_local_host(host: str) -> bool:
    h = (host or "").strip().lower()
    if not h:
        return True
    if h in {"localhost", "127.0.0.1", "::1"}:
        return True
    try:
        ip = ipaddress.ip_address(h)
        return bool(ip.is_private or ip.is_loopback)
    except ValueError:
        return False


def _ensure_public_base_url(port: int) -> str:
    global _tunnel_public_url, _tunnel_port

    if ngrok is None:
        raise RuntimeError("未安装 pyngrok，请先安装依赖并重启服务")

    with _tunnel_lock:
        if _tunnel_public_url and _tunnel_port == port:
            return _tunnel_public_url

        token = os.getenv("NGROK_AUTHTOKEN", "").strip()
        if token:
            ngrok.set_auth_token(token)

        ngrok_path = os.getenv("NGROK_PATH", "").strip()
        pyngrok_config = None
        if conf is not None and ngrok_path:
            pyngrok_config = conf.PyngrokConfig(ngrok_path=ngrok_path)

        if _tunnel_public_url and _tunnel_port != port:
            try:
                ngrok.kill()
            except Exception:
                pass
            _tunnel_public_url = None
            _tunnel_port = None

        try:
            tunnel = ngrok.connect(addr=str(port), proto="http", bind_tls=True, pyngrok_config=pyngrok_config)
        except Exception as e:  # pragma: no cover
            raise RuntimeError(
                "无法自动创建公网隧道。可设置 WORKBUDDY_SHARE_PUBLIC_BASE_URL，或设置 NGROK_PATH/NGROK_AUTHTOKEN 后重试。"
                f" 原始错误: {e}"
            ) from e

        _tunnel_public_url = str(tunnel.public_url).rstrip("/")
        _tunnel_port = port
        return _tunnel_public_url


def _resolve_public_base_url(request_base_url: str) -> str:
    configured_public = os.getenv("WORKBUDDY_SHARE_PUBLIC_BASE_URL", "").strip().rstrip("/")
    if configured_public:
        return configured_public

    parsed = urlparse(request_base_url)
    host = parsed.hostname or ""
    if host and not _is_private_or_local_host(host):
        return request_base_url.rstrip("/")

    port = _resolve_server_port(request_base_url)
    return _ensure_public_base_url(port)


def create_chat_share(
    ids: list[str],
    request_base_url: str,
    selected_media_paths: list[str] | None = None,
    uploaded_media: list[dict[str, object]] | None = None,
) -> dict[str, str | int]:
    uniq_ids = [x for x in dict.fromkeys(ids) if x]
    if not uniq_ids:
        raise ValueError("ids required")

    now_ts = time.time()
    _SHARED_DIR.mkdir(parents=True, exist_ok=True)
    _cleanup_expired_shares(now_ts)

    blob = build_share_html_zip(
        uniq_ids,
        selected_media_paths=selected_media_paths or [],
        uploaded_media=uploaded_media or [],
    )

    share_id = f"{time.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(3)}"
    share_root = _SHARED_DIR / share_id
    share_root.mkdir(parents=True, exist_ok=False)

    with zipfile.ZipFile(io.BytesIO(blob), "r") as zf:
        zf.extractall(share_root)

    entry = share_root / "index.html"
    if not entry.exists():
        raise RuntimeError("分享页面生成失败：未找到 index.html")

    base = request_base_url.rstrip("/")
    local_path = f"/shared/{share_id}/index.html"
    local_url = f"{base}{local_path}"

    public_base = _resolve_public_base_url(request_base_url)
    public_url = f"{public_base}{local_path}"

    return {
        "shareId": share_id,
        "count": len(uniq_ids),
        "localUrl": local_url,
        "publicUrl": public_url,
    }
