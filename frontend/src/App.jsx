import { useEffect, useMemo, useState } from "react";

import Pagination from "./components/Pagination";
import DeleteConfirmModal from "./components/DeleteConfirmModal";
import SessionDetailModal from "./components/SessionDetailModal";
import SessionHeader from "./components/SessionHeader";
import SessionStats from "./components/SessionStats";
import SessionTable from "./components/SessionTable";
import SessionToolbar from "./components/SessionToolbar";
import { PAGE_SIZE } from "./constants/session";
import { copyToClipboard, extractUserQuery } from "./utils/session";

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
  const [chatViewMode, setChatViewMode] = useState("basic");
  const [copiedId, setCopiedId] = useState(null);

  async function fetchChat(conversationId) {
    if (!conversationId) return;
    setChatLoading(true);
    setChatError("");
    try {
      const resp = await fetch(`/api/session/${encodeURIComponent(conversationId)}/chat?_t=${Date.now()}`, { cache: "no-store" });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data?.detail || `请求失败: ${resp.status}`);
      setChatMap((prev) => ({ ...prev, [conversationId]: data }));
    } catch (e) {
      setChatError(e.message || "加载对话失败");
    } finally {
      setChatLoading(false);
    }
  }

  function openDetail(session, nextTab = "info") {
    if (!session) return;
    setChatError("");
    setChatLoading(!chatMap[session.conversationId]);
    setDetail(session);
    setTab(nextTab);
  }


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
    if (!detail) return;
    if (chatMap[detail.conversationId]) return;
    fetchChat(detail.conversationId);
  }, [detail, chatMap]);

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

  async function exportSessions(ids) {
    if (!ids.length) {
      setError("请先勾选要导出的会话");
      return;
    }

    setLoading(true);
    setError("");
    try {
      const resp = await fetch("/api/export-chat", {
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
      const fileName = m?.[1] || `workbuddy-chat-${Date.now()}.zip`;
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

  async function exportSelected() {
    await exportSessions(Array.from(selectedIds));
  }

  async function exportOne(conversationId) {
    await exportSessions([conversationId]);
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

  const basicChatMessages = useMemo(() => {
    return currentChatMessages.filter((m) => (m.role === "user" || m.role === "assistant") && (m.text || "").trim());
  }, [currentChatMessages]);

  const basicChatText = useMemo(() => {
    return basicChatMessages.map((m) => {
      const role = m.role === "user" ? "user" : "assistant";
      let text = m.text || "(无内容)";
      if (m.role === "user") {
        const q = extractUserQuery(m.text || "");
        if (q) text = q;
      }
      return `【${role}】\n${text}`;
    }).join("\n\n---\n\n");
  }, [basicChatMessages]);

  return (
    <>
      <SessionHeader />

      <SessionStats stats={stats} />

      <SessionToolbar
        search={search}
        setSearch={(v) => { setSearch(v); setCurrentPage(1); }}
        statusFilter={statusFilter}
        setStatusFilter={(v) => { setStatusFilter(v); setCurrentPage(1); }}
        cwdFilter={cwdFilter}
        setCwdFilter={(v) => { setCwdFilter(v); setCurrentPage(1); }}
        dateFrom={dateFrom}
        setDateFrom={(v) => { setDateFrom(v); setCurrentPage(1); }}
        dateTo={dateTo}
        setDateTo={(v) => { setDateTo(v); setCurrentPage(1); }}
        clearFilters={clearFilters}
        refresh={() => { setCountdown(5); fetchSessions({ resetPage: true }); }}
        loading={loading}
        exportSelected={exportSelected}
        selectedCount={selectedIds.size}
        openDeleteSelected={() => openDelete(Array.from(selectedIds))}
        filteredCount={filteredRows.length}
        totalCount={sessions.length}
        autoRefreshing={autoRefreshing}
        countdown={countdown}
      />

      {error ? <div className="error">{error}</div> : null}

      <SessionTable
        pageRows={pageRows}
        selectedIds={selectedIds}
        allCheckedOnPage={allCheckedOnPage}
        toggleAll={toggleAll}
        toggleOne={toggleOne}
        sortBy={sortBy}
        openDetail={openDetail}
        exportOne={exportOne}
        openDelete={openDelete}
      />

      <Pagination currentPage={currentPage} totalPages={totalPages} setCurrentPage={setCurrentPage} />

      <SessionDetailModal
        detail={detail}
        setDetail={setDetail}
        tab={tab}
        setTab={setTab}
        openDelete={openDelete}
        chatMap={chatMap}
        chatLoading={chatLoading}
        chatError={chatError}
        chatViewMode={chatViewMode}
        setChatViewMode={setChatViewMode}
        basicChatMessages={basicChatMessages}
        basicChatText={basicChatText}
        copiedId={copiedId}
        setCopiedId={setCopiedId}
        copyToClipboard={copyToClipboard}
      />

      <DeleteConfirmModal
        pendingDeleteIds={pendingDeleteIds}
        closeDelete={closeDelete}
        sessions={sessions}
        pendingManifest={pendingManifest}
        executeDelete={executeDelete}
        loading={loading}
      />
    </>
  );
}
