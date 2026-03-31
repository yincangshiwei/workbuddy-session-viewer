import { useEffect, useMemo, useState } from "react";

function createEmptyModel() {
  return {
    id: "",
    name: "",
    vendor: "Custom",
    url: "",
    apiKey: "",
    maxInputTokens: 262144,
    maxOutputTokens: 65536,
    supportsToolCall: true,
    supportsImages: true,
    supportsReasoning: true,
  };
}

function normalizeModel(item) {
  const safe = item && typeof item === "object" ? item : {};
  return {
    ...createEmptyModel(),
    ...safe,
    maxInputTokens: Number(safe.maxInputTokens ?? 0) || 0,
    maxOutputTokens: Number(safe.maxOutputTokens ?? 0) || 0,
    supportsToolCall: !!safe.supportsToolCall,
    supportsImages: !!safe.supportsImages,
    supportsReasoning: !!safe.supportsReasoning,
  };
}

export default function ModelConfigPanel() {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [config, setConfig] = useState({ models: [] });
  const [models, setModels] = useState([]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [showApiKey, setShowApiKey] = useState(false);

  async function loadConfig() {
    setLoading(true);
    setError("");
    setNotice("");
    try {
      const resp = await fetch(`/api/config/models?_t=${Date.now()}`, { cache: "no-store" });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data?.detail || `请求失败: ${resp.status}`);
      const nextModels = Array.isArray(data?.models) ? data.models.map(normalizeModel) : [];
      setConfig(data?.config && typeof data.config === "object" ? data.config : { models: [] });
      setModels(nextModels);
      setSelectedIndex((prev) => {
        if (!nextModels.length) return 0;
        return Math.min(prev, nextModels.length - 1);
      });
    } catch (e) {
      setError(e.message || "读取模型配置失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadConfig();
  }, []);

  const currentModel = useMemo(() => {
    if (!models.length) return null;
    return models[Math.max(0, Math.min(selectedIndex, models.length - 1))];
  }, [models, selectedIndex]);

  function updateCurrent(patch) {
    if (!currentModel) return;
    setModels((prev) => prev.map((item, idx) => (idx === selectedIndex ? { ...item, ...patch } : item)));
  }

  function addModel() {
    const next = [...models, createEmptyModel()];
    setModels(next);
    setSelectedIndex(next.length - 1);
    setNotice("");
  }

  function removeCurrent() {
    if (!models.length) return;
    const next = models.filter((_, idx) => idx !== selectedIndex);
    setModels(next);
    setSelectedIndex((prev) => Math.max(0, Math.min(prev - 1, next.length - 1)));
    setNotice("");
  }

  async function saveConfig() {
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const payload = {
        config: { ...config, models },
        models,
      };
      const resp = await fetch("/api/config/models", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await resp.json();
      if (!resp.ok || !data?.success) throw new Error(data?.detail || data?.error || `保存失败: ${resp.status}`);
      const nextModels = Array.isArray(data?.models) ? data.models.map(normalizeModel) : models;
      setConfig(data?.config && typeof data.config === "object" ? data.config : { models: nextModels });
      setModels(nextModels);
      setNotice("模型配置已保存");
    } catch (e) {
      setError(e.message || "保存模型配置失败");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="config-page">
      <div className="config-toolbar">
        <div className="config-title-wrap">
          <h2>模型配置管理</h2>
          <span className="config-tag">仅支持 OpenAI 兼容协议 API</span>
        </div>
        <div className="config-actions">
          <button onClick={loadConfig} disabled={loading || saving}>{loading ? "加载中..." : "重新读取"}</button>
          <button onClick={saveConfig} disabled={loading || saving}>{saving ? "保存中..." : "保存"}</button>
        </div>
      </div>

      {error ? <div className="error">{error}</div> : null}
      {notice ? <div className="notice">{notice}</div> : null}

      <div className="model-config-layout">
        <div className="model-list-panel">
          <div className="model-list-header">
            <span>模型列表 ({models.length})</span>
            <button className="btn-outline" onClick={addModel}>+ 新增</button>
          </div>
          <div className="model-list">
            {!models.length ? <div className="empty-state">暂无模型，点击“新增”创建</div> : null}
            {models.map((item, idx) => (
              <button
                key={`${item.id || item.name || "model"}-${idx}`}
                className={`model-item ${idx === selectedIndex ? "active" : ""}`}
                onClick={() => setSelectedIndex(idx)}
              >
                <div className="model-item-name">{item.name || item.id || `未命名模型 ${idx + 1}`}</div>
                <div className="model-item-meta">{item.vendor || "Custom"}</div>
              </button>
            ))}
          </div>
        </div>

        <div className="model-editor-panel">
          {!currentModel ? (
            <div className="empty-state">请选择或新增一个模型</div>
          ) : (
            <>
              <div className="form-grid">
                <label>
                  <span>提供商</span>
                  <input
                    type="text"
                    value={currentModel.vendor || ""}
                    onChange={(e) => updateCurrent({ vendor: e.target.value })}
                    placeholder="Custom"
                  />
                </label>

                <label className="full-width">
                  <span>接口地址</span>
                  <input
                    type="text"
                    value={currentModel.url || ""}
                    onChange={(e) => updateCurrent({ url: e.target.value })}
                    placeholder="https://api.example.com/v1/chat/completions"
                  />
                </label>

                <label className="full-width">
                  <span>API KEY</span>
                  <div className="api-key-row">
                    <input
                      type={showApiKey ? "text" : "password"}
                      value={currentModel.apiKey || ""}
                      onChange={(e) => updateCurrent({ apiKey: e.target.value })}
                      placeholder="sk-..."
                    />
                    <button type="button" className="btn-outline" onClick={() => setShowApiKey((v) => !v)}>
                      {showApiKey ? "隐藏" : "显示"}
                    </button>
                  </div>
                </label>

                <label>
                  <span>模型名称</span>
                  <input
                    type="text"
                    value={currentModel.name || ""}
                    onChange={(e) => {
                      const name = e.target.value;
                      updateCurrent({ name, id: currentModel.id || name });
                    }}
                    placeholder="claude-sonnet-4-6"
                  />
                </label>

                <label>
                  <span>模型 ID</span>
                  <input
                    type="text"
                    value={currentModel.id || ""}
                    onChange={(e) => updateCurrent({ id: e.target.value })}
                    placeholder="claude-sonnet-4-6"
                  />
                </label>
              </div>

              <div className="advanced-box">
                <div className="advanced-title">高级配置</div>
                <div className="switch-group">
                  <label><input type="checkbox" checked={!!currentModel.supportsToolCall} onChange={(e) => updateCurrent({ supportsToolCall: e.target.checked })} /> 工具调用</label>
                  <label><input type="checkbox" checked={!!currentModel.supportsImages} onChange={(e) => updateCurrent({ supportsImages: e.target.checked })} /> 图片输入</label>
                  <label><input type="checkbox" checked={!!currentModel.supportsReasoning} onChange={(e) => updateCurrent({ supportsReasoning: e.target.checked })} /> 推理模式</label>
                </div>

                <div className="token-grid">
                  <label>
                    <span>输入 Token</span>
                    <input
                      type="number"
                      min="0"
                      value={currentModel.maxInputTokens ?? 0}
                      onChange={(e) => updateCurrent({ maxInputTokens: Number(e.target.value || 0) })}
                    />
                  </label>
                  <label>
                    <span>输出 Token</span>
                    <input
                      type="number"
                      min="0"
                      value={currentModel.maxOutputTokens ?? 0}
                      onChange={(e) => updateCurrent({ maxOutputTokens: Number(e.target.value || 0) })}
                    />
                  </label>
                </div>
              </div>

              <div className="editor-footer">
                <button className="btn-danger" onClick={removeCurrent}>删除当前模型</button>
                <button onClick={saveConfig} disabled={loading || saving}>{saving ? "保存中..." : "保存模型配置"}</button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
