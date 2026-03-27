import { useMemo, useState } from "react";

function formatStatus(status = "") {
  return status || "unknown";
}

export default function App() {
  const [loading, setLoading] = useState(false);
  const [sessions, setSessions] = useState([]);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [selected, setSelected] = useState(new Set());
  const [active, setActive] = useState(null);
  const [error, setError] = useState("");

  async function loadSessions() {
    setLoading(true);
    setError("");
    try {
      const resp = await fetch("/api/sessions");
      if (!resp.ok) throw new Error(`请求失败: ${resp.status}`);
      const data = await resp.json();
      setSessions(data.sessions || []);
      setSelected(new Set());
      setActive(null);
    } catch (e) {
      setError(e.message || "加载失败");
    } finally {
      setLoading(false);
    }
  }

  async function deleteByIds(ids) {
    if (!ids.length) return;
    const ok = window.confirm(`确认删除 ${ids.length} 条会话？`);
    if (!ok) return;

    setLoading(true);
    setError("");
    try {
      const resp = await fetch("/api/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids }),
      });
      if (!resp.ok) throw new Error(`删除失败: ${resp.status}`);
      const next = sessions.filter((x) => !ids.includes(x.conversationId));
      setSessions(next);
      setSelected(new Set());
      if (active && ids.includes(active.conversationId)) setActive(null);
    } catch (e) {
      setError(e.message || "删除失败");
    } finally {
      setLoading(false);
    }
  }

  const filtered = useMemo(() => {
    const keyword = q.trim().toLowerCase();
    return sessions
      .filter((s) => {
        if (status && (s.status || "").toLowerCase() !== status) return false;
        if (!keyword) return true;
        return [s.title, s.conversationId, s.cwd]
          .filter(Boolean)
          .some((v) => String(v).toLowerCase().includes(keyword));
      })
      .sort((a, b) => (b.createdAtTs || 0) - (a.createdAtTs || 0));
  }, [sessions, q, status]);

  const stats = useMemo(() => {
    const total = sessions.length;
    const completed = sessions.filter((s) => (s.status || "").toLowerCase() === "completed").length;
    const working = sessions.filter((s) => ["working", "inprogress"].includes((s.status || "").toLowerCase())).length;
    return { total, completed, working };
  }, [sessions]);

  const statusList = useMemo(() => {
    const set = new Set(sessions.map((s) => (s.status || "").toLowerCase()).filter(Boolean));
    return [...set].sort();
  }, [sessions]);

  function toggleOne(id) {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelected(next);
  }

  return (
    <div className="page">
      <header className="header">
        <h1>WorkBuddy 会话管理器</h1>
        <div className="actions">
          <button onClick={loadSessions} disabled={loading}>{loading ? "处理中..." : "刷新数据"}</button>
          <button className="danger" onClick={() => deleteByIds(Array.from(selected))} disabled={loading || selected.size === 0}>
            删除已选({selected.size})
          </button>
        </div>
      </header>

      <section className="stats">
        <div><strong>{stats.total}</strong><span>总任务</span></div>
        <div><strong>{stats.completed}</strong><span>已完成</span></div>
        <div><strong>{stats.working}</strong><span>进行中</span></div>
      </section>

      <section className="filters">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="搜索标题 / ID / 目录" />
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">全部状态</option>
          {statusList.map((s) => <option value={s} key={s}>{s}</option>)}
        </select>
      </section>

      {error ? <div className="error">{error}</div> : null}

      <section className="main">
        <div className="tableWrap">
          <table>
            <thead>
              <tr>
                <th></th>
                <th>标题</th>
                <th>状态</th>
                <th>工作目录</th>
                <th>创建时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((s) => (
                <tr key={s.conversationId}>
                  <td>
                    <input type="checkbox" checked={selected.has(s.conversationId)} onChange={() => toggleOne(s.conversationId)} />
                  </td>
                  <td>
                    <button className="linkBtn" onClick={() => setActive(s)}>{s.title || "(无标题)"}</button>
                    <div className="sub">{s.conversationId}</div>
                  </td>
                  <td>{formatStatus(s.status)}</td>
                  <td><div className="cwd">{s.cwd || "-"}</div></td>
                  <td>{s.createdAt || "-"}</td>
                  <td>
                    <button className="danger ghost" onClick={() => deleteByIds([s.conversationId])}>删除</button>
                  </td>
                </tr>
              ))}
              {!filtered.length ? (
                <tr>
                  <td colSpan={6} className="empty">暂无数据，点击“刷新数据”加载</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>

        <aside className="detail">
          {!active ? (
            <div className="empty">点击标题查看详情</div>
          ) : (
            <div>
              <h3>{active.title || "(无标题)"}</h3>
              <p><strong>ID:</strong> {active.conversationId}</p>
              <p><strong>状态:</strong> {active.status || "-"}</p>
              <p><strong>目录:</strong> {active.cwd || "-"}</p>
              <p><strong>Todos:</strong> {active.todos?.length || 0}</p>
              <p><strong>文件变更:</strong> {active.fileChanges?.length || 0}</p>
              <p><strong>媒体文件:</strong> {active.mediaFiles?.length || 0}</p>
            </div>
          )}
        </aside>
      </section>
    </div>
  );
}
