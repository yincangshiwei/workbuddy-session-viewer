import { STATUS_COLORS } from "../constants/session";

export default function SessionTable({
  pageRows,
  selectedIds,
  allCheckedOnPage,
  toggleAll,
  toggleOne,
  sortBy,
  openDetail,
  exportOne,
  shareOne,
  openDelete,
}) {

  return (
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


            <th style={{ width: 200, textAlign: "center" }}>操作</th>
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
                onDoubleClick={() => openDetail(s, "info")}
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
                  {s.deletedAt ? <div className="small c-err">🗑 逻辑删除：{s.deletedAt}</div> : null}

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
                  <button className="btn-outline" onClick={(e) => { e.stopPropagation(); openDetail(s, "info"); }}>详情</button>
                  <button className="btn-outline" onClick={(e) => { e.stopPropagation(); exportOne(s.conversationId); }}>导出</button>
                  <button className="btn-outline" onClick={(e) => { e.stopPropagation(); shareOne(s.conversationId); }}>分享</button>
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
  );
}
