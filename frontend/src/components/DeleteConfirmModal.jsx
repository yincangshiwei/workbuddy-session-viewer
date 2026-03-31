export default function DeleteConfirmModal({
  pendingDeleteIds,
  closeDelete,
  sessions,
  pendingManifest,
  executeDelete,
  loading,
}) {
  if (!pendingDeleteIds.length) return null;

  return (
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
  );
}
