import { Fragment, useState } from "react";


import { escHtml, extractUserQuery, formatSize, prettyJson } from "../utils/session";

export default function SessionDetailModal({
  detail,
  setDetail,
  tab,
  setTab,
  openDelete,
  chatMap,
  chatLoading,
  chatError,
  chatViewMode,
  setChatViewMode,
  basicChatMessages,
  basicChatText,
  copiedId,
  setCopiedId,
  copyToClipboard,
  workspaceData,
  workspaceLoading,
  workspaceError,
}) {
  const [mediaActionKey, setMediaActionKey] = useState("");

  function buildOpenFileHref(filePath) {
    return `/api/local/open-file?path=${encodeURIComponent(filePath || "")}`;
  }


  async function handleMediaAction(action, filePath) {
    if (!filePath) return;
    const actionKey = `${action}:${filePath}`;
    setMediaActionKey(actionKey);
    try {
      const resp = await fetch(`/api/local/${action}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: filePath }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data?.detail || `操作失败: ${resp.status}`);
    } catch (e) {
      window.alert(e.message || "操作失败");
    } finally {
      setMediaActionKey((prev) => (prev === actionKey ? "" : prev));
    }
  }


  if (!detail) return null;

  const currentChat = chatMap[detail.conversationId] || null;

  const currentChatMessages = currentChat?.messages || [];
  const chatCount = currentChat?.messageCount ?? (chatLoading ? "..." : 0);
  const firstChatTime = currentChatMessages[0]?.createdAt || "-";
  const lastChatTime = currentChatMessages[currentChatMessages.length - 1]?.createdAt || "-";

  function formatModelMeta(message) {
    const name = (message?.modelName || "").trim();
    const id = (message?.modelId || "").trim();
    const mode = (message?.mode || "").trim();
    const model = name || id;
    if (!model && !mode) return "";
    if (model && mode) return `${model} / ${mode}`;
    return model || mode;
  }

  function flattenWorkspaceFiles(nodes, out = []) {
    if (!Array.isArray(nodes) || nodes.length === 0) return out;
    nodes.forEach((node) => {
      if (node?.type === "file") {
        out.push(node);
        return;
      }
      flattenWorkspaceFiles(node?.children || [], out);
    });
    return out;
  }

  const workspaceFiles = flattenWorkspaceFiles(workspaceData?.tree?.children || []).sort((a, b) =>
    String(a?.relativePath || "").localeCompare(String(b?.relativePath || ""), "zh-CN", { sensitivity: "base" })
  );

  return (

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
          <div className={`modal-tab ${tab === "chat" ? "active" : ""}`} onClick={() => setTab("chat")}>💬 对话 ({chatCount})</div>
          <div className={`modal-tab ${tab === "todos" ? "active" : ""}`} onClick={() => setTab("todos")}>✅ Todos ({detail.todos?.length || 0})</div>
          <div className={`modal-tab ${tab === "files" ? "active" : ""}`} onClick={() => setTab("files")}>📁 文件变更 ({detail.fileChanges?.length || 0})</div>
          <div className={`modal-tab ${tab === "related" ? "active" : ""}`} onClick={() => setTab("related")}>🔗 关联对话 ({detail.related?.length || 0})</div>
          <div className={`modal-tab ${tab === "media" ? "active" : ""}`} onClick={() => setTab("media")}>🖼 媒体文件 ({detail.mediaFiles?.length || 0})</div>
          <div className={`modal-tab ${tab === "workspace" ? "active" : ""}`} onClick={() => setTab("workspace")}>🗂 工作目录文件 ({workspaceData?.fileCount ?? "..."})</div>

        </div>

        <div className="modal-body">
          {tab === "info" && (
            <div className="tab-content active">
              <div className="info-grid">
                <div className="info-item"><div className="info-label">对话 ID</div><div className="info-value mono">{detail.conversationId}</div></div>
                <div className="info-item"><div className="info-label">状态</div><div className="info-value">{detail.status}</div></div>
                <div className="info-item"><div className="info-label">创建时间</div><div className="info-value">{detail.createdAt}</div></div>
                <div className="info-item"><div className="info-label">更新时间</div><div className="info-value">{detail.updatedAt}</div></div>
                <div className="info-item"><div className="info-label">逻辑删除时间</div><div className="info-value">{detail.deletedAt || "-"}</div></div>
                <div className="info-item full"><div className="info-label">工作目录</div><div className="info-value mono">{detail.cwd} {detail.cwdExists ? "✅" : "❌"}</div></div>

              </div>
            </div>
          )}

          {tab === "chat" && (
            <div className="tab-content active">
              {chatLoading ? <div className="empty-state">对话加载中...</div> : null}
              {!chatLoading && chatError ? <div className="error">{chatError}</div> : null}
              {!chatLoading && !chatError && !currentChatMessages.length ? <div className="empty-state">📭 暂无对话记录</div> : null}
              {!chatLoading && !chatError && currentChatMessages.length > 0 && (
                <>
                  <div className="chat-toolbar">
                    <div className="chat-view-toggle">
                      <button className={chatViewMode === "basic" ? "active" : ""} onClick={() => setChatViewMode("basic")}>基础对话</button>
                      <button className={chatViewMode === "full" ? "active" : ""} onClick={() => setChatViewMode("full")}>完整对话</button>
                    </div>
                    {chatViewMode === "basic" && basicChatMessages.length > 0 && (
                      <button
                        className="btn-copy-all"
                        onClick={async () => {
                          await copyToClipboard(basicChatText);
                          setCopiedId("all");
                          setTimeout(() => setCopiedId(null), 1500);
                        }}
                      >{copiedId === "all" ? "已复制" : "复制全部对话"}</button>
                    )}
                  </div>
                  <div className="chat-summary">
                    对话时间：{firstChatTime} ~ {lastChatTime}
                    {chatViewMode === "basic"
                      ? `（基础对话 ${basicChatMessages.length} 条）`
                      : `（完整对话 ${currentChatMessages.length} 条）`}
                  </div>
                </>
              )}

              {chatViewMode === "basic" && !chatLoading && !chatError && basicChatMessages.map((m, i) => {
                const userQueryText = m.role === "user" ? extractUserQuery(m.text || "") : "";
                const modelMeta = formatModelMeta(m);
                const metaBase = `${m.role || "unknown"} · ${m.id} · ${m.createdAt || "-"}${modelMeta ? ` · ${modelMeta}` : ""}`;
                const displayText = userQueryText || m.text;

                const msgKey = m.id || `${m.role || "unknown"}-${i}`;
                const toolCallEvents = (m.toolEvents || []).filter((evt) => evt?.type === "tool-call");

                return (
                  <div className={`chat-item role-${m.role || "unknown"}`} key={msgKey}>
                    <div className="chat-meta">
                      <span>{metaBase}</span>
                      <button
                        className="btn-copy"
                        onClick={async () => {
                          await copyToClipboard(displayText);
                          setCopiedId(msgKey);
                          setTimeout(() => setCopiedId(null), 1500);
                        }}
                      >{copiedId === msgKey ? "已复制" : "复制"}</button>
                    </div>
                    <pre className={`chat-text ${userQueryText ? "chat-text-user-query" : ""}`}>{displayText}</pre>
                    {toolCallEvents.length > 0 && (
                      <div className="basic-tool-call-list">
                        {toolCallEvents.map((evt, ti) => (
                          <div className="basic-tool-call" key={`${msgKey}-basic-tool-${ti}`}>
                            工具调用 · {evt.toolName || "-"}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}


              {chatViewMode === "full" && !chatLoading && !chatError && currentChatMessages.map((m, i) => {
                const userQueryText = m.role === "user" ? extractUserQuery(m.text || "") : "";
                const modelMeta = formatModelMeta(m);
                const metaBase = `${m.role || "unknown"} · ${m.id} · ${m.createdAt || "-"}${modelMeta ? ` · ${modelMeta}` : ""}`;
                const keyBase = m.id || `${m.role || "unknown"}-${i}`;


                if (userQueryText) {
                  return (
                    <Fragment key={`full-${keyBase}`}>
                      <div className={`chat-item role-${m.role || "unknown"}`}>
                        <div className="chat-meta">{metaBase} · 原始</div>
                        <pre className="chat-text">{m.text}</pre>
                      </div>
                      <div className={`chat-item role-${m.role || "unknown"}`}>
                        <div className="chat-meta">{metaBase} · 实际</div>
                        <pre className="chat-text chat-text-user-query">{userQueryText}</pre>
                      </div>
                    </Fragment>
                  );
                }

                return (
                  <div className={`chat-item role-${m.role || "unknown"}`} key={keyBase}>
                    <div className="chat-meta">{metaBase}</div>
                    {m.text ? <pre className="chat-text">{m.text}</pre> : null}
                    {(m.toolEvents || []).length > 0 && (
                      <div className="tool-event-list">
                        {(m.toolEvents || []).map((evt, ti) => (
                          <div className="tool-event" key={`${keyBase}-tool-${ti}`}>
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
                );
              })}
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
              {(detail.mediaFiles || []).length === 0 ? <div className="empty-state">📭 暂无媒体文件记录</div> : (detail.mediaFiles || []).map((m, i) => {
                const filePath = m.filePath || "";
                const locateKey = `locate-file:${filePath}`;
                const disabled = !filePath;

                return (
                  <div className="media-item" key={i}>
                    <div className="media-main">
                      <span className="media-icon">📎</span>
                      <div className="media-info">
                        <div className="media-name">{m.fileName || "-"}</div>
                        <div className="media-meta-row">
                          <span className="media-size">{formatSize(m.size)}</span>
                          <span className="sub">{m.mimeType || "-"}</span>
                        </div>
                        {filePath ? <div className="media-path mono">{filePath}</div> : <div className="media-path sub">未记录本地路径</div>}
                      </div>
                    </div>
                    <div className="media-actions">
                      {disabled ? (
                        <button className="btn-outline" disabled>打开文件</button>
                      ) : (
                        <a className="btn-outline" href={buildOpenFileHref(filePath)} target="_blank" rel="noreferrer">
                          打开文件
                        </a>
                      )}


                      <button className="btn-outline" disabled={disabled || mediaActionKey === locateKey} onClick={() => handleMediaAction("locate-file", filePath)}>
                        {mediaActionKey === locateKey ? "定位中..." : "定位文件"}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {tab === "workspace" && (
            <div className="tab-content active">
              {workspaceLoading ? <div className="empty-state">工作目录文件加载中...</div> : null}
              {!workspaceLoading && workspaceError ? <div className="error">{workspaceError}</div> : null}
              {!workspaceLoading && !workspaceError && !detail.cwd ? <div className="empty-state">📭 当前会话无工作目录</div> : null}
              {!workspaceLoading && !workspaceError && detail.cwd && !workspaceData ? <div className="empty-state">📭 暂无工作目录文件数据</div> : null}
              {!workspaceLoading && !workspaceError && workspaceData && (
                <>
                  <div className="chat-summary">
                    工作目录：{workspaceData.cwd || "-"}（文件 {workspaceData.fileCount || 0} 个，目录 {workspaceData.dirCount || 0} 个）
                  </div>
                  <div className="workspace-tree">
                    {workspaceFiles.length === 0 ? <div className="empty-state">📭 工作目录为空</div> : workspaceFiles.map((node, i) => {
                      const filePath = node?.filePath || "";
                      const locateKey = `locate-file:${filePath}`;
                      const key = `${node?.relativePath || node?.name || "file"}-${i}`;
                      return (
                        <div className="workspace-row" key={key}>
                          <div className="workspace-line mono">
                            <span className="workspace-name">{node?.name || "-"}</span>
                            <span className="workspace-rel">{node?.relativePath || "-"}</span>
                            <span className="workspace-size">{formatSize(node?.size || 0)}</span>
                          </div>
                          <div className="media-actions">
                            {!filePath ? (
                              <button className="btn-outline" disabled>打开文件</button>
                            ) : (
                              <a className="btn-outline" href={buildOpenFileHref(filePath)} target="_blank" rel="noreferrer">打开文件</a>
                            )}
                            <button className="btn-outline" disabled={!filePath || mediaActionKey === locateKey} onClick={() => handleMediaAction("locate-file", filePath)}>
                              {mediaActionKey === locateKey ? "定位中..." : "定位文件"}
                            </button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </>
              )}
            </div>
          )}

        </div>

      </div>
    </div>
  );
}
