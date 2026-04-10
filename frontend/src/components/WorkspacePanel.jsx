import { useEffect, useMemo, useState } from "react";

export default function WorkspacePanel() {
  const [workspaces, setWorkspaces] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [filterType, setFilterType] = useState("");
  const [expandedCwd, setExpandedCwd] = useState(null);
  const [deletingCwd, setDeletingCwd] = useState(null);
  const [deletingSession, setDeletingSession] = useState(null); // conversationId

  async function fetchWorkspaces() {
    setLoading(true);
    setError("");
    try {
      const resp = await fetch(`/api/workspaces?_t=${Date.now()}`, { cache: "no-store" });
      if (!resp.ok) throw new Error(`请求失败: ${resp.status}`);
      const data = await resp.json();
      setWorkspaces(data.workspaces || []);
    } catch (e) {
      setError(e.message || "加载工作空间失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { fetchWorkspaces(); }, []);

  async function deleteWorkspace(cwd) {
    if (!cwd) return;
    if (!window.confirm(`确认删除工作目录？\n\n路径：${cwd}\n\n⚠️ 该操作将删除磁盘上的工作目录文件，不可恢复！`)) return;
    setDeletingCwd(cwd);
    try {
      const resp = await fetch("/api/workspace", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cwd }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data?.detail || "删除失败");
      setWorkspaces((prev) => prev.filter((w) => w.cwd !== cwd));
      if (expandedCwd === cwd) setExpandedCwd(null);
    } catch (e) {
      window.alert(e.message || "删除失败");
    } finally {
      setDeletingCwd(null);
    }
  }

  async function deleteSession(conversationId, cwd) {
    if (!conversationId) return;
    if (!window.confirm(`确认删除此对话？\n\n该操作将从数据库和本地彻底删除对话记录，不可恢复！`)) return;
    setDeletingSession(conversationId);
    try {
      const resp = await fetch("/api/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids: [conversationId] }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok || !data.success) throw new Error(data?.detail || "删除失败");
      // 从本地状态中移除该会话，并重新计算 canDelete
      setWorkspaces((prev) => prev.map((w) => {
        if (w.cwd !== cwd) return w;
        const newSessions = w.sessions.filter((s) => s.conversationId !== conversationId);
        return {
          ...w,
          sessions: newSessions,
          totalSessions: newSessions.length,
          activeSessions: newSessions.filter((s) => !s.isDeleted).length,
          deletedSessions: newSessions.filter((s) => s.isDeleted).length,
          canDelete: newSessions.length === 0,
        };
      }));
    } catch (e) {
      window.alert(e.message || "删除失败");
    } finally {
      setDeletingSession(null);
    }
  }

  const filteredWorkspaces = useMemo(() => {
    const q = search.trim().toLowerCase();
    return workspaces.filter((w) => {
      const cwd = (w.cwd || "").toLowerCase();
      if (q && !cwd.includes(q)) return false;
      if (filterType === "active" && w.activeSessions === 0) return false;
      if (filterType === "orphan" && w.activeSessions > 0) return false;
      return true;
    });
  }, [workspaces, search, filterType]);

  const stats = useMemo(() => {
    const total = workspaces.length;
    const active = workspaces.filter((w) => w.activeSessions > 0).length;
    const orphan = workspaces.filter((w) => w.activeSessions === 0).length;
    const missing = workspaces.filter((w) => !w.cwdExists).length;
    return { total, active, orphan, missing };
  }, [workspaces]);

  function tsToText(ts) {
    if (!ts) return "-";
    const d = new Date(ts);
    if (isNaN(d.getTime())) return "-";
    return d.toLocaleString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
  }

  return (
    <div className="config-page">
      <div className="config-toolbar">
        <div className="config-title-wrap">
          <h2>工作空间</h2>
          <span className="config-tag">共 {stats.total} 个工作空间</span>
        </div>
        <div className="config-actions">
          <button onClick={fetchWorkspaces} disabled={loading}>{loading ? "加载中..." : "刷新"}</button>
        </div>
      </div>

      <div className="stats" style={{ marginBottom: 12 }}>
        <div className="stat"><div className="num">{stats.total}</div><div className="lbl">总工作空间</div></div>
        <div className="stat"><div className="num c-ok">{stats.active}</div><div className="lbl">有活跃会话</div></div>
        <div className="stat"><div className="num c-err">{stats.orphan}</div><div className="lbl">无活跃会话</div></div>
        <div className="stat"><div className="num c-run">{stats.missing}</div><div className="lbl">目录缺失</div></div>
      </div>

      <div className="toolbar" style={{ marginBottom: 12 }}>
        <input type="text" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="🔍 搜索工作目录路径..." />
        <select value={filterType} onChange={(e) => setFilterType(e.target.value)}>
          <option value="">全部工作空间</option>
          <option value="active">✅ 有活跃会话</option>
          <option value="orphan">🗑 无活跃会话</option>
        </select>
      </div>

      {error ? <div className="error">{error}</div> : null}

      <div className="ws-list">
        {filteredWorkspaces.length === 0 && !loading ? (
          <div className="empty-state">📭 暂无工作空间数据</div>
        ) : null}
        {filteredWorkspaces.map((w) => {
          const spaceName = (w.cwd || "").split(/[\\/]/).filter(Boolean).pop() || w.cwd;
          const isExpanded = expandedCwd === w.cwd;
          const canDelete = w.canDelete;

          return (
            <div className="ws-item" key={w.cwd}>
              <div className="ws-header" onClick={() => setExpandedCwd(isExpanded ? null : w.cwd)}>
                <div className="ws-info">
                  <div className="ws-name">
                    {w.cwdExists ? "✅" : "❌"} {spaceName}
                  </div>
                  <div className="ws-path sub">{w.cwd}</div>
                  <div className="ws-badges">
                    <span className="ws-badge ws-badge-active">活跃 {w.activeSessions}</span>
                    {w.deletedSessions > 0 ? <span className="ws-badge ws-badge-deleted">已删除 {w.deletedSessions}</span> : null}
                    <span className="ws-badge ws-badge-total">共 {w.totalSessions}</span>
                  </div>
                </div>
                <div className="ws-actions" onClick={(e) => e.stopPropagation()}>
                  {canDelete ? (
                    <button
                      className="btn-danger"
                      disabled={deletingCwd === w.cwd}
                      onClick={() => deleteWorkspace(w.cwd)}
                    >
                      {deletingCwd === w.cwd ? "删除中..." : "🗑 删除目录"}
                    </button>
                  ) : (
                    <button className="btn-outline" disabled title="该工作目录下仍有会话记录（含逻辑删除），请先彻底删除所有关联会话">🗑 删除目录</button>
                  )}
                  <span className="ws-expand-icon">{isExpanded ? "▼" : "▶"}</span>
                </div>
              </div>

              {isExpanded && (
                <div className="ws-sessions">
                  {w.sessions.length === 0 ? (
                    <div className="empty-state">📭 无关联会话</div>
                  ) : (
                    <table className="ws-session-table">
                      <thead>
                        <tr>
                          <th>标题</th>
                          <th style={{ width: 90 }}>状态</th>
                          <th style={{ width: 80 }}>逻辑删除</th>
                          <th style={{ width: 140 }}>创建时间</th>
                          <th style={{ width: 70, textAlign: "center" }}>操作</th>
                        </tr>
                      </thead>
                      <tbody>
                        {w.sessions.map((s) => (
                          <tr key={s.conversationId} className={s.isDeleted ? "ws-row-deleted" : ""}>
                            <td>
                              <div className="ws-session-title">{s.title || "(无标题)"}</div>
                              <div className="sub">{(s.conversationId || "").slice(0, 16)}...</div>
                            </td>
                            <td><span style={{ fontSize: 12 }}>{s.status}</span></td>
                            <td>{s.isDeleted ? <span className="c-err">🗑 已删除</span> : <span className="c-ok">正常</span>}</td>
                            <td className="sub">{tsToText(s.createdAt)}</td>
                            <td style={{ textAlign: "center" }}>
                              <button
                                className="btn-danger"
                                disabled={deletingSession === s.conversationId}
                                onClick={() => deleteSession(s.conversationId, w.cwd)}
                              >
                                {deletingSession === s.conversationId ? "删除中..." : "删除"}
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
