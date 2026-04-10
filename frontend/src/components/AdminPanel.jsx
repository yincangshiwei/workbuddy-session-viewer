import { useCallback, useEffect, useRef, useState } from "react";

const POLL_INTERVAL = 10; // 秒，监控轮询间隔

const PROTOCOL_OPTIONS = [
  { value: "http", label: "HTTP POST" },
  { value: "https", label: "HTTPS POST" },
];

const DEFAULT_CFG = {
  enabled: false,
  protocol: "https",
  url: "",
  headers: {},
  include_basic: true,
  include_full: false,
  include_user: true,
  include_assistant: false,
  batch_size: 50,
  retry_times: 3,
};

function useMonitorConfig() {
  const [cfg, setCfg] = useState(DEFAULT_CFG);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [saveOk, setSaveOk] = useState(false);

  async function fetchConfig() {
    setLoading(true);
    setError("");
    try {
      const r = await fetch("/api/admin/monitor/config");
      if (!r.ok) throw new Error(`加载失败: ${r.status}`);
      const d = await r.json();
      setCfg({ ...DEFAULT_CFG, ...d });
    } catch (e) {
      setError(e.message || "加载配置失败");
    } finally {
      setLoading(false);
    }
  }

  async function saveConfig(next) {
    setSaving(true);
    setError("");
    setSaveOk(false);
    try {
      const r = await fetch("/api/admin/monitor/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(next),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d?.detail || "保存失败");
      setCfg({ ...DEFAULT_CFG, ...d.config });
      setSaveOk(true);
      setTimeout(() => setSaveOk(false), 2000);
    } catch (e) {
      setError(e.message || "保存失败");
    } finally {
      setSaving(false);
    }
  }

  useEffect(() => { fetchConfig(); }, []);

  return { cfg, setCfg, loading, saving, error, saveOk, saveConfig, refetch: fetchConfig };
}


export default function AdminPanel() {
  const { cfg, setCfg, loading, saving, error, saveOk, saveConfig } = useMonitorConfig();

  // 自定义请求头编辑（key-value 列表）
  const [headerRows, setHeaderRows] = useState([{ key: "", value: "" }]);

  // 机器信息
  const [machineInfo, setMachineInfo] = useState(null);
  const [machineLoading, setMachineLoading] = useState(false);

  async function fetchMachineInfo(forceRefresh = false) {
    setMachineLoading(true);
    try {
      const url = forceRefresh ? "/api/admin/machine-info/refresh" : "/api/admin/machine-info";
      const r = await fetch(url, { method: forceRefresh ? "POST" : "GET" });
      if (r.ok) setMachineInfo(await r.json());
    } catch (_) {}
    finally { setMachineLoading(false); }
  }

  useEffect(() => { fetchMachineInfo(); }, []);

  // 监控运行状态
  const [monitorRunning, setMonitorRunning] = useState(false);
  const [monitorLog, setMonitorLog] = useState([]);
  const [cacheStats, setCacheStats] = useState(null);
  const [uploadErrors, setUploadErrors] = useState([]);
  const monitorTimer = useRef(null);
  const logRef = useRef(null);

  // 同步 cfg.headers -> headerRows
  useEffect(() => {
    const rows = Object.entries(cfg.headers || {}).map(([k, v]) => ({ key: k, value: v }));
    setHeaderRows(rows.length > 0 ? rows : [{ key: "", value: "" }]);
  }, [cfg.headers]);

  function headersFromRows() {
    const h = {};
    headerRows.forEach(({ key, value }) => {
      if (key.trim()) h[key.trim()] = value;
    });
    return h;
  }

  function handleSave() {
    const next = { ...cfg, headers: headersFromRows() };
    saveConfig(next);
  }

  // ── 监控轮询逻辑 ──────────────────────────────────────────
  const addLog = useCallback((msg, type = "info") => {
    const ts = new Date().toLocaleTimeString();
    setMonitorLog((prev) => {
      const next = [...prev, { ts, msg, type }];
      return next.slice(-200); // 最多保留 200 条
    });
  }, []);

  async function runOnce() {
    try {
      // 1. 拉取会话列表
      const r = await fetch(`/api/sessions?_t=${Date.now()}`, { cache: "no-store" });
      if (!r.ok) throw new Error(`获取会话列表失败: ${r.status}`);
      const data = await r.json();
      const sessions = (data.sessions || []).filter((s) => !s.deletedAt);

      if (sessions.length === 0) {
        addLog("暂无活跃会话", "info");
        return;
      }

      // 2. 批量触发上传
      const ids = sessions.map((s) => s.conversationId);
      const resp = await fetch("/api/admin/monitor/upload-batch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ conversationIds: ids }),
      });
      if (!resp.ok) throw new Error(`上传请求失败: ${resp.status}`);
      const result = await resp.json();

      // 3. 统计结果
      let totalUploaded = 0;
      let totalSkipped = 0;
      let hasError = false;
      Object.entries(result.results || {}).forEach(([cid, res]) => {
        totalUploaded += res.uploaded || 0;
        totalSkipped += res.skipped || 0;
        if (res.error && res.uploaded === 0) hasError = true;
      });

      if (totalUploaded > 0) {
        addLog(`已上传 ${totalUploaded} 条新/变化消息，跳过 ${totalSkipped} 条（无变化）`, "success");
      } else if (hasError) {
        addLog(`上传失败，请检查目标地址配置`, "error");
      } else {
        addLog(`无新消息（跳过 ${totalSkipped} 条）`, "info");
      }

      // 4. 更新缓存统计
      const statsR = await fetch("/api/admin/monitor/cache-stats");
      if (statsR.ok) setCacheStats(await statsR.json());

      // 5. 拉取错误日志
      const errR = await fetch("/api/admin/monitor/errors");
      if (errR.ok) {
        const errData = await errR.json();
        setUploadErrors(errData.errors || []);
      }
    } catch (e) {
      addLog(`监控错误: ${e.message}`, "error");
    }
  }

  function startMonitor() {
    if (monitorRunning) return;
    setMonitorRunning(true);
    addLog("监控已启动，正在执行初始全量同步...", "success");
    // 启动时先清除后端缓存，确保将现有所有数据全量同步一次
    fetch("/api/admin/monitor/clear-cache", { method: "POST" })
      .then(() => {
        addLog("缓存已重置，开始全量同步现有数据", "info");
        runOnce();
      })
      .catch(() => {
        // 清缓存失败不阻断，直接跑
        runOnce();
      });
    monitorTimer.current = setInterval(runOnce, POLL_INTERVAL * 1000);
  }

  function stopMonitor() {
    if (monitorTimer.current) {
      clearInterval(monitorTimer.current);
      monitorTimer.current = null;
    }
    setMonitorRunning(false);
    addLog("监控已停止", "info");
  }

  useEffect(() => {
    return () => {
      if (monitorTimer.current) clearInterval(monitorTimer.current);
    };
  }, []);

  // 日志自动滚到底部
  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [monitorLog]);

  // ── 渲染 ──────────────────────────────────────────────────
  if (loading) return <div className="admin-panel"><div className="empty-state">配置加载中...</div></div>;

  return (
    <div className="admin-panel">
      <div className="admin-panel-header">
        <h2>管理配置</h2>
        <p className="admin-panel-desc">以下功能仅在管理员模式下可见，普通启动方式无法访问。</p>
      </div>

      {/* ── 本机环境信息模块 ── */}
      <div className="admin-section">
        <div className="admin-section-title">🖥 本机环境信息</div>
        <div className="admin-section-desc">
          以下信息将随每次上传数据一起发送到目标服务器，用于标识数据来源。
        </div>
        {machineLoading ? (
          <div className="empty-state" style={{ padding: "12px 0" }}>采集中...</div>
        ) : machineInfo ? (
          <div className="admin-machine-grid">
            <div className="admin-machine-row"><span className="admin-machine-label">主机名</span><span className="admin-machine-val mono">{machineInfo.hostname || "-"}</span></div>
            <div className="admin-machine-row"><span className="admin-machine-label">域账号</span><span className="admin-machine-val mono">{machineInfo.domain_user || "-"}</span></div>
            <div className="admin-machine-row"><span className="admin-machine-label">内网 IP</span><span className="admin-machine-val mono">{(machineInfo.local_ips || []).join("，") || "-"}</span></div>
            <div className="admin-machine-row"><span className="admin-machine-label">公网 IP</span><span className="admin-machine-val mono">{machineInfo.public_ip || "获取失败"}</span></div>
            <div className="admin-machine-row"><span className="admin-machine-label">操作系统</span><span className="admin-machine-val">{machineInfo.os} {machineInfo.os_release}</span></div>
            <div className="admin-machine-row"><span className="admin-machine-label">OS 版本</span><span className="admin-machine-val mono">{machineInfo.os_version || "-"}</span></div>
            <div className="admin-machine-row"><span className="admin-machine-label">架构</span><span className="admin-machine-val">{machineInfo.machine || "-"}</span></div>
            <div className="admin-machine-row"><span className="admin-machine-label">采集时间</span><span className="admin-machine-val">{machineInfo.collected_at || "-"}</span></div>
          </div>
        ) : (
          <div className="empty-state" style={{ padding: "12px 0" }}>暂无数据</div>
        )}
        <div className="admin-actions" style={{ marginTop: 10 }}>
          <button className="btn-outline" onClick={() => fetchMachineInfo(true)} disabled={machineLoading}>
            {machineLoading ? "刷新中..." : "🔄 重新采集（含公网IP）"}
          </button>
        </div>
      </div>

      {/* ── 数据监控上传模块 ── */}
      <div className="admin-section">
        <div className="admin-section-title">📡 数据监控上传</div>
        <div className="admin-section-desc">
          实时监控会话对话内容，检测到新消息或内容变化时自动上传到指定服务器，已上传且无变化的消息不会重复上传。
        </div>

        {error ? <div className="error" style={{ marginBottom: 12 }}>{error}</div> : null}

        {/* 配置区 */}
        <div className="admin-config-grid">
          {/* 启用开关 */}
          <div className="admin-config-row full">
            <label className="admin-label">
              <input
                type="checkbox"
                checked={cfg.enabled}
                onChange={(e) => setCfg((p) => ({ ...p, enabled: e.target.checked }))}
              />
              <span>启用监控上传</span>
            </label>
          </div>

          {/* 协议 */}
          <div className="admin-config-row">
            <label className="admin-label-text">上传协议</label>
            <select
              className="admin-select"
              value={cfg.protocol}
              onChange={(e) => setCfg((p) => ({ ...p, protocol: e.target.value }))}
            >
              {PROTOCOL_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>

          {/* 重试次数 */}
          <div className="admin-config-row">
            <label className="admin-label-text">失败重试次数</label>
            <input
              type="number"
              className="admin-input"
              min={1}
              max={10}
              value={cfg.retry_times}
              onChange={(e) => setCfg((p) => ({ ...p, retry_times: Number(e.target.value) }))}
            />
          </div>

          {/* 目标地址 */}
          <div className="admin-config-row full">
            <label className="admin-label-text">目标上传地址</label>
            <input
              type="text"
              className="admin-input"
              placeholder="例如：http://your-server.com/api/collect"
              value={cfg.url}
              onChange={(e) => setCfg((p) => ({ ...p, url: e.target.value }))}
            />
          </div>

          {/* 上传数据选项 */}
          <div className="admin-config-row full">
            <div className="admin-label-text">上传数据范围</div>
            <div className="admin-checkbox-group">
              <div className="admin-checkbox-section">
                <div className="admin-checkbox-section-title">对话类型</div>
                <label className="admin-label">
                  <input
                    type="checkbox"
                    checked={cfg.include_basic}
                    onChange={(e) => setCfg((p) => ({ ...p, include_basic: e.target.checked }))}
                  />
                  <span>基础对话 <span className="admin-hint">（仅 user/assistant 的文本内容，不含工具调用）</span></span>
                </label>
                <label className="admin-label">
                  <input
                    type="checkbox"
                    checked={cfg.include_full}
                    onChange={(e) => setCfg((p) => ({ ...p, include_full: e.target.checked }))}
                  />
                  <span>完整对话 <span className="admin-hint">（含工具调用/结果等所有消息）</span></span>
                </label>
              </div>
              <div className="admin-checkbox-section">
                <div className="admin-checkbox-section-title">角色筛选</div>
                <label className="admin-label">
                  <input
                    type="checkbox"
                    checked={cfg.include_user}
                    onChange={(e) => setCfg((p) => ({ ...p, include_user: e.target.checked }))}
                  />
                  <span>用户消息 (user)</span>
                </label>
                <label className="admin-label">
                  <input
                    type="checkbox"
                    checked={cfg.include_assistant}
                    onChange={(e) => setCfg((p) => ({ ...p, include_assistant: e.target.checked }))}
                  />
                  <span>AI 回复 (assistant)</span>
                </label>
              </div>
            </div>
          </div>

          {/* 自定义请求头 */}
          <div className="admin-config-row full">
            <div className="admin-label-text">自定义请求头（可选，如鉴权 Token）</div>
            {headerRows.map((row, i) => (
              <div key={i} className="admin-header-row">
                <input
                  className="admin-input admin-input-sm"
                  placeholder="Header 名称"
                  value={row.key}
                  onChange={(e) => {
                    const next = [...headerRows];
                    next[i] = { ...next[i], key: e.target.value };
                    setHeaderRows(next);
                  }}
                />
                <span className="admin-header-sep">:</span>
                <input
                  className="admin-input"
                  placeholder="Header 值"
                  value={row.value}
                  onChange={(e) => {
                    const next = [...headerRows];
                    next[i] = { ...next[i], value: e.target.value };
                    setHeaderRows(next);
                  }}
                />
                <button
                  className="btn-outline admin-btn-sm"
                  onClick={() => setHeaderRows((prev) => prev.filter((_, idx) => idx !== i))}
                  disabled={headerRows.length <= 1}
                >✕</button>
              </div>
            ))}
            <button
              className="btn-outline admin-btn-sm"
              onClick={() => setHeaderRows((prev) => [...prev, { key: "", value: "" }])}
            >+ 添加请求头</button>
          </div>
        </div>

        {/* 保存按钮 */}
        <div className="admin-actions">
          <button className="btn-primary" onClick={handleSave} disabled={saving}>
            {saving ? "保存中..." : saveOk ? "✓ 已保存" : "保存配置"}
          </button>
        </div>

        {/* 监控控制 */}
        <div className="admin-monitor-ctrl">
          <div className="admin-monitor-status">
            <span className={`monitor-dot ${monitorRunning ? "running" : ""}`} />
            {monitorRunning ? `监控运行中（每 ${POLL_INTERVAL}s 检测一次）` : "监控未启动"}
          </div>
          <div className="admin-actions">
            <button
              className="btn-primary"
              onClick={startMonitor}
              disabled={monitorRunning || !cfg.enabled || !cfg.url.trim()}
            >
              ▶ 启动监控
            </button>
            <button
              className="btn-outline"
              onClick={stopMonitor}
              disabled={!monitorRunning}
            >
              ■ 停止监控
            </button>
            <button
              className="btn-outline"
              onClick={() => setMonitorLog([])}
            >
              清空日志
            </button>
          </div>
          {!cfg.enabled && (
            <div className="admin-hint" style={{ marginTop: 6 }}>请先启用监控上传并保存配置，再启动监控。</div>
          )}
          {cfg.enabled && !cfg.url.trim() && (
            <div className="admin-hint" style={{ marginTop: 6 }}>请先填写目标上传地址并保存配置。</div>
          )}
        </div>

        {/* 缓存统计 */}
        {cacheStats && (
          <div className="admin-cache-stats">
            <span>已缓存会话：{cacheStats.sessions} 个</span>
            <span>已追踪消息：{cacheStats.total_messages} 条</span>
          </div>
        )}

        {/* 运行日志 */}
        <div className="admin-log-box" ref={logRef}>
          {monitorLog.length === 0 ? (
            <div className="admin-log-empty">暂无日志，启动监控后将在此显示运行状态</div>
          ) : (
            monitorLog.map((entry, i) => (
              <div key={i} className={`admin-log-entry log-${entry.type}`}>
                <span className="admin-log-ts">{entry.ts}</span>
                <span className="admin-log-msg">{entry.msg}</span>
              </div>
            ))
          )}
        </div>

        {/* 上传错误 */}
        {uploadErrors.length > 0 && (
          <div className="admin-error-list">
            <div className="admin-label-text" style={{ marginBottom: 6 }}>最近上传错误</div>
            {uploadErrors.slice(-5).map((e, i) => (
              <div key={i} className="admin-error-item">
                <span className="admin-log-ts">{e.time}</span>
                <span className="admin-log-msg">{e.error}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
