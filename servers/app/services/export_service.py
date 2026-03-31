from __future__ import annotations

import base64
import io
import json
import re
import sqlite3
import time
import zipfile
from pathlib import Path
from typing import Any

from app.core.settings import FC_BASE, MEDIA_BASE, SESSIONS_DB, TODOS_BASE
from app.services.chat_service import load_conversation_chat
from app.services.common import escape_html, resolve_transcript_index, safe_json, ts_to_text


def load_session_values(ids: list[str]) -> dict[str, dict[str, Any]]:
    if not ids or not SESSIONS_DB.exists():
        return {}

    out: dict[str, dict[str, Any]] = {}
    conn = sqlite3.connect(f"file:{SESSIONS_DB}?mode=ro", uri=True)
    cur = conn.cursor()
    for cid in ids:
        key = f"session:{cid}"
        cur.execute("SELECT value FROM ItemTable WHERE key=?", (key,))
        row = cur.fetchone()
        if not row:
            continue
        try:
            obj = json.loads(row[0])
            if isinstance(obj, dict):
                out[cid] = obj
        except Exception:
            continue
    conn.close()
    return out


def collect_media_records(cid: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not MEDIA_BASE.exists():
        return records
    for mf in MEDIA_BASE.glob("*.json"):
        data = safe_json(mf)
        if not data:
            continue
        for rec in data.get("records", {}).values():
            if rec.get("sessionId") == cid:
                records.append(rec)
    return records


def collect_workspace_files(cwd: str) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    root = Path(cwd or "")
    if not root.exists() or not root.is_dir():
        return files

    for file_path in root.rglob("*"):
        if not file_path.is_file() or file_path.is_symlink():
            continue
        rel = str(file_path.relative_to(root)).replace("\\", "/")
        size = 0
        try:
            size = file_path.stat().st_size
        except Exception:
            size = 0
        files.append(
            {
                "name": file_path.name,
                "relativePath": rel,
                "localPath": str(file_path),
                "size": size,
            }
        )

    files.sort(key=lambda x: str(x.get("relativePath", "")).lower())
    return files


def build_export_zip(ids: list[str]) -> bytes:

    uniq_ids = [x for x in dict.fromkeys(ids) if x]
    session_map = load_session_values(uniq_ids)

    buf = io.BytesIO()
    exported: list[dict[str, Any]] = []

    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for cid in uniq_ids:
            session = session_map.get(cid)
            if not session:
                continue

            root = f"sessions/{cid}"
            zf.writestr(
                f"{root}/session.json",
                json.dumps(session, ensure_ascii=False, indent=2),
            )

            todo_file = TODOS_BASE / f"{cid}.json"
            if todo_file.exists():
                zf.writestr(f"{root}/todos.json", todo_file.read_text(encoding="utf-8"))

            fc_dir = FC_BASE / cid
            if fc_dir.is_dir():
                for fc in fc_dir.glob("*.json"):
                    zf.writestr(
                        f"{root}/file-changes/{fc.name}",
                        fc.read_text(encoding="utf-8"),
                    )

            media_records = collect_media_records(cid)
            if media_records:
                zf.writestr(
                    f"{root}/media-records.json",
                    json.dumps(media_records, ensure_ascii=False, indent=2),
                )

            idx = resolve_transcript_index(cid)
            transcript_ok = False
            if idx and idx.exists():
                transcript_ok = True
                zf.writestr(
                    f"{root}/transcript/index.json",
                    idx.read_text(encoding="utf-8"),
                )
                msg_dir = idx.parent / "messages"
                if msg_dir.is_dir():
                    for mf in msg_dir.glob("*.json"):
                        zf.writestr(
                            f"{root}/transcript/messages/{mf.name}",
                            mf.read_text(encoding="utf-8"),
                        )

            exported.append(
                {
                    "conversationId": cid,
                    "title": session.get("title", ""),
                    "transcriptIncluded": transcript_ok,
                }
            )

        zf.writestr(
            "manifest.json",
            json.dumps(
                {
                    "format": "workbuddy-session-export-v1",
                    "exportedAt": int(time.time() * 1000),
                    "count": len(exported),
                    "sessions": exported,
                },
                ensure_ascii=False,
                indent=2,
            ),
        )

    return buf.getvalue()


def _extract_user_query(text: str) -> str:
    if not text:
        return ""
    m = re.search(r"<user_query>\s*([\s\S]*?)\s*</user_query>", text, flags=re.IGNORECASE)
    return (m.group(1).strip() if m else "")


def _normalize_message_text(text: str) -> str:
    return (text or "").strip()


def _build_basic_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    basic: list[dict[str, Any]] = []
    for m in messages:
        role = str(m.get("role", ""))
        if role not in {"user", "assistant"}:
            continue
        text = _normalize_message_text(str(m.get("text", "")))
        if not text:
            continue
        display_text = _extract_user_query(text) if role == "user" else text
        basic.append(
            {
                "id": str(m.get("id", "")),
                "role": role,
                "createdAt": str(m.get("createdAt", "") or ""),
                "text": display_text or text,
                "rawText": text,
                "toolEvents": m.get("toolEvents", []),
                "modelId": str(m.get("modelId", "") or ""),
                "modelName": str(m.get("modelName", "") or ""),
                "mode": str(m.get("mode", "") or ""),
            }
        )
    return basic


def _slugify(value: str, fallback: str) -> str:
    text = (value or "").strip() or fallback
    text = re.sub(r"[\\/:*?\"<>|]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        text = fallback
    safe = "".join(c if c.isalnum() or c in {"-", "_", " "} else "_" for c in text).strip()
    safe = re.sub(r"\s+", "-", safe)
    return (safe[:64] or fallback)


def _to_file_uri(path_text: str) -> str:
    if not path_text:
        return ""
    try:
        p = Path(path_text)
        if not p.is_absolute():
            p = p.resolve()
        return p.as_uri()
    except Exception:
        return ""


def _json_to_b64(data: Any) -> str:
    payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
    return base64.b64encode(payload).decode("ascii")


def generate_export_index_html(sessions: list[dict[str, Any]], exported_at: str) -> str:
    total_messages = sum(s.get("messageCount", 0) for s in sessions)
    total_media = sum(s.get("mediaCount", 0) for s in sessions)

    cards = []
    for idx, item in enumerate(sessions, 1):
        cards.append(
            f"""
      <a class="session-card" href="{escape_html(item.get("entry", ""))}" data-title="{escape_html(item.get("title", "").lower())}" data-messages="{item.get("messageCount", 0)}">
        <div class="card-header">
          <span class="card-index">#{idx}</span>
          <span class="card-badge">{item.get("messageCount", 0)} 条</span>
        </div>
        <div class="session-title">{escape_html(item.get("title") or item.get("conversationId", ""))}</div>
        <div class="session-meta">
          <span class="meta-item">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>
            {item.get("messageCount", 0)}
          </span>
          <span class="meta-item">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12"></path></svg>
            {item.get("mediaCount", 0)}
          </span>
        </div>
        <div class="session-id">{escape_html(item.get("conversationId", ""))}</div>
      </a>
"""
        )

    body = "".join(cards) if cards else ""
    empty_html = """<div class="empty">
          <svg class="empty-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
            <line x1="9" y1="9" x2="15" y2="15"></line>
            <line x1="15" y1="9" x2="9" y2="15"></line>
          </svg>
          <div class="empty-title">暂无导出内容</div>
          <div class="empty-text">未找到任何会话记录</div>
        </div>"""

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>WorkBuddy 对话导出</title>
  <style>
    :root {{
      --bg:#070b14; --bg-elevated:#0d1220; --panel:#111827; --panel-hover:#1a2332; --line:#1f2937; --line-light:#374151;
      --text:#f3f4f6; --text-secondary:#d1d5db; --muted:#9ca3af;
      --accent:#3b82f6; --accent-hover:#60a5fa; --accent-glow:rgba(59,130,246,0.25);
      --success:#10b981; --success-glow:rgba(16,185,129,0.2);
      --warning:#f59e0b;
    }}
    * {{ box-sizing:border-box; margin:0; padding:0; }}
    body {{
      font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;
      background:var(--bg); color:var(--text); min-height:100vh; line-height:1.6;
    }}
    body::before {{
      content:''; position:fixed; inset:0;
      background:
        radial-gradient(ellipse 100% 80% at 50% -30%,rgba(59,130,246,0.12) 0%,transparent 60%),
        radial-gradient(ellipse 60% 50% at 100% 50%,rgba(16,185,129,0.08) 0%,transparent 50%),
        radial-gradient(ellipse 50% 50% at 0% 80%,rgba(139,92,246,0.06) 0%,transparent 50%);
      pointer-events:none; z-index:-1;
    }}
    .container {{ max-width:1400px; margin:0 auto; padding:0 24px; }}

    /* Header */
    .header {{
      padding:40px 0 32px;
      border-bottom:1px solid var(--line);
      margin-bottom:32px;
    }}
    .header-top {{ display:flex; justify-content:space-between; align-items:center; gap:24px; flex-wrap:wrap; margin-bottom:24px; }}
    .brand {{ display:flex; align-items:center; gap:16px; }}
    .brand-icon {{
      width:56px; height:56px; border-radius:14px;
      background:linear-gradient(135deg,var(--accent),var(--success));
      display:flex; align-items:center; justify-content:center;
      box-shadow:0 8px 24px var(--accent-glow);
    }}
    .brand-icon svg {{ width:32px; height:32px; color:#fff; }}
    .brand-text h1 {{ font-size:28px; font-weight:800; letter-spacing:-0.5px; margin:0 0 4px; background:linear-gradient(135deg,var(--text),var(--text-secondary)); -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text; }}
    .brand-text p {{ color:var(--muted); font-size:14px; margin:0; }}

    /* Stats Row */
    .stats-row {{ display:flex; gap:12px; flex-wrap:wrap; }}
    .stat-card {{
      background:var(--panel); border:1px solid var(--line);
      border-radius:14px; padding:16px 24px;
      min-width:110px; text-align:center;
      transition:all .2s ease;
    }}
    .stat-card:hover {{ border-color:var(--line-light); transform:translateY(-2px); }}
    .stat-value {{ font-size:32px; font-weight:800; background:linear-gradient(135deg,var(--accent),var(--accent-hover)); -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text; line-height:1.1; }}
    .stat-label {{ font-size:12px; color:var(--muted); text-transform:uppercase; letter-spacing:0.5px; margin-top:8px; font-weight:600; }}

    /* Toolbar */
    .toolbar {{
      display:flex; gap:12px; margin-bottom:28px;
      flex-wrap:wrap; align-items:center;
    }}
    .search-box {{
      flex:1; min-width:240px; max-width:480px;
      position:relative;
    }}
    .search-box svg {{
      position:absolute; left:16px; top:50%; transform:translateY(-50%);
      width:20px; height:20px; color:var(--muted);
      pointer-events:none;
    }}
    .search-input {{
      width:100%; padding:14px 18px 14px 48px;
      background:var(--panel); border:1px solid var(--line);
      border-radius:12px; color:var(--text);
      font-size:15px; transition:all .2s ease; font-family:inherit;
    }}
    .search-input:focus {{
      outline:none; border-color:var(--accent);
      box-shadow:0 0 0 4px var(--accent-glow);
    }}
    .search-input::placeholder {{ color:var(--muted); }}
    .filter-group {{ display:flex; gap:8px; }}
    .filter-btn {{
      display:flex; align-items:center; gap:8px;
      padding:12px 18px; background:var(--panel);
      border:1px solid var(--line); border-radius:12px;
      color:var(--text); font-size:14px; cursor:pointer;
      transition:all .2s ease; font-family:inherit; font-weight:500;
    }}
    .filter-btn:hover {{ border-color:var(--line-light); }}
    .filter-btn.active {{ border-color:var(--accent); background:rgba(59,130,246,0.1); color:var(--accent); }}
    .filter-btn svg {{ width:18px; height:18px; }}

    /* Grid */
    .grid {{
      display:grid;
      grid-template-columns:repeat(auto-fill,minmax(340px,1fr));
      gap:20px;
    }}
    .session-card {{
      text-decoration:none; color:inherit;
      background:var(--panel); border:1px solid var(--line);
      border-radius:18px; padding:24px;
      display:block; transition:all .3s cubic-bezier(.4,0,.2,1);
      box-shadow:0 4px 20px rgba(0,0,0,0.15);
      position:relative; overflow:hidden;
    }}
    .session-card::before {{
      content:''; position:absolute; top:0; left:0; right:0; height:4px;
      background:linear-gradient(90deg,var(--accent),var(--success));
      opacity:0; transition:opacity .3s ease;
    }}
    .session-card::after {{
      content:''; position:absolute; inset:0;
      background:radial-gradient(ellipse at top,rgba(59,130,246,0.05) 0%,transparent 70%);
      opacity:0; transition:opacity .3s ease;
    }}
    .session-card:hover {{
      border-color:var(--accent); transform:translateY(-6px);
      box-shadow:0 20px 50px rgba(0,0,0,0.25);
    }}
    .session-card:hover::before {{ opacity:1; }}
    .session-card:hover::after {{ opacity:1; }}
    .card-content {{ position:relative; z-index:1; }}
    .card-header {{
      display:flex; justify-content:space-between;
      align-items:center; margin-bottom:14px;
    }}
    .card-index {{
      font-size:13px; font-weight:700; color:var(--muted);
      background:rgba(255,255,255,0.05);
      padding:6px 12px; border-radius:8px;
    }}
    .card-badge {{
      font-size:12px; font-weight:700;
      color:var(--success); background:var(--success-glow);
      padding:6px 12px; border-radius:8px;
    }}
    .session-title {{
      font-weight:700; line-height:1.5; margin-bottom:14px;
      font-size:16px; color:var(--text);
      display:-webkit-box; -webkit-line-clamp:2;
      -webkit-box-orient:vertical; overflow:hidden;
    }}
    .session-meta {{ display:flex; gap:20px; margin-bottom:14px; }}
    .meta-item {{
      display:flex; align-items:center; gap:8px;
      color:var(--muted); font-size:13px; font-weight:500;
    }}
    .meta-item svg {{ opacity:0.6; }}
    .session-id {{
      font-family:'JetBrains Mono',ui-monospace,monospace;
      font-size:11px; color:var(--muted); opacity:0.5;
      word-break:break-all; padding-top:12px;
      border-top:1px solid var(--line);
    }}

    /* Empty State */
    .empty {{
      grid-column:1/-1;
      background:var(--panel); border:2px dashed var(--line);
      border-radius:20px; padding:80px 40px;
      color:var(--muted); text-align:center;
    }}
    .empty-icon {{
      width:80px; height:80px; margin:0 auto 20px;
      opacity:0.3;
    }}
    .empty-title {{ font-size:22px; font-weight:700; color:var(--text); margin-bottom:10px; }}
    .empty-text {{ font-size:15px; }}

    /* Footer */
    .footer {{
      margin-top:60px; padding:32px 0;
      border-top:1px solid var(--line);
      text-align:center; color:var(--muted);
      font-size:13px;
    }}

    @media (max-width: 768px) {{
      .header-top {{ flex-direction:column; align-items:flex-start; }}
      .stats-row {{ width:100%; }}
      .stat-card {{ flex:1; min-width:0; padding:12px 16px; }}
      .stat-value {{ font-size:24px; }}
      .search-box {{ max-width:none; order:-1; width:100%; }}
      .filter-group {{ width:100%; }}
      .filter-btn {{ flex:1; justify-content:center; }}
      .grid {{ grid-template-columns:1fr; }}
    }}
  </style>
</head>
<body>
  <div class="container">
    <header class="header">
      <div class="header-top">
        <div class="brand">
          <div class="brand-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
            </svg>
          </div>
          <div class="brand-text">
            <h1>WorkBuddy 对话导出</h1>
            <p>导出时间：{escape_html(exported_at)}</p>
          </div>
        </div>
        <div class="stats-row">
          <div class="stat-card">
            <div class="stat-value">{len(sessions)}</div>
            <div class="stat-label">会话</div>
          </div>
          <div class="stat-card">
            <div class="stat-value">{total_messages}</div>
            <div class="stat-label">消息</div>
          </div>
          <div class="stat-card">
            <div class="stat-value">{total_media}</div>
            <div class="stat-label">媒体</div>
          </div>
        </div>
      </div>
    </header>

    <div class="toolbar">
      <div class="search-box">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="11" cy="11" r="8"></circle>
          <path d="m21 21-4.35-4.35"></path>
        </svg>
        <input type="text" class="search-input" id="searchInput" placeholder="搜索会话标题或ID..." />
      </div>
      <div class="filter-group">
        <button class="filter-btn active" id="sortBtn" onclick="toggleSort()">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M3 6h18M6 12h12M9 18h6"></path>
          </svg>
          <span id="sortLabel">默认排序</span>
        </button>
      </div>
    </div>

    <div class="grid" id="sessionGrid">
      {body if body else empty_html}
    </div>

    <footer class="footer">
      WorkBuddy Session Export · {escape_html(exported_at)}
    </footer>
  </div>

  <script>
    var currentSort = 'default';

    document.getElementById('searchInput').addEventListener('input', function(e) {{
      var query = e.target.value.toLowerCase();
      var cards = document.querySelectorAll('.session-card');
      var visibleCount = 0;
      cards.forEach(function(card) {{
        var title = (card.getAttribute('data-title') || '') + ' ' + (card.querySelector('.session-id').textContent);
        var visible = title.toLowerCase().includes(query);
        card.style.display = visible ? '' : 'none';
        if (visible) visibleCount++;
      }});
    }});

    function toggleSort() {{
      var grid = document.getElementById('sessionGrid');
      var cards = Array.from(grid.querySelectorAll('.session-card'));
      var label = document.getElementById('sortLabel');

      if (currentSort === 'default') {{
        currentSort = 'messages';
        cards.sort(function(a, b) {{
          var aVal = parseInt(a.getAttribute('data-messages')) || 0;
          var bVal = parseInt(b.getAttribute('data-messages')) || 0;
          return bVal - aVal;
        }});
        label.textContent = '消息排序';
      }} else {{
        currentSort = 'default';
        cards.sort(function(a, b) {{
          var aIdx = parseInt(a.querySelector('.card-index').textContent.replace('#', ''));
          var bIdx = parseInt(b.querySelector('.card-index').textContent.replace('#', ''));
          return aIdx - bIdx;
        }});
        label.textContent = '默认排序';
      }}

      cards.forEach(function(card) {{ grid.appendChild(card); }});
    }}
  </script>
</body>
</html>"""


def generate_chat_html(
    title: str,
    conversation_id: str,
    messages: list[dict[str, Any]],
    media_files: list[dict[str, Any]],
    created_at: str,
    show_back_link: bool = True,
    back_href: str = "../../index.html",
) -> str:

    basic_messages = _build_basic_messages(messages)

    normalized_full = []
    for m in messages:
        normalized_full.append(
            {
                "id": str(m.get("id", "")),
                "role": str(m.get("role", "")) or "unknown",
                "createdAt": str(m.get("createdAt", "") or ""),
                "text": str(m.get("text", "") or ""),
                "toolEvents": m.get("toolEvents", []),
                "modelId": str(m.get("modelId", "") or ""),
                "modelName": str(m.get("modelName", "") or ""),
                "mode": str(m.get("mode", "") or ""),
            }
        )

    user_count = sum(1 for m in basic_messages if m.get("role") == "user")
    assistant_count = sum(1 for m in basic_messages if m.get("role") == "assistant")
    back_link_html = (
        f'''<a href="{escape_html(back_href)}" class="back-link">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 12H5M12 19l-7-7 7-7"></path></svg>
            返回列表
          </a>'''
        if show_back_link
        else ""
    )

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>{escape_html(title or "对话记录")}</title>
  <style>
    :root {{
      --bg:#101317;
      --surface:#171b21;
      --surface-soft:#1d232b;
      --border:#2a313a;
      --text:#eef2f7;
      --muted:#98a2b3;
      --accent:#4f8cff;
      --accent-soft:rgba(79,140,255,0.14);
      --user-bg:#1f2732;
      --assistant-bg:#151a20;
      --tool-bg:#131820;
      --success:#22c55e;
      --purple:#a78bfa;
    }}
    * {{ box-sizing:border-box; margin:0; padding:0; }}
    body {{
      font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;
      background:var(--bg); color:var(--text);
      line-height:1.6; min-height:100vh;
    }}
    .layout {{ max-width:1320px; margin:0 auto; padding:24px 24px 40px; }}

    .header {{
      background:var(--surface);
      border:1px solid var(--border);
      border-radius:16px;
      padding:24px;
      margin-bottom:20px;
    }}
    .header-content {{ display:flex; justify-content:space-between; align-items:flex-start; gap:20px; flex-wrap:wrap; }}
    .header-left {{ flex:1; min-width:0; }}
    .header-actions {{ display:flex; align-items:center; gap:12px; flex-wrap:wrap; }}

    .title {{ font-size:24px; font-weight:700; margin:0 0 10px; word-break:break-word; line-height:1.35; }}
    .meta {{ color:var(--muted); font-size:13px; display:flex; flex-wrap:wrap; gap:14px; }}
    .meta-item {{ display:flex; align-items:center; gap:6px; }}
    .meta-item svg {{ width:16px; height:16px; opacity:0.75; }}

    .stats-inline {{ display:flex; gap:8px; margin-top:14px; flex-wrap:wrap; }}
    .stat-badge {{
      display:flex; align-items:center; gap:8px;
      padding:6px 10px; background:var(--surface-soft);
      border:1px solid var(--border); border-radius:999px;
      font-size:12px; font-weight:600; color:var(--muted);
    }}
    .stat-badge.user {{ color:#93c5fd; }}
    .stat-badge.assistant {{ color:#86efac; }}
    .stat-badge svg {{ width:15px; height:15px; }}

    .back-link {{
      display:inline-flex; align-items:center; gap:8px;
      color:var(--text); text-decoration:none;
      font-size:13px; font-weight:600; margin-bottom:14px;
      padding:8px 12px; background:var(--surface-soft);
      border:1px solid var(--border); border-radius:10px;
      transition:background .2s ease,border-color .2s ease;
    }}
    .back-link:hover {{ background:#222933; border-color:#394353; }}
    .back-link svg {{ width:16px; height:16px; }}

    .toolbar {{
      display:flex; gap:12px; margin-top:18px;
      flex-wrap:wrap; align-items:center;
    }}
    .view-switch {{
      display:inline-flex; gap:4px; padding:4px;
      background:var(--surface-soft); border:1px solid var(--border);
      border-radius:10px;
    }}
    .btn-switch {{
      border:none; border-radius:8px; background:transparent;
      color:var(--muted); padding:8px 14px; cursor:pointer;
      font-size:13px; font-weight:600; font-family:inherit;
      transition:background .2s ease,color .2s ease;
    }}
    .btn-switch.active {{ background:var(--accent); color:#fff; }}
    .btn-switch:hover:not(.active) {{ color:var(--text); background:rgba(255,255,255,0.04); }}

    .search-mini {{ flex:1; max-width:320px; position:relative; }}
    .search-mini svg {{
      position:absolute; left:14px; top:50%; transform:translateY(-50%);
      width:16px; height:16px; color:var(--muted); pointer-events:none;
    }}
    .search-mini input {{
      width:100%; padding:10px 14px 10px 40px;
      background:var(--surface-soft); border:1px solid var(--border);
      border-radius:10px; color:var(--text);
      font-size:13px; font-family:inherit;
      transition:border-color .2s ease,background .2s ease;
    }}
    .search-mini input:focus {{ outline:none; border-color:var(--accent); background:#202730; }}
    .search-mini input::placeholder {{ color:var(--muted); }}

    .btn-action {{
      display:flex; align-items:center; gap:8px;
      border:1px solid var(--border); border-radius:10px;
      background:var(--surface-soft); color:var(--text);
      padding:10px 16px; cursor:pointer;
      font-size:13px; font-weight:600; font-family:inherit;
      transition:background .2s ease,border-color .2s ease;
    }}
    .btn-action:hover {{ background:#222933; border-color:#394353; }}
    .btn-action svg {{ width:16px; height:16px; }}

    .summary {{ color:var(--muted); font-size:13px; font-weight:500; display:flex; align-items:center; gap:8px; }}
    .summary-dot {{ width:6px; height:6px; border-radius:50%; background:var(--accent); }}

    .content {{
      display:grid;
      grid-template-columns:minmax(0,1fr) 340px;
      gap:20px; align-items:start;
    }}

    .chat-panel,
    .media-panel {{
      background:var(--surface);
      border:1px solid var(--border);
      border-radius:16px;
      padding:18px;
    }}
    .panel-header {{
      display:flex; justify-content:space-between;
      align-items:center; margin-bottom:14px;
      padding-bottom:14px; border-bottom:1px solid var(--border);
    }}
    .panel-title {{ font-size:15px; font-weight:700; display:flex; align-items:center; gap:10px; }}
    .panel-title svg {{ width:18px; height:18px; opacity:0.75; }}

    .chat-list {{
      display:flex; flex-direction:column; gap:14px;
      min-height:300px; max-height:72vh; overflow-y:auto;
      padding-right:4px; scrollbar-width:thin; scrollbar-color:var(--border) transparent;
    }}
    .chat-list::-webkit-scrollbar {{ width:6px; }}
    .chat-list::-webkit-scrollbar-track {{ background:transparent; }}
    .chat-list::-webkit-scrollbar-thumb {{ background:var(--border); border-radius:3px; }}

    .bubble {{
      border:1px solid var(--border);
      border-radius:14px;
      padding:14px 16px;
      max-width:82%;
      background:var(--assistant-bg);
    }}
    .bubble.user {{ margin-left:auto; background:var(--user-bg); }}
    .bubble.assistant {{ margin-right:auto; background:var(--assistant-bg); }}
    .bubble.tool,.bubble.unknown {{ margin-right:auto; background:var(--tool-bg); }}

    .bubble-head {{ display:flex; align-items:center; gap:10px; margin-bottom:10px; flex-wrap:wrap; }}
    .role {{ font-weight:700; font-size:12px; }}
    .bubble.user .role {{ color:#93c5fd; }}
    .bubble.assistant .role {{ color:#86efac; }}
    .bubble.tool .role,.bubble.unknown .role {{ color:var(--purple); }}
    .time {{ color:var(--muted); font-size:12px; }}
    .model-tag {{
      font-size:11px;
      color:#c4b5fd;
      border:1px solid rgba(167,139,250,0.35);
      background:rgba(167,139,250,0.12);
      border-radius:999px;
      padding:2px 8px;
      max-width:260px;
      overflow:hidden;
      text-overflow:ellipsis;
      white-space:nowrap;
    }}
    .id {{
      color:var(--muted); font-size:11px; margin-left:auto;
      font-family:'JetBrains Mono',monospace; max-width:180px;
      overflow:hidden; text-overflow:ellipsis; white-space:nowrap;
    }}
    .copy-one,
    .bubble-toggle {{
      border:1px solid var(--border); background:transparent;
      color:var(--muted); border-radius:8px; padding:4px 10px;
      font-size:12px; cursor:pointer; font-family:inherit;
      transition:background .2s ease,border-color .2s ease,color .2s ease;
    }}
    .copy-one:hover,
    .bubble-toggle:hover {{ color:var(--text); border-color:#394353; background:#222933; }}

    .message-body {{ margin:0; }}
    .bubble.tool .message-body {{ display:none; margin-top:2px; }}
    .bubble.tool.expanded .message-body {{ display:block; }}

    .message-text,
    .tool-content pre {{
      margin:0; white-space:pre-wrap; word-break:break-word;
      font-family:'JetBrains Mono',ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
      line-height:1.65; font-size:13px; color:var(--text);
    }}

    .tool-events {{ margin-top:12px; display:flex; flex-direction:column; gap:8px; }}
    .tool-event {{ border:1px solid var(--border); border-radius:12px; background:rgba(255,255,255,0.02); overflow:hidden; }}
    .tool-toggle {{
      width:100%; border:none; background:transparent; color:var(--text);
      display:flex; align-items:center; justify-content:space-between; gap:10px;
      padding:10px 12px; cursor:pointer; font-family:inherit; text-align:left;
    }}
    .tool-toggle:hover {{ background:rgba(255,255,255,0.03); }}
    .tool-toggle-main {{ min-width:0; display:flex; align-items:center; gap:10px; }}
    .tool-kind {{
      flex:none; font-size:11px; font-weight:700; color:var(--purple);
      background:rgba(167,139,250,0.12); border:1px solid rgba(167,139,250,0.2);
      border-radius:999px; padding:3px 8px;
    }}
    .tool-title {{ font-size:12px; color:var(--muted); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
    .tool-chevron {{ width:16px; height:16px; color:var(--muted); flex:none; transition:transform .2s ease; }}
    .tool-event.expanded .tool-chevron {{ transform:rotate(180deg); }}
    .tool-content {{ display:none; padding:0 12px 12px; }}
    .tool-event.expanded .tool-content {{ display:block; }}
    .tool-content pre {{
      background:#0f1318; border:1px solid var(--border);
      border-radius:10px; padding:12px; overflow:auto;
    }}

    .media-panel {{ position:sticky; top:24px; }}
    .media-list {{
      display:flex; flex-direction:column; gap:12px;
      max-height:72vh; overflow-y:auto;
      padding-right:4px; scrollbar-width:thin; scrollbar-color:var(--border) transparent;
    }}
    .media-list::-webkit-scrollbar {{ width:6px; }}
    .media-list::-webkit-scrollbar-track {{ background:transparent; }}
    .media-list::-webkit-scrollbar-thumb {{ background:var(--border); border-radius:3px; }}

    .media-item {{
      border:1px solid var(--border);
      border-radius:12px; padding:14px;
      background:var(--surface-soft);
    }}
    .media-icon {{
      width:34px; height:34px; border-radius:10px;
      background:#202730; border:1px solid var(--border);
      display:flex; align-items:center; justify-content:center;
      margin-bottom:10px;
    }}
    .media-icon svg {{ width:18px; height:18px; color:var(--muted); }}
    .media-name {{ font-size:14px; font-weight:700; margin-bottom:6px; word-break:break-all; color:var(--text); }}
    .media-meta {{ color:var(--muted); font-size:12px; margin-bottom:12px; }}
    .media-links {{ display:flex; flex-wrap:wrap; gap:8px; }}
    .link {{
      font-size:12px; color:var(--text); text-decoration:none;
      border:1px solid var(--border); background:#202730;
      border-radius:8px; padding:6px 12px; font-weight:600;
      transition:background .2s ease,border-color .2s ease;
    }}
    .link:hover {{ border-color:#394353; background:#252d38; }}
    .workspace-path-card {{
      border:1px solid var(--border);
      border-radius:12px;
      background:var(--surface-soft);
      padding:12px;
      display:flex;
      flex-direction:column;
      gap:10px;
    }}
    .workspace-path-label {{ color:var(--muted); font-size:12px; }}
    .workspace-path-row {{ display:flex; gap:8px; align-items:center; }}
    .workspace-path-value {{
      min-width:0;
      flex:1;
      font-size:12px;
      color:var(--text);
      font-family:'JetBrains Mono',ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
      padding:8px 10px;
      border:1px solid var(--border);
      border-radius:8px;
      background:#202730;
      word-break:break-all;
    }}


    .empty {{

      color:var(--muted); font-size:14px;
      border:1px dashed var(--border);
      border-radius:12px; padding:28px;
      text-align:center; background:rgba(255,255,255,0.02);
    }}

    @media (max-width: 1100px) {{
      .content {{ grid-template-columns:1fr; }}
      .media-panel {{ position:static; }}
    }}
    @media (max-width: 640px) {{
      .layout {{ padding:16px 16px 32px; }}
      .header {{ padding:18px; }}
      .title {{ font-size:20px; }}
      .toolbar {{ gap:10px; }}
      .btn-switch {{ padding:8px 12px; font-size:12px; }}
      .btn-action {{ padding:9px 14px; }}
      .search-mini {{ max-width:none; order:-1; width:100%; }}
      .bubble {{ max-width:94%; padding:12px 14px; }}
      .content {{ gap:16px; }}
      .chat-panel, .media-panel {{ padding:16px; }}
      .id {{ max-width:100%; margin-left:0; }}
    }}
  </style>
</head>
<body>
  <div class="layout">
    <header class="header">
      <div class="header-content">
        <div class="header-left">
          {back_link_html}
          <h1 class="title">{escape_html(title or "(无标题)")}</h1>
          <div class="meta">
            <span class="meta-item">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><path d="M12 6v6l4 2"></path></svg>
              {escape_html(created_at or "-")}
            </span>
            <span class="meta-item">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><path d="M14 2v6h6M16 13H8M16 17H8M10 9H8"></path></svg>
              {len(normalized_full)} 完整 · {len(basic_messages)} 基础
            </span>
          </div>
          <div class="stats-inline">
            <div class="stat-badge user">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>
              {user_count} 用户消息
            </div>
            <div class="stat-badge assistant">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2z"></path><path d="M12 16v-4M12 8h.01"></path></svg>
              {assistant_count} 助手消息
            </div>
          </div>
        </div>
        <div class="header-actions">
          <button id="btnCopyAll" class="btn-action" type="button" onclick="copyAll()">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
            复制全部
          </button>
        </div>
      </div>
      <div class="toolbar">
        <div class="view-switch">
          <button id="btnBasic" class="btn-switch active" type="button" onclick="setView('basic')">基础对话</button>
          <button id="btnFull" class="btn-switch" type="button" onclick="setView('full')">完整对话</button>
        </div>
        <div class="search-mini">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"></circle><path d="m21 21-4.35-4.35"></path></svg>
          <input type="text" id="searchMsg" placeholder="搜索消息内容..." />
        </div>
        <div id="summary" class="summary">
          <span class="summary-dot"></span>
          <span>基础对话 {len(basic_messages)} 条</span>
        </div>
      </div>
    </header>

    <section class="content">
      <div class="chat-panel">
        <div class="panel-header">
          <h2 class="panel-title">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>
            对话记录
          </h2>
        </div>
        <div id="chatList" class="chat-list"></div>
      </div>
      <aside class="media-panel">
        <div class="panel-header">
          <h3 class="panel-title">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12"></path></svg>
            媒体文件
          </h3>
          <span style="color:var(--muted);font-size:13px;font-weight:600">{len(media_files)} 个</span>
        </div>
        <div id="mediaList" class="media-list"></div>

        <div class="panel-header" style="margin-top:14px">
          <h3 class="panel-title">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 7h5l2 2h11v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z"></path></svg>
            工作目录
          </h3>
        </div>
        <div class="workspace-path-card">
          <div class="workspace-path-label">工作目录路径</div>
          <div class="workspace-path-row">
            <div id="workspacePathValue" class="workspace-path-value"></div>
            <button id="btnCopyWorkspacePath" class="btn-action" type="button" onclick="copyWorkspacePath()">复制目录</button>
          </div>
        </div>
      </aside>

    </section>
  </div>

  <script>
    function decodeB64Json(s) {{
      try {{
        var bin = atob(String(s || ''));
        var hex = [];
        for (var i = 0; i < bin.length; i += 1) {{
          var h = bin.charCodeAt(i).toString(16);
          hex.push('%' + (h.length === 1 ? '0' + h : h));
        }}
        return JSON.parse(decodeURIComponent(hex.join('')));
      }} catch (e) {{
        return [];
      }}
    }}

    var FULL_MESSAGES = decodeB64Json('{_json_to_b64(normalized_full)}');
    var BASIC_MESSAGES = decodeB64Json('{_json_to_b64(basic_messages)}');
    var MEDIA_FILES = decodeB64Json('{_json_to_b64(media_files)}');
    var WORKSPACE_DIR_NAME = 'workspace';
    var currentView = 'basic';

    var searchQuery = '';

    document.getElementById('searchMsg').addEventListener('input', function(e) {{
      searchQuery = e.target.value.toLowerCase();
      renderChats();
    }});

    function safe(v) {{
      return String(v == null ? '' : v)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
    }}

    function roleLabel(role) {{
      if (role === 'user') return '用户';
      if (role === 'assistant') return '助手';
      if (role === 'tool') return '工具结果';
      return String(role || '未知');
    }}

    function formatToolContent(content) {{
      if (typeof content === 'string') {{
        var text = content.trim();
        return text || '(空内容)';
      }}
      try {{
        return JSON.stringify(content == null ? null : content, null, 2);
      }} catch (e) {{
        return String(content == null ? '(空内容)' : content);
      }}
    }}

    function modelLabel(msg) {{
      var name = String((msg && msg.modelName) || '').trim();
      var id = String((msg && msg.modelId) || '').trim();
      var mode = String((msg && msg.mode) || '').trim();
      var model = name || id;
      if (!model && !mode) return '';
      if (model && mode) return model + ' / ' + mode;
      return model || mode;
    }}

    function displayText(msg) {{
      var text = msg && msg.text ? msg.text : '';
      text = String(text).trim();
      if (text) return text;

      var role = String((msg && msg.role) || '');
      var toolEvents = Array.isArray(msg && msg.toolEvents) ? msg.toolEvents : [];
      if (role === 'tool' && toolEvents.length) {{
        var resultTexts = toolEvents
          .filter(function (evt) {{ return evt && evt.type !== 'tool-call'; }})
          .map(function (evt) {{ return formatToolContent(evt ? evt.result : null); }});
        if (resultTexts.length) return resultTexts.join(String.fromCharCode(10) + String.fromCharCode(10));
      }}

      return '(空内容)';
    }}

    function formatBytes(size) {{
      var n = Number(size || 0);
      if (n >= 1024 * 1024) return (n / 1024 / 1024).toFixed(1) + ' MB';
      if (n >= 1024) return (n / 1024).toFixed(1) + ' KB';
      return n + ' B';
    }}

    function copyText(text) {{
      var val = String(text || '');
      if (navigator.clipboard && navigator.clipboard.writeText) return navigator.clipboard.writeText(val);
      var ta = document.createElement('textarea');
      ta.value = val;
      ta.style.position = 'fixed';
      ta.style.left = '-9999px';
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
      return Promise.resolve();
    }}

    function sourceMessages() {{
      return currentView === 'basic' ? BASIC_MESSAGES : FULL_MESSAGES;
    }}

    function copyAll() {{
      var lines = sourceMessages().map(function (m) {{
        return '【' + roleLabel(m.role) + '】' + String.fromCharCode(10) + displayText(m);
      }});
      var sep = String.fromCharCode(10) + String.fromCharCode(10) + '---' + String.fromCharCode(10) + String.fromCharCode(10);
      copyText(lines.join(sep)).then(function () {{
        var btn = document.getElementById('btnCopyAll');
        var prev = btn.innerHTML;
        btn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:18px;height:18px"><path d="M20 6L9 17l-5-5"></path></svg>已复制';
        setTimeout(function () {{ btn.innerHTML = prev; }}, 1500);
      }});
    }}

    function copyOne(index) {{
      var m = sourceMessages()[index];
      if (!m) return;
      copyText(displayText(m));
    }}

    function toggleTool(btn) {{
      var item = btn && btn.parentNode;
      if (!item) return;
      item.classList.toggle('expanded');
    }}

    function toggleBubble(btn) {{
      var item = btn && btn.closest ? btn.closest('.bubble') : null;
      if (!item) return;
      var expanded = item.classList.toggle('expanded');
      btn.textContent = expanded ? '隐藏' : '展开';
    }}

    function renderChats() {{
      var data = sourceMessages();
      var root = document.getElementById('chatList');
      
      if (searchQuery) {{
        data = data.filter(function(m) {{
          return displayText(m).toLowerCase().includes(searchQuery);
        }});
      }}
      
      if (!data.length) {{
        root.innerHTML = '<div class="empty">' + (searchQuery ? '未找到匹配的消息' : '暂无可显示对话') + '</div>';
        return;
      }}
      root.innerHTML = data.map(function (m, i) {{
        var role = String((m && m.role) || 'unknown');
        var toolEvents = Array.isArray(m && m.toolEvents) ? m.toolEvents : [];
        var toolsHtml = '';
        var model = modelLabel(m);
        var modelHtml = model ? '<span class="model-tag">' + safe(model) + '</span>' : '';
        var toggleBtn = role === 'tool' ? '<button class="bubble-toggle" type="button" onclick="toggleBubble(this)">展开</button>' : '';
        if (currentView === 'full' && role !== 'tool' && toolEvents.length) {{
          toolsHtml = '<div class="tool-events">' + toolEvents.map(function (evt) {{
            var isCall = evt && evt.type === 'tool-call';
            var content = isCall ? evt.args : (evt ? evt.result : null);
            var kind = isCall ? '工具调用' : '工具结果';
            var title = (evt && evt.toolName) || '-';
            return '<div class="tool-event">' +
              '<button class="tool-toggle" type="button" onclick="toggleTool(this)">' +
                '<span class="tool-toggle-main">' +
                  '<span class="tool-kind">' + safe(kind) + '</span>' +
                  '<span class="tool-title">' + safe(title) + '</span>' +
                '</span>' +
                '<svg class="tool-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m6 9 6 6 6-6"></path></svg>' +
              '</button>' +
              '<div class="tool-content"><pre>' + safe(formatToolContent(content)) + '</pre></div>' +
            '</div>';
          }}).join('') + '</div>';
        }}

        return '<article class="bubble ' + safe(role) + '">' +
          '<div class="bubble-head">' +
            '<span class="role">' + safe(roleLabel(role)) + '</span>' +
            '<span class="time">' + safe((m && m.createdAt) || '-') + '</span>' +
            modelHtml +
            toggleBtn +
            '<button class="copy-one" type="button" onclick="copyOne(' + i + ')">复制</button>' +
          '</div>' +
          '<div class="message-body"><pre class="message-text">' + safe(displayText(m)) + '</pre></div>' +
          toolsHtml +
        '</article>';
      }}).join('');
    }}

    function renderMedia() {{
      var root = document.getElementById('mediaList');
      if (!MEDIA_FILES.length) {{
        root.innerHTML = '<div class="empty">未找到媒体文件</div>';
        return;
      }}
      root.innerHTML = MEDIA_FILES.map(function (m) {{
        var path = m && m.exportedPath ? m.exportedPath : '';
        var openLink = path ? '<a class="link" href="' + safe(path) + '" target="_blank">打开文件</a>' : '';
        var dirPath = path ? path.substring(0, path.lastIndexOf('/') + 1) : '';
        var locateLink = dirPath ? '<a class="link" href="' + safe(dirPath) + '" target="_blank">定位文件</a>' : '';
        return '<div class="media-item">' +
          '<div class="media-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><path d="M14 2v6h6"></path></svg></div>' +
          '<div class="media-name">' + safe((m && m.fileName) || '-') + '</div>' +
          '<div class="media-meta">' + safe((m && m.mimeType) || '-') + ' · ' + safe(formatBytes((m && m.size) || 0)) + '</div>' +
          '<div class="media-links">' + openLink + locateLink + '</div>' +
        '</div>';
      }}).join('');
    }}

    function resolveExportWorkspacePath() {{
      var dirName = WORKSPACE_DIR_NAME || 'workspace';
      var href = String(window.location.href || '');
      if (!href) return './' + dirName;
      if (href.indexOf('file://') === 0) {{
        var pathname = decodeURIComponent(String(window.location.pathname || ''));
        if (/^\/[A-Za-z]:\//.test(pathname)) pathname = pathname.slice(1);
        var sep = String.fromCharCode(92);
        pathname = pathname.replace(/\//g, sep);
        var pos = pathname.lastIndexOf(sep);
        var base = pos >= 0 ? pathname.slice(0, pos) : pathname;
        return base ? (base + sep + dirName) : ('.' + sep + dirName);
      }}
      return './' + dirName;
    }}

    function renderWorkspacePath() {{
      var valEl = document.getElementById('workspacePathValue');
      if (!valEl) return;
      valEl.textContent = resolveExportWorkspacePath();
    }}

    function copyWorkspacePath() {{
      var val = resolveExportWorkspacePath();
      if (!val) return;
      copyText(val).then(function () {{
        var btn = document.getElementById('btnCopyWorkspacePath');
        if (!btn) return;
        var prev = btn.textContent;
        btn.textContent = '已复制';
        setTimeout(function () {{ btn.textContent = prev; }}, 1500);
      }});
    }}



    function setView(view) {{
      currentView = view === 'full' ? 'full' : 'basic';
      document.getElementById('btnBasic').classList.toggle('active', currentView === 'basic');
      document.getElementById('btnFull').classList.toggle('active', currentView === 'full');
      var count = sourceMessages().length;
      document.getElementById('summary').querySelector('span:last-child').textContent = (currentView === 'basic' ? '基础对话 ' : '完整对话 ') + count + ' 条';
      renderChats();
    }}

    renderChats();
    renderMedia();
    renderWorkspacePath();
  </script>

</body>
</html>"""


def build_export_html_zip(ids: list[str]) -> bytes:
    uniq_ids = [x for x in dict.fromkeys(ids) if x]
    session_map = load_session_values(uniq_ids)
    exportable_ids = [cid for cid in uniq_ids if session_map.get(cid)]
    single_mode = len(exportable_ids) == 1

    buf = io.BytesIO()
    exported_at_ms = int(time.time() * 1000)
    exported_at_text = ts_to_text(exported_at_ms)
    index_entries: list[dict[str, Any]] = []

    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for cid in uniq_ids:
            session = session_map.get(cid)
            if not session:
                continue

            try:
                chat_data = load_conversation_chat(cid)
            except Exception:
                chat_data = {"messages": []}

            messages = chat_data.get("messages", []) if isinstance(chat_data, dict) else []
            media_records = collect_media_records(cid)

            title = str(session.get("title", "") or "")
            created_at = ts_to_text(session.get("createdAt", 0))
            folder_name = f"{cid}-{_slugify(title, cid)[:32]}"
            conv_root = "" if single_mode else f"conversations/{folder_name}"
            detail_entry = "index.html" if single_mode else f"{conv_root}/index.html"
            session_entry = "session.json" if single_mode else f"{conv_root}/session.json"
            media_root = "media" if single_mode else f"{conv_root}/media"
            workspace_root = "workspace" if single_mode else f"{conv_root}/workspace"


            media_files: list[dict[str, Any]] = []
            used_names: set[str] = set()
            for rec in media_records:
                file_path = str(rec.get("filePath", "") or "")
                file_name = str(rec.get("fileName", "") or "")
                if not file_name:
                    file_name = Path(file_path).name if file_path else "unknown.bin"

                ext = Path(file_name).suffix
                stem = Path(file_name).stem
                candidate = file_name
                idx = 1
                while candidate.lower() in used_names:
                    candidate = f"{stem}_{idx}{ext}"
                    idx += 1
                used_names.add(candidate.lower())

                src_path = Path(file_path) if file_path else None
                file_exists = bool(src_path is not None and src_path.exists() and src_path.is_file())
                if src_path is not None and file_exists:
                    try:
                        zf.writestr(f"{media_root}/{candidate}", src_path.read_bytes())
                    except Exception:
                        pass

                media_files.append(
                    {
                        "fileName": file_name,
                        "mimeType": str(rec.get("mimeType", "") or ""),
                        "size": int(rec.get("size", 0) or 0),
                        "exportedPath": f"media/{candidate}" if file_exists else "",
                        "localPath": file_path,
                    }
                )

            workspace_files: list[dict[str, Any]] = []
            cwd = str(session.get("cwd", "") or "")
            for wf in collect_workspace_files(cwd):
                rel_path = str(wf.get("relativePath", "") or "")
                local_path = str(wf.get("localPath", "") or "")
                src_path = Path(local_path) if local_path else None
                file_exists = bool(src_path is not None and src_path.exists() and src_path.is_file())
                if src_path is not None and file_exists:
                    try:
                        zf.writestr(f"{workspace_root}/{rel_path}", src_path.read_bytes())
                    except Exception:
                        file_exists = False
                workspace_files.append(
                    {
                        "name": str(wf.get("name", "") or ""),
                        "relativePath": rel_path,
                        "size": int(wf.get("size", 0) or 0),
                        "localPath": local_path,
                        "exportedPath": f"workspace/{rel_path}" if file_exists else "",
                    }
                )

            html_content = generate_chat_html(
                title,
                cid,
                messages,
                media_files,
                created_at,
                show_back_link=not single_mode,
                back_href="../../index.html",
            )

            zf.writestr(detail_entry, html_content)
            zf.writestr(
                session_entry,
                json.dumps(
                    {
                        "conversationId": cid,
                        "title": title,
                        "createdAt": created_at,
                        "messageCount": len(messages),
                        "mediaCount": len(media_files),
                        "workspaceFileCount": len(workspace_files),

                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            )

            index_entries.append(
                {
                    "conversationId": cid,
                    "title": title,
                    "entry": detail_entry,
                    "messageCount": len(messages),
                    "mediaCount": len(media_files),
                    "workspaceFileCount": len(workspace_files),

                }
            )

        if not single_mode:
            zf.writestr("index.html", generate_export_index_html(index_entries, exported_at_text))
        zf.writestr(
            "manifest.json",
            json.dumps(
                {
                    "format": "workbuddy-chat-export-v3",
                    "exportedAt": exported_at_ms,
                    "count": len(index_entries),
                    "sessions": index_entries,
                },
                ensure_ascii=False,
                indent=2,
            ),
        )

    return buf.getvalue()
