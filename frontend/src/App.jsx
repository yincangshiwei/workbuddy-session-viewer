import { useEffect, useMemo, useRef, useState } from "react";


const STATUS_COLORS = {
  completed: "#68d391",
  working: "#f6ad55",
  failed: "#fc8181",
  cancelled: "#718096",
  inprogress: "#63b3ed",
};

const PAGE_SIZE = 20;

function escHtml(str = "") {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;");
}

function formatSize(size = 0) {
  if (size > 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)}MB`;
  if (size > 1024) return `${(size / 1024).toFixed(1)}KB`;
  return `${size}B`;
}

function prettyJson(value) {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value ?? "");
  }
}


export default function App() {
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [autoRefreshing, setAutoRefreshing] = useState(false);
  const [countdown, setCountdown] = useState(5);
  const [error, setError] = useState("");


  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [cwdFilter, setCwdFilter] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const [sortField, setSortField] = useState("created");
  const [sortDir, setSortDir] = useState(-1);
  const [currentPage, setCurrentPage] = useState(1);

  const [selectedIds, setSelectedIds] = useState(new Set());
  const [detail, setDetail] = useState(null);
  const [tab, setTab] = useState("info");
  const [pendingDeleteIds, setPendingDeleteIds] = useState([]);
  const [chatLoading, setChatLoading] = useState(false);
  const [chatError, setChatError] = useState("");
  const [chatMap, setChatMap] = useState({});
  const fileInputRef = useRef(null);


  async function fetchSessions(options = { silent: false, preserveUi: false, auto: false, resetPage: false }) {


    const { silent, preserveUi, auto, resetPage } = options;

    if (auto) setAutoRefreshing(true);

    if (!silent) {
      setLoading(true);
      setError("");
    }
    try {
      const resp = await fetch(`/api/sessions?_t=${Date.now()}`, { cache: "no-store" });

      if (!resp.ok) throw new Error(`请求失败: ${resp.status}`);
      const data = await resp.json();
      const nextSessions = data.sessions || [];
      const idSet = new Set(nextSessions.map((x) => x.conversationId));

      setSessions(nextSessions);
      if (resetPage) setCurrentPage(1);

      if (preserveUi) {
        setSelectedIds((prev) => new Set([...prev].filter((id) => idSet.has(id))));
        setDetail((prev) => {
          if (!prev) return null;
          return nextSessions.find((x) => x.conversationId === prev.conversationId) || null;
        });
      } else {
        setSelectedIds(new Set());
        setDetail(null);
      }
    } catch (e) {
      if (!silent) setError(e.message || "加载失败");
    } finally {
      if (!silent) setLoading(false);
      if (auto) setAutoRefreshing(false);
    }
  }


  useEffect(() => {
    fetchSessions();
  }, []);

  useEffect(() => {
    const timer = setInterval(() => {
      setCountdown((prev) => {
        if (prev <= 1) {
          fetchSessions({ silent: true, preserveUi: true, auto: true });
          return 5;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!detail) return;
    const onKeyDown = (e) => {
      if (e.key === "Escape") setDetail(null);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [detail]);

  useEffect(() => {

    if (!detail || tab !== "chat") return;
    if (chatMap[detail.conversationId]) return;
    let cancelled = false;

    async function fetchChat() {
      setChatLoading(true);
      setChatError("");
      try {
        const resp = await fetch(`/api/session/${encodeURIComponent(detail.conversationId)}/chat?_t=${Date.now()}`, { cache: "no-store" });

        const data = await resp.json();
        if (!resp.ok) throw new Error(data?.detail || `请求失败: ${resp.status}`);
        if (!cancelled) {
          setChatMap((prev) => ({ ...prev, [detail.conversationId]: data }));
        }
      } catch (e) {
        if (!cancelled) setChatError(e.message || "加载对话失败");
      } finally {
        if (!cancelled) setChatLoading(false);
      }
    }

    fetchChat();
    return () => {
      cancelled = true;
    };
  }, [detail, tab, chatMap]);


  const filteredRows = useMemo(() => {

    const q = search.trim().toLowerCase();
    let rows = sessions.filter((s) => {
      const title = (s.title || "").toLowerCase();
      const id = (s.conversationId || "").toLowerCase();
      const cwd = (s.cwd || "").toLowerCase();
      const st = (s.status || "").toLowerCase();
      const created = Number(s.createdAtTs || 0);

      if (q && !title.includes(q) && !id.includes(q) && !cwd.includes(q)) return false;
      if (statusFilter && st !== statusFilter) return false;
      if (cwdFilter === "missing" && s.cwdExists) return false;
      if (cwdFilter === "exists" && !s.cwdExists) return false;
      if (dateFrom) {
        const from = new Date(dateFrom).getTime();
        if (created < from) return false;
      }
      if (dateTo) {
        const to = new Date(dateTo);
        to.setHours(23, 59, 59, 999);
        if (created > to.getTime()) return false;
      }
      return true;
    });

    rows = rows.sort((a, b) => {
      let va;
      let vb;
      if (sortField === "title") {
        va = a.title || "";
        vb = b.title || "";
      } else if (sortField === "status") {
        va = a.status || "";
        vb = b.status || "";
      } else if (sortField === "cwd") {
        va = a.cwd || "";
        vb = b.cwd || "";
      } else {
        va = Number(a.createdAtTs || 0);
        vb = Number(b.createdAtTs || 0);
      }
      if (va < vb) return -sortDir;
      if (va > vb) return sortDir;
      return 0;
    });

    return rows;
  }, [sessions, search, statusFilter, cwdFilter, dateFrom, dateTo, sortField, sortDir]);

  const totalPages = Math.max(1, Math.ceil(filteredRows.length / PAGE_SIZE));
  useEffect(() => {
    setCurrentPage((prev) => Math.min(prev, totalPages));
  }, [totalPages]);

  const pageStart = (currentPage - 1) * PAGE_SIZE;
  const pageRows = filteredRows.slice(pageStart, pageStart + PAGE_SIZE);

  const stats = useMemo(() => {
    const total = sessions.length;
    const completed = sessions.filter((s) => (s.status || "").toLowerCase() === "completed").length;
    const working = sessions.filter((s) => ["working", "inprogress"].includes((s.status || "").toLowerCase())).length;
    const missing = sessions.filter((s) => !s.cwdExists).length;
    const withFc = sessions.filter((s) => (s.fileChanges || []).length > 0).length;
    return { total, completed, working, missing, withFc };
  }, [sessions]);

  function clearFilters() {
    setSearch("");
    setStatusFilter("");
    setCwdFilter("");
    setDateFrom("");
    setDateTo("");
    setCurrentPage(1);
  }

  function sortBy(field) {
    if (sortField === field) setSortDir((x) => -x);
    else {
      setSortField(field);
      setSortDir(-1);
    }
    setCurrentPage(1);
  }

  function toggleOne(cid) {
    const next = new Set(selectedIds);
    if (next.has(cid)) next.delete(cid);
    else next.add(cid);
    setSelectedIds(next);
  }

  function toggleAll(checked) {
    if (!checked) {
      const next = new Set(selectedIds);
      pageRows.forEach((x) => next.delete(x.conversationId));
      setSelectedIds(next);
      return;
    }
    const next = new Set(selectedIds);
    pageRows.forEach((x) => next.add(x.conversationId));
    setSelectedIds(next);
  }

  function openDelete(ids) {
    if (!ids.length) return;
    setPendingDeleteIds(ids);
  }

  function closeDelete() {
    setPendingDeleteIds([]);
  }

  async function executeDelete() {
    if (!pendingDeleteIds.length) return;
    setLoading(true);
    setError("");
    try {
      const resp = await fetch("/api/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids: pendingDeleteIds }),
      });
      const result = await resp.json();
      if (!resp.ok || !result.success) {
        throw new Error(result?.error || `删除失败: ${resp.status}`);
      }
      const deletedSet = new Set(pendingDeleteIds);
      setSessions((prev) => prev.filter((s) => !deletedSet.has(s.conversationId)));
      setSelectedIds((prev) => new Set([...prev].filter((id) => !deletedSet.has(id))));
      if (detail && deletedSet.has(detail.conversationId)) setDetail(null);
      closeDelete();
    } catch (e) {
      setError(e.message || "删除失败");
    } finally {
      setLoading(false);
    }
  }

  async function exportSelected() {
    const ids = Array.from(selectedIds);
    if (!ids.length) {
      setError("请先勾选要导出的会话");
      return;
    }

    setLoading(true);
    setError("");
    try {
      const resp = await fetch("/api/export", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids }),
      });
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data?.detail || `导出失败: ${resp.status}`);
      }

      const blob = await resp.blob();
      const disposition = resp.headers.get("content-disposition") || "";
      const m = disposition.match(/filename="([^"]+)"/i);
      const fileName = m?.[1] || `workbuddy-export-${Date.now()}.zip`;
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = fileName;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e.message || "导出失败");
    } finally {
      setLoading(false);
    }
  }

  async function onImportFileChange(e) {
    const file = e.target.files?.[0];
    if (!file) return;

    setLoading(true);
    setError("");
    try {
      const form = new FormData();
      form.append("file", file);
      const resp = await fetch("/api/import", { method: "POST", body: form });
      const data = await resp.json();
      if (!resp.ok || !data?.success) {
        throw new Error(data?.detail || data?.error || `导入失败: ${resp.status}`);
      }
      await fetchSessions({ silent: false, preserveUi: false, auto: false });
      setSelectedIds(new Set());
      window.alert(`导入完成：${data.count || 0} 条会话`);
    } catch (err) {
      setError(err.message || "导入失败");
    } finally {
      setLoading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  const pendingManifest = useMemo(() => {

    const map = new Map(sessions.map((x) => [x.conversationId, x]));
    const items = [];
    pendingDeleteIds.forEach((id) => {
      const s = map.get(id);
      if (s?.deleteManifest?.length) items.push(...s.deleteManifest);
    });
    return items;
  }, [pendingDeleteIds, sessions]);

  const allCheckedOnPage = pageRows.length > 0 && pageRows.every((x) => selectedIds.has(x.conversationId));
  const currentChat = detail ? chatMap[detail.conversationId] : null;
  const currentChatMessages = currentChat?.messages || [];
  const firstChatTime = currentChatMessages[0]?.createdAt || "-";
  const lastChatTime = currentChatMessages[currentChatMessages.length - 1]?.createdAt || "-";

  return (

    <>
      <div className="header">
        <h1>WorkBuddy 任务会话</h1>
        <p>数据来源：codebuddy-sessions.vscdb · todos · file-changes · media-index</p>
      </div>

      <div className="stats">
        <div className="stat"><div className="num">{stats.total}</div><div className="lbl">总任务</div></div>
        <div className="stat"><div className="num c-ok">{stats.completed}</div><div className="lbl">已完成</div></div>
        <div className="stat"><div className="num c-run">{stats.working}</div><div className="lbl">进行中</div></div>
        <div className="stat"><div className="num c-err">{stats.missing}</div><div className="lbl">目录缺失</div></div>
        <div className="stat"><div className="num c-info">{stats.withFc}</div><div className="lbl">有文件变更</div></div>
      </div>

      <div className="toolbar">
        <input type="text" value={search} onChange={(e) => { setSearch(e.target.value); setCurrentPage(1); }} placeholder="🔍 搜索标题 / ID / 目录..." />
        <select value={statusFilter} onChange={(e) => { setStatusFilter(e.target.value); setCurrentPage(1); }}>
          <option value="">全部状态</option>
          <option value="completed">Completed</option>
          <option value="working">Working</option>
          <option value="failed">Failed</option>
          <option value="cancelled">Cancelled</option>
          <option value="inprogress">InProgress</option>
        </select>
        <select value={cwdFilter} onChange={(e) => { setCwdFilter(e.target.value); setCurrentPage(1); }}>
          <option value="">全部目录</option>
          <option value="missing">❌ 目录缺失</option>
          <option value="exists">✅ 目录存在</option>
        </select>
        <div className="date-group">
          <span>从</span>
          <input type="date" value={dateFrom} onChange={(e) => { setDateFrom(e.target.value); setCurrentPage(1); }} />
          <span>到</span>
          <input type="date" value={dateTo} onChange={(e) => { setDateTo(e.target.value); setCurrentPage(1); }} />
        </div>
        <button onClick={clearFilters}>清除筛选</button>
        <button onClick={() => { setCountdown(5); fetchSessions({ resetPage: true }); }} disabled={loading}>{loading ? "处理中..." : "刷新"}</button>

        <button onClick={() => fileInputRef.current?.click()} disabled={loading}>导入</button>
        <button onClick={exportSelected} disabled={loading || selectedIds.size === 0}>导出已选({selectedIds.size})</button>
        <button className="btn-danger" onClick={() => openDelete(Array.from(selectedIds))} disabled={loading || selectedIds.size === 0}>批量删除({selectedIds.size})</button>
        <input ref={fileInputRef} type="file" accept=".zip" style={{ display: "none" }} onChange={onImportFileChange} />
        <span className="countDisplay">显示 {filteredRows.length} / {sessions.length} 条</span>


        <span className={`auto-refresh-tip ${autoRefreshing ? "active" : ""}`}>{autoRefreshing ? "自动刷新中..." : `自动刷新倒计时：${countdown}s`}</span>

      </div>

      {error ? <div className="error">{error}</div> : null}


      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th style={{ width: 36 }}>
                <input type="checkbox" checked={allCheckedOnPage} onChange={(e) => toggleAll(e.target.checked)} />
              </th>
              <th onClick={() => sortBy("title")}>标题 / 对话ID <span className="sort-icon">↕</span></th>
              <th style={{ width: 90 }} onClick={() => sortBy("status")}>状态 <span className="sort-icon">↕</span></th>
              <th onClick={() => sortBy("cwd")}>工作目录 <span className="sort-icon">↕</span></th>
              <th onClick={() => sortBy("created")}>创建时间 <span className="sort-icon">↕</span></th>
              <th style={{ width: 130, textAlign: "center" }}>操作</th>


            </tr>
          </thead>
          <tbody>
            {pageRows.map((s) => {
              const st = (s.status || "").toLowerCase();
              const stColor = STATUS_COLORS[st] || "#718096";
              const todos = s.todos || [];
              const fileChanges = s.fileChanges || [];
              const related = s.related || [];
              const done = todos.filter((t) => t.status === "completed").length;
              const totalAdd = fileChanges.reduce((a, f) => a + (f.addedLines || 0), 0);
              const totalRm = fileChanges.reduce((a, f) => a + (f.removedLines || 0), 0);
              const spaceName = (s.cwd || "").split(/[\\/]/).filter(Boolean).pop() || "";
              return (
                <tr
                  key={s.conversationId}
                  className={selectedIds.has(s.conversationId) ? "row-selected" : ""}
                  onClick={() => toggleOne(s.conversationId)}
                  onDoubleClick={() => { setDetail(s); setTab("info"); }}
                >
                  <td>
                    <input
                      type="checkbox"
                      checked={selectedIds.has(s.conversationId)}
                      onClick={(e) => e.stopPropagation()}
                      onChange={() => toggleOne(s.conversationId)}
                    />
                  </td>
                  <td>
                    <div className="title-link">{s.title || "(无标题)"}</div>
                    <div className="sub">ID: {(s.conversationId || "").slice(0, 16)}...（双击查看详情）</div>
                    <div className="sub">{s.createdAt || ""}</div>
                    {todos.length > 0 ? <div className="small">📋 {done}/{todos.length} 完成</div> : null}
                    {fileChanges.length > 0 ? <div className="small"><span className="c-ok">+{totalAdd}</span> <span className="c-err">-{totalRm}</span> <span className="sub">({fileChanges.length} 文件)</span></div> : null}
                    {related.length > 0 ? <div className="small c-info">🔗 {related.length} 个关联对话</div> : null}
                  </td>
                  <td><span style={{ color: stColor, fontWeight: 600, fontSize: 12 }}>{s.status}</span></td>
                  <td>
                    <div className="small">{s.cwdExists ? "✅" : "❌"} <span className="c-info" style={{ fontWeight: 600 }}>{spaceName}</span></div>
                    <div className="sub cwd-sub">{s.cwd}</div>
                  </td>
                  <td>{s.createdAt || ""}</td>
                  <td style={{ textAlign: "center", whiteSpace: "nowrap" }}>
                    <button className="btn-outline" onClick={(e) => { e.stopPropagation(); setDetail(s); setTab("info"); }}>详情</button>
                    <button className="btn-danger" onClick={(e) => { e.stopPropagation(); openDelete([s.conversationId]); }}>删除</button>
                  </td>

                </tr>
              );

            })}
            {pageRows.length === 0 && (
              <tr>
                <td colSpan={6} className="empty-state">暂无数据</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="pagination">
        <button onClick={() => setCurrentPage(1)} disabled={currentPage <= 1}>首页</button>
        <button onClick={() => setCurrentPage((p) => Math.max(1, p - 1))} disabled={currentPage <= 1}>上一页</button>
        <span>第 {currentPage} / {totalPages} 页</span>
        <button onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))} disabled={currentPage >= totalPages}>下一页</button>
        <button onClick={() => setCurrentPage(totalPages)} disabled={currentPage >= totalPages}>末页</button>
      </div>

      {detail && (
        <div className="modal-overlay active" onClick={() => setDetail(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div className="modal-title">{detail.title || "(无标题)"}</div>
              <div style={{ display: "flex", gap: 8 }}>
                <button className="btn-danger" onClick={() => openDelete([detail.conversationId])}>🗑 删除此任务</button>
                <button className="modal-close" onClick={() => setDetail(null)}>✕</button>
              </div>
            </div>
            <div className="modal-tabs">
              <div className={`modal-tab ${tab === "info" ? "active" : ""}`} onClick={() => setTab("info")}>📋 基本信息</div>
              <div className={`modal-tab ${tab === "chat" ? "active" : ""}`} onClick={() => setTab("chat")}>💬 对话 ({chatMap[detail.conversationId]?.messageCount || 0})</div>
              <div className={`modal-tab ${tab === "todos" ? "active" : ""}`} onClick={() => setTab("todos")}>✅ Todos ({detail.todos?.length || 0})</div>
              <div className={`modal-tab ${tab === "files" ? "active" : ""}`} onClick={() => setTab("files")}>📁 文件变更 ({detail.fileChanges?.length || 0})</div>
              <div className={`modal-tab ${tab === "related" ? "active" : ""}`} onClick={() => setTab("related")}>🔗 关联对话 ({detail.related?.length || 0})</div>
              <div className={`modal-tab ${tab === "media" ? "active" : ""}`} onClick={() => setTab("media")}>🖼 媒体文件 ({detail.mediaFiles?.length || 0})</div>
            </div>

            <div className="modal-body">
              {tab === "info" && (
                <div className="tab-content active">
                  <div className="info-grid">
                    <div className="info-item"><div className="info-label">对话 ID</div><div className="info-value mono">{detail.conversationId}</div></div>
                    <div className="info-item"><div className="info-label">状态</div><div className="info-value">{detail.status}</div></div>
                    <div className="info-item"><div className="info-label">创建时间</div><div className="info-value">{detail.createdAt}</div></div>
                    <div className="info-item"><div className="info-label">更新时间</div><div className="info-value">{detail.updatedAt}</div></div>
                    <div className="info-item full"><div className="info-label">工作目录</div><div className="info-value mono">{detail.cwd} {detail.cwdExists ? "✅" : "❌"}</div></div>
                  </div>
                </div>
              )}

              {tab === "chat" && (
                <div className="tab-content active">
                  {chatLoading ? <div className="empty-state">对话加载中...</div> : null}
                  {!chatLoading && chatError ? <div className="error">{chatError}</div> : null}
                  {!chatLoading && !chatError && !currentChatMessages.length ? <div className="empty-state">📭 暂无对话记录</div> : null}
                  {!chatLoading && !chatError && currentChatMessages.length > 0 ? (
                    <div className="chat-summary">对话时间：{firstChatTime} ~ {lastChatTime}（共 {currentChatMessages.length} 条）</div>
                  ) : null}
                  {!chatLoading && !chatError && currentChatMessages.map((m, i) => (
                    <div className={`chat-item role-${m.role || "unknown"}`} key={m.id || `${m.role || "unknown"}-${i}`}>
                      <div className="chat-meta">{m.role || "unknown"} · {m.id} · {m.createdAt || "-"}</div>
                      {m.text ? <pre className="chat-text">{m.text}</pre> : null}
                      {!m.text && !(m.toolEvents || []).length ? <pre className="chat-text">(无文本内容)</pre> : null}
                      {(m.toolEvents || []).length > 0 && (

                        <div className="tool-event-list">
                          {(m.toolEvents || []).map((evt, ti) => (
                            <div className="tool-event" key={`${m.id || i}-tool-${ti}`}>
                              <div className="tool-event-title">
                                {evt.type === "tool-call" ? "工具调用" : "工具结果"} · {evt.toolName || "-"} · {evt.toolCallId || "-"}
                                {evt.isError ? " · error" : ""}
                              </div>
                              <pre className="tool-event-body">{prettyJson(evt.type === "tool-call" ? evt.args : evt.result)}</pre>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}


              {tab === "todos" && (
                <div className="tab-content active">
                  {(detail.todos || []).length === 0 ? <div className="empty-state">📭 暂无 Todo 数据</div> : (detail.todos || []).map((t, i) => (
                    <div className="todo-item" key={i}>
                      <span>{t.status === "completed" ? "✅" : t.status === "in_progress" ? "⟳" : t.status === "cancelled" ? "✗" : "○"}</span>
                      <span className="todo-content">{t.content}</span>
                      <span className="todo-status">{t.status}</span>
                    </div>
                  ))}
                </div>
              )}


              {tab === "files" && (
                <div className="tab-content active">
                  {(detail.fileChanges || []).length === 0 ? <div className="empty-state">📭 暂无文件变更记录</div> : (detail.fileChanges || []).map((fc, i) => (
                    <div className="fc-item" key={i}>
                      <div className="fc-header">
                        <div className="fc-filename">{fc.fileName}</div>
                        <div className="fc-stats"><span className="c-ok">+{fc.addedLines}</span><span className="c-err">-{fc.removedLines}</span><span className="fc-type">{fc.changeType}</span><span className="sub">{fc.timestampText}</span></div>
                      </div>
                      <div className="fc-diff open">
                        <pre dangerouslySetInnerHTML={{ __html: fc.diffHtml || escHtml(fc.diff || "") }} />
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {tab === "related" && (
                <div className="tab-content active">
                  {(detail.related || []).length === 0 ? <div className="empty-state">📭 此工作目录只有本任务</div> : (detail.related || []).map((r) => (
                    <div className="related-item" key={r.conversationId}>
                      <div className="related-title">{r.title || "(无标题)"}</div>
                      <div className="related-meta">{r.status} · 创建: {r.createdAt || "-"} · 更新: {r.updatedAt || "-"}</div>
                      <div className="mono sub">{r.conversationId}</div>
                    </div>

                  ))}
                </div>
              )}

              {tab === "media" && (
                <div className="tab-content active">
                  {(detail.mediaFiles || []).length === 0 ? <div className="empty-state">📭 暂无媒体文件记录</div> : (detail.mediaFiles || []).map((m, i) => (
                    <div className="media-item" key={i}>
                      <span className="media-icon">📎</span>
                      <span className="media-name">{m.fileName}</span>
                      <span className="media-size">{formatSize(m.size)}</span>
                      <span className="sub">{m.mimeType}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {pendingDeleteIds.length > 0 && (
        <div className="modal-overlay active" onClick={closeDelete}>
          <div className="del-modal" onClick={(e) => e.stopPropagation()}>
            <div className="del-header">
              <h3>⚠️ 确认删除</h3>
              <button className="modal-close" onClick={closeDelete}>✕</button>
            </div>
            <div className="del-body">
              <div className="del-title-preview">
                {pendingDeleteIds.length === 1 ? (sessions.find((s) => s.conversationId === pendingDeleteIds[0])?.title || pendingDeleteIds[0]) : `共 ${pendingDeleteIds.length} 条任务`}
              </div>
              <div className="del-manifest-title">将删除以下本地数据：</div>
              <div>
                {(pendingManifest.length ? pendingManifest : [{ type: "db", desc: "sessions DB 中的记录" }]).map((m, i) => (
                  <div className="del-manifest-item" key={i}><span className="icon">{m.type === "dir" ? "📁" : m.type === "db" ? "🗄️" : "📄"}</span>{m.desc}</div>
                ))}
              </div>
              <div className="del-warning">⚠️ 删除后该任务在 WorkBuddy 侧边栏会消失，工作目录代码文件不会被删除。</div>
              <div className="del-actions">
                <button className="del-cancel-btn" onClick={closeDelete}>取消</button>
                <button className="del-confirm-btn" onClick={executeDelete} disabled={loading}>{loading ? "删除中..." : "确认删除"}</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
