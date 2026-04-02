export default function ShareResultModal({ result, closeShareResult, copyShareLink }) {
  if (!result) return null;

  const shareUrl = result.publicUrl || result.localUrl || "";

  return (
    <div className="modal-overlay active" onClick={closeShareResult}>
      <div className="share-modal" onClick={(e) => e.stopPropagation()}>
        <div className="share-modal-header">
          <h3>分享成功</h3>
          <button className="modal-close" onClick={closeShareResult}>✕</button>
        </div>
        <div className="share-modal-body">
          <div className="share-meta">已生成 {result.count || 0} 条会话的分享页面。</div>
          <div className="share-url-box mono">{shareUrl || "无可用链接"}</div>
          <div className="share-actions">
            {shareUrl ? (
              <button className="btn-outline" type="button" onClick={() => copyShareLink(shareUrl)}>复制链接</button>
            ) : null}
            {shareUrl ? (
              <a className="btn-outline" href={shareUrl} target="_blank" rel="noreferrer">打开链接</a>
            ) : null}
            <button className="del-cancel-btn" onClick={closeShareResult}>关闭</button>
          </div>
        </div>
      </div>
    </div>
  );
}
