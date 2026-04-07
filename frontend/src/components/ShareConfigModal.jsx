import { useEffect, useMemo, useRef, useState } from "react";
import JSZip from "jszip";

function formatSize(size = 0) {
  if (size >= 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)} MB`;
  if (size >= 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${size} B`;
}

async function packFolderToZip(files) {
  // files: FileList 中 webkitRelativePath 带文件夹前缀的 File 列表
  const zip = new JSZip();
  for (const file of files) {
    const rel = file.webkitRelativePath || file.name;
    const buf = await file.arrayBuffer();
    zip.file(rel, buf);
  }
  const blob = await zip.generateAsync({ type: "blob", compression: "DEFLATE" });
  // 取文件夹名作为 zip 文件名
  const folderName = (files[0]?.webkitRelativePath || "folder").split("/")[0];
  return new File([blob], `${folderName}.zip`, { type: "application/zip" });
}

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
  // uploadedFiles: Array<{ id, file, label, packing }>
  const [uploadedFiles, setUploadedFiles] = useState([]);
  const [packing, setPacking] = useState(false);

  const fileInputRef = useRef(null);
  const folderInputRef = useRef(null);

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

  function removeUpload(id) {
    setUploadedFiles((prev) => prev.filter((f) => f.id !== id));
  }

  async function onPickFiles(e) {
    const files = Array.from(e.target.files || []);
    e.target.value = "";
    if (!files.length) return;
    const entries = files.map((f) => ({
      id: `${f.name}-${f.size}-${f.lastModified}-${Math.random()}`,
      file: f,
      label: f.name,
      packing: false,
    }));
    setUploadedFiles((prev) => [...prev, ...entries]);
  }

  async function onPickFolder(e) {
    const files = Array.from(e.target.files || []);
    e.target.value = "";
    if (!files.length) return;

    const folderName = (files[0]?.webkitRelativePath || "folder").split("/")[0];
    const tempId = `folder-${folderName}-${Date.now()}`;

    // 先占位显示打包中
    setUploadedFiles((prev) => [
      ...prev,
      { id: tempId, file: null, label: `${folderName}/ (打包中…)`, packing: true },
    ]);
    setPacking(true);

    try {
      const zipFile = await packFolderToZip(files);
      setUploadedFiles((prev) =>
        prev.map((item) =>
          item.id === tempId
            ? { id: tempId, file: zipFile, label: `${folderName}.zip（文件夹打包）`, packing: false }
            : item
        )
      );
    } catch {
      setUploadedFiles((prev) => prev.filter((item) => item.id !== tempId));
    } finally {
      setPacking(false);
    }
  }

  const readyFiles = uploadedFiles.filter((f) => f.file && !f.packing).map((f) => f.file);

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

          {/* 已有媒体文件 */}
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
                      <span className="sub">{item.title} · {item.mimeType || "-"} · {formatSize(item.size)}</span>
                    </span>
                  </label>
                ))}
              </div>
            )}
          </div>

          {/* 上传文件 / 文件夹 */}
          <div className="share-config-block">
            <div className="share-config-title">上传文件或文件夹（可不传）</div>
            <div className="upload-btn-row">
              <button
                type="button"
                className="upload-pick-btn"
                onClick={() => fileInputRef.current?.click()}
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="14" height="14">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                  <path d="M14 2v6h6M12 18v-6M9 15l3-3 3 3" />
                </svg>
                选择文件
              </button>
              <button
                type="button"
                className="upload-pick-btn"
                onClick={() => folderInputRef.current?.click()}
                disabled={packing}
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="14" height="14">
                  <path d="M3 7h5l2 2h11v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z" />
                  <path d="M12 13v4M10 15l2-2 2 2" />
                </svg>
                选择文件夹
                {packing && <span style={{ marginLeft: 4, color: "#f6ad55" }}>打包中…</span>}
              </button>
              {/* 隐藏的 input */}
              <input
                ref={fileInputRef}
                type="file"
                multiple
                style={{ display: "none" }}
                onChange={onPickFiles}
              />
              <input
                ref={folderInputRef}
                type="file"
                webkitdirectory=""
                style={{ display: "none" }}
                onChange={onPickFolder}
              />
            </div>

            {/* 已选列表 */}
            {uploadedFiles.length > 0 && (
              <div className="upload-file-list">
                {uploadedFiles.map((item) => (
                  <div key={item.id} className="upload-file-item">
                    <span className="upload-file-icon">
                      {item.packing ? (
                        <svg viewBox="0 0 24 24" fill="none" stroke="#f6ad55" strokeWidth="2" width="14" height="14">
                          <path d="M3 7h5l2 2h11v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z" />
                        </svg>
                      ) : item.file?.type === "application/zip" && item.label.includes("文件夹打包") ? (
                        <svg viewBox="0 0 24 24" fill="none" stroke="#68d391" strokeWidth="2" width="14" height="14">
                          <path d="M3 7h5l2 2h11v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z" />
                        </svg>
                      ) : (
                        <svg viewBox="0 0 24 24" fill="none" stroke="#90cdf4" strokeWidth="2" width="14" height="14">
                          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                          <path d="M14 2v6h6" />
                        </svg>
                      )}
                    </span>
                    <span className="upload-file-name">{item.label}</span>
                    {!item.packing && item.file && (
                      <span className="upload-file-size">{formatSize(item.file.size)}</span>
                    )}
                    <button
                      type="button"
                      className="upload-file-remove"
                      onClick={() => removeUpload(item.id)}
                      title="移除"
                    >✕</button>
                  </div>
                ))}
              </div>
            )}
            <div className="small" style={{ marginTop: 6 }}>
              已选 {uploadedFiles.length} 项（{readyFiles.length} 个就绪）
              {packing && <span style={{ color: "#f6ad55", marginLeft: 6 }}>文件夹打包中，请稍候…</span>}
            </div>
          </div>

          <div className="share-actions">
            <button
              className="btn-outline"
              type="button"
              disabled={packing}
              onClick={() =>
                submitShare({
                  ids: config.ids,
                  selectedMediaPaths: Array.from(selectedPaths),
                  uploadFiles: readyFiles,
                })
              }
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
