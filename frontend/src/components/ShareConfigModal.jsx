import { useEffect, useMemo, useState } from "react";

export default function ShareConfigModal({
  config,
  sessions,
  closeModal,
  submitShare,
  title = "分享配置",
  description = "本次将分享 {count} 条会话。可选媒体文件，也可单独上传。",

  submitText = "生成分享链接",
}) {

  if (!config) return null;

  const [selectedPaths, setSelectedPaths] = useState(new Set());
  const [uploadedFiles, setUploadedFiles] = useState([]);

  const mediaOptions = useMemo(() => {
    const byId = new Map((sessions || []).map((s) => [s.conversationId, s]));
    const out = [];
    const usedPath = new Set();

    (config.ids || []).forEach((cid) => {
      const session = byId.get(cid);
      const medias = session?.mediaFiles || [];
      medias.forEach((m, idx) => {
        const filePath = String(m?.filePath || "").trim();
        if (!filePath || usedPath.has(filePath)) return;
        usedPath.add(filePath);
        out.push({
          key: `${cid}:${idx}`,
          conversationId: cid,
          title: session?.title || cid,
          filePath,
          fileName: m?.fileName || filePath.split(/[\\/]/).pop() || "unknown",
          size: Number(m?.size || 0),
          mimeType: m?.mimeType || "",
        });
      });
    });

    return out;
  }, [config.ids, sessions]);

  useEffect(() => {
    setSelectedPaths(new Set());
    setUploadedFiles([]);
  }, [config.ids]);

  function togglePath(path) {
    setSelectedPaths((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  }

  function onPickFiles(e) {
    const files = Array.from(e.target.files || []);
    setUploadedFiles(files);
  }

  const metaText = String(description || "").replace("{count}", String(config.ids.length));

  return (
    <div className="modal-overlay active" onClick={closeModal}>

      <div className="share-config-modal" onClick={(e) => e.stopPropagation()}>
        <div className="share-modal-header">
          <h3>{title}</h3>
          <button className="modal-close" onClick={closeModal}>✕</button>
        </div>
        <div className="share-modal-body">
          <div className="share-meta">{metaText}</div>



          <div className="share-config-block">
            <div className="share-config-title">选择已有媒体文件（可不选）</div>
            {mediaOptions.length === 0 ? (
              <div className="small">所选会话暂无可选媒体文件</div>
            ) : (
              <div className="share-media-options">
                {mediaOptions.map((item) => (
                  <label key={item.key} className="share-media-option">
                    <input
                      type="checkbox"
                      checked={selectedPaths.has(item.filePath)}
                      onChange={() => togglePath(item.filePath)}
                    />
                    <span className="share-media-text">
                      <span className="share-media-name">{item.fileName}</span>
                      <span className="sub">{item.title} · {item.mimeType || "-"} · {item.size || 0}B</span>
                    </span>
                  </label>
                ))}
              </div>
            )}
          </div>

          <div className="share-config-block">
            <div className="share-config-title">上传媒体文件（可不传）</div>
            <input type="file" multiple onChange={onPickFiles} />
            <div className="small">已选择 {uploadedFiles.length} 个文件</div>
          </div>

          <div className="share-actions">
            <button
              className="btn-outline"
              type="button"
              onClick={() => submitShare({
                ids: config.ids,
                selectedMediaPaths: Array.from(selectedPaths),
                uploadFiles: uploadedFiles,
              })}
            >
              {submitText}

            </button>
            <button className="del-cancel-btn" type="button" onClick={closeModal}>取消</button>
          </div>
        </div>
      </div>
    </div>
  );
}
