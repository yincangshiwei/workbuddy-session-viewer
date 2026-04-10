import { useCallback, useEffect, useRef, useState } from "react";

const POLL_INTERVAL = 10; // 秒

const PROTOCOL_OPTIONS = [
  { value: "https", label: "HTTPS POST" },
  { value: "http", label: "HTTP POST" },
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

// ── 配置 Hook ────────────────────────────────────────────────
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
      setCfg({ ...DEFAULT_CFG, ...(await r.json()) });
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
  return { cfg, setCfg, loading, saving, error, saveOk, saveConfig };
}

// ── 主组件 ───────────────────────────────────────────────────
export default function AdminPanel() {
  const { cfg, setCfg, loading, saving, error: cfgError, saveOk, saveConfig } = useMonitorConfig();

  // 自定义请求头
  const [headerRows, setHeaderRows] = useState([{ key: "", value: "" }]);
  useEffect(() => {
    const rows = Object.entries(cfg.headers || {}).map(([k, v]) => ({ key: k, value: v }));
    setHeaderRows(rows.length > 0 ? rows : [{ key: "", value: "" }]);
  }, [cfg.headers]);
  function headersFromRows() {
    const h = {};
    headerRows.forEach(({ key, value }) => { if (key.trim()) h[key.trim()] = value; });
    return h;
  }
  function handleSave() { saveConfig({ ...cfg, headers: headersFromRows() }); }

  // 本机信息
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

  // 同步状态统计
  const [syncStats, setSyncStats] = useState(null);
  async function fetchStats() {
    try {
      const r = await fetch("/api/admin/monitor/stats");
      if (r.ok) setSyncStats(await r.json());
    } catch (_) {}
  }
  useEffect(() => { fetchStats(); }, []);

  // 初始化
  const [initializing, setInitializing] = useState(false);
  const [initResult, setInitResult] = useState(null);
  async function handleInitialize() {
    if (!window.confirm(
      "初始化将清空所有同步记录，重新从所有活跃会话读取数据，状态全部置为「未同步」。\n\n确认执行初始化？"
    )) return;
    setInitializing(true);
    setInitResult(null);
    try {
      const r = await fetch("/api/admin/monitor/initialize", { method: "POST" });
      const d = await r.json();
      setInitResult(d);
      fetchStats();
    } catch (e) {
      setInitResult({ error: e.message });
    } finally {
      setInitializing(false);
    }
  }

  // 监控运行
  const [monitorRunning, setMonitorRunning] = useState(false);
  const [monitorLog, setMonitorLog] = useState([]);
  const [uploadErrors, setUploadErrors] = useState([]);
  const monitorTimer = useRef(null);
  const logRef = useRef(null);

  const addLog = useCallback((msg, type = "info") => {
    const ts = new Date().toLocaleTimeString();
    setMonitorLog((prev) => [...prev, { ts, msg, type }].slice(-300));
  }, []);

  async function runPoll() {
    try {
      const r = await fetch("/api/admin/monitor/poll", { method: "POST" });
      if (!r.ok) throw new Error(`轮询请求失败: ${r.status}`);
      const d = await r.json();

      const scanMsg = (d.scan_new || d.scan_changed)
        ? `发现 ${d.scan_new} 条新消息、${d.scan_changed} 条变化消息`
        : "无新变化";
      const uploadMsg = d.uploaded > 0
        ? `上传 ${d.uploaded} 条`
        : d.failed > 0 ? `上传失败 ${d.failed} 条` : "无待上传";

      const type = d.failed > 0 ? "error" : d.uploaded > 0 || d.scan_new > 0 || d.scan_changed > 0 ? "success" : "info";
      addLog(`${scanMsg}，${uploadMsg}（共扫描 ${d.scanned_sessions} 个会话）`, type);

      // 刷新统计和错误
      fetchStats();
      const errR = await fetch("/api/admin/monitor/errors");
      if (errR.ok) setUploadErrors((await errR.json()).errors || []);
    } catch (e) {
      addLog(`轮询错误: ${e.message}`, "error");
    }
  }

  function startMonitor() {
    if (monitorRunning) return;
    setMonitorRunning(true);
    addLog("监控已启动，开始第一次轮询...", "success");
    runPoll();
    monitorTimer.current = setInterval(runPoll, POLL_INTERVAL * 1000);
  }

  function stopMonitor() {
    if (monitorTimer.current) { clearInterval(monitorTimer.current); monitorTimer.current = null; }
    setMonitorRunning(false);
    addLog("监控已停止", "info");
  }

  useEffect(() => () => { if (monitorTimer.current) clearInterval(monitorTimer.current); }, []);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [monitorLog]);

  // ── 渲染 ──────────────────────────────────────────────────
  if (loading) return <div className="admin-panel"><div className="empty-state">配置加载中...</div></div>;

  const canStartMonitor = cfg.enabled && cfg.url.trim() && syncStats && syncStats.total > 0;

  return (
    <div className="admin-panel">
      <div className="admin-panel-header">
        <h2>管理配置</h2>
        <p className="admin-panel-desc">以下功能仅在管理员模式下可见，普通启动方式无法访问。</p>
      </div>

      {/* ── 本机环境信息 ── */}
      <div className="admin-section">
        <div className="admin-section-title">🖥 本机环境信息</div>
        <div className="admin-section-desc">以下信息将随每次上传数据一起发送到目标服务器，用于标识数据来源。</div>
        {machineLoading ? (
          <div className="empty-state" style={{ padding: "12px 0" }}>采集中...</div>
        ) : machineInfo ? (
          <div className="admin-machine-grid">
            {[
              ["主机名", machineInfo.hostname],
              ["域账号", machineInfo.domain_user],
              ["内网 IP", (machineInfo.local_ips || []).join("，") || "-"],
              ["公网 IP", machineInfo.public_ip || "获取失败"],
              ["操作系统", `${machineInfo.os} ${machineInfo.os_release}`],
              ["OS 版本", machineInfo.os_version],
              ["架构", machineInfo.machine],
              ["采集时间", machineInfo.collected_at],
            ].map(([label, val]) => (
              <div className="admin-machine-row" key={label}>
                <span className="admin-machine-label">{label}</span>
                <span className="admin-machine-val mono">{val || "-"}</span>
              </div>
            ))}
          </div>
        ) : <div className="empty-state" style={{ padding: "12px 0" }}>暂无数据</div>}
        <div className="admin-actions" style={{ marginTop: 10 }}>
          <button className="btn-outline" onClick={() => fetchMachineInfo(true)} disabled={machineLoading}>
            {machineLoading ? "刷新中..." : "🔄 重新采集（含公网IP）"}
          </button>
        </div>
      </div>

      {/* ── 数据监控上传 ── */}
      <div className="admin-section">
        <div className="admin-section-title">📡 数据监控上传</div>
        <div className="admin-section-desc">
          基于本地 SQLite 持久化同步状态，检测到新消息或内容变化时自动上传到指定服务器。<br />
          <strong>操作流程：</strong>先保存配置 → 执行初始化 → 启动监控。
        </div>

        {cfgError ? <div className="error" style={{ marginBottom: 12 }}>{cfgError}</div> : null}

        {/* ── STEP 1：配置 ── */}
        <div className="admin-step-title">第一步：配置上传参数</div>
        <div className="admin-config-grid">
          <div className="admin-config-row full">
            <label className="admin-label">
              <input type="checkbox" checked={cfg.enabled}
                onChange={(e) => setCfg((p) => ({ ...p, enabled: e.target.checked }))} />
              <span>启用监控上传</span>
            </label>
          </div>

          <div className="admin-config-row">
            <label className="admin-label-text">上传协议</label>
            <select className="admin-select" value={cfg.protocol}
              onChange={(e) => setCfg((p) => ({ ...p, protocol: e.target.value }))}>
              {PROTOCOL_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>

          <div className="admin-config-row">
            <label className="admin-label-text">失败重试次数</label>
            <input type="number" className="admin-input" min={1} max={10} value={cfg.retry_times}
              onChange={(e) => setCfg((p) => ({ ...p, retry_times: Number(e.target.value) }))} />
          </div>

          <div className="admin-config-row full">
            <label className="admin-label-text">目标上传地址</label>
            <input type="text" className="admin-input"
              placeholder="例如：https://your-server.com/api/collect"
              value={cfg.url}
              onChange={(e) => setCfg((p) => ({ ...p, url: e.target.value }))} />
          </div>

          <div className="admin-config-row full">
            <div className="admin-label-text">上传数据范围</div>
            <div className="admin-checkbox-group">
              <div className="admin-checkbox-section">
                <div className="admin-checkbox-section-title">对话类型</div>
                <label className="admin-label">
                  <input type="checkbox" checked={cfg.include_basic}
                    onChange={(e) => setCfg((p) => ({ ...p, include_basic: e.target.checked }))} />
                  <span>基础对话 <span className="admin-hint">（user/assistant 文本，不含工具调用）</span></span>
                </label>
                <label className="admin-label">
                  <input type="checkbox" checked={cfg.include_full}
                    onChange={(e) => setCfg((p) => ({ ...p, include_full: e.target.checked }))} />
                  <span>完整对话 <span className="admin-hint">（含工具调用/结果等所有消息）</span></span>
                </label>
              </div>
              <div className="admin-checkbox-section">
                <div className="admin-checkbox-section-title">角色筛选</div>
                <label className="admin-label">
                  <input type="checkbox" checked={cfg.include_user}
                    onChange={(e) => setCfg((p) => ({ ...p, include_user: e.target.checked }))} />
                  <span>用户消息 (user)</span>
                </label>
                <label className="admin-label">
                  <input type="checkbox" checked={cfg.include_assistant}
                    onChange={(e) => setCfg((p) => ({ ...p, include_assistant: e.target.checked }))} />
                  <span>AI 回复 (assistant)</span>
                </label>
              </div>
            </div>
          </div>

          <div className="admin-config-row full">
            <div className="admin-label-text">自定义请求头（可选，如鉴权 Token）</div>
            {headerRows.map((row, i) => (
              <div key={i} className="admin-header-row">
                <input className="admin-input admin-input-sm" placeholder="Header 名称" value={row.key}
                  onChange={(e) => { const n = [...headerRows]; n[i] = { ...n[i], key: e.target.value }; setHeaderRows(n); }} />
                <span className="admin-header-sep">:</span>
                <input className="admin-input" placeholder="Header 值" value={row.value}
                  onChange={(e) => { const n = [...headerRows]; n[i] = { ...n[i], value: e.target.value }; setHeaderRows(n); }} />
                <button className="btn-outline admin-btn-sm"
                  onClick={() => setHeaderRows((p) => p.filter((_, idx) => idx !== i))}
                  disabled={headerRows.length <= 1}>✕</button>
              </div>
            ))}
            <button className="btn-outline admin-btn-sm"
              onClick={() => setHeaderRows((p) => [...p, { key: "", value: "" }])}>+ 添加请求头</button>
          </div>
        </div>
        <div className="admin-actions">
          <button className="btn-primary" onClick={handleSave} disabled={saving}>
            {saving ? "保存中..." : saveOk ? "✓ 已保存" : "保存配置"}
          </button>
        </div>

        {/* ── STEP 2：初始化 ── */}
        <div className="admin-step-title" style={{ marginTop: 20 }}>第二步：初始化同步数据</div>
        <div className="admin-hint" style={{ marginBottom: 10 }}>
          初始化会清空 DB 中的所有同步记录，重新从所有活跃会话读取消息并写入，状态全部置为「未同步」。<br />
          <strong>换服务地址、修改数据范围配置后，需重新初始化。</strong>
        </div>

        {/* 当前 DB 统计 */}
        {syncStats ? (
          <div className="admin-sync-stats">
            <div className="admin-sync-stat">
              <span className="admin-sync-num">{syncStats.total}</span>
              <span className="admin-sync-lbl">总消息数</span>
            </div>
            <div className="admin-sync-stat c-ok">
              <span className="admin-sync-num">{syncStats.synced}</span>
              <span className="admin-sync-lbl">已同步</span>
            </div>
            <div className="admin-sync-stat c-err">
              <span className="admin-sync-num">{syncStats.unsynced}</span>
              <span className="admin-sync-lbl">未同步</span>
            </div>
            <div className="admin-sync-stat">
              <span className="admin-sync-num">{syncStats.conversations}</span>
              <span className="admin-sync-lbl">涉及会话</span>
            </div>
          </div>
        ) : null}

        {initResult && (
          <div className={`admin-init-result ${initResult.error ? "has-error" : "ok"}`}>
            {initResult.error
              ? `初始化出现错误：${initResult.error}`
              : `初始化完成：共写入 ${initResult.total} 条消息（${initResult.conversations} 个会话），全部标记为未同步`}
          </div>
        )}

        <div className="admin-actions">
          <button className="btn-primary" onClick={handleSave} disabled={saving} style={{ background: "#2d3748", border: "1px solid #4a5568", color: "#a0aec0" }}>
            {saving ? "保存中..." : saveOk ? "✓ 已保存" : "保存配置"}
          </button>
          <button
            className="btn-primary"
            style={{ background: initializing ? undefined : "#744210", borderColor: "#c05621" }}
            onClick={handleInitialize}
            disabled={initializing}
          >
            {initializing ? "初始化中..." : "⚡ 执行初始化"}
          </button>
          <button className="btn-outline" onClick={fetchStats}>刷新统计</button>
        </div>

        {/* ── STEP 3：启动监控 ── */}
        <div className="admin-step-title" style={{ marginTop: 20 }}>第三步：启动监控</div>
        <div className="admin-hint" style={{ marginBottom: 10 }}>
          启动后每 {POLL_INTERVAL} 秒自动扫描所有活跃会话，检测变化后更新 DB，并将所有未同步记录上传到目标服务器。
        </div>

        {!cfg.enabled && <div className="admin-hint c-err" style={{ marginBottom: 6 }}>⚠ 请先启用监控上传并保存配置</div>}
        {cfg.enabled && !cfg.url.trim() && <div className="admin-hint c-err" style={{ marginBottom: 6 }}>⚠ 请先填写目标上传地址并保存配置</div>}
        {cfg.enabled && cfg.url.trim() && syncStats && syncStats.total === 0 && (
          <div className="admin-hint c-err" style={{ marginBottom: 6 }}>⚠ DB 中暂无数据，请先执行初始化</div>
        )}

        <div className="admin-monitor-ctrl">
          <div className="admin-monitor-status">
            <span className={`monitor-dot ${monitorRunning ? "running" : ""}`} />
            {monitorRunning ? `监控运行中（每 ${POLL_INTERVAL}s 轮询一次）` : "监控未启动"}
          </div>
          <div className="admin-actions">
            <button className="btn-primary" onClick={startMonitor}
              disabled={monitorRunning || !canStartMonitor}>
              ▶ 启动监控
            </button>
            <button className="btn-outline" onClick={stopMonitor} disabled={!monitorRunning}>
              ■ 停止监控
            </button>
            <button className="btn-outline" onClick={() => setMonitorLog([])}>清空日志</button>
          </div>
        </div>

        {/* 运行日志 */}
        <div className="admin-log-box" ref={logRef}>
          {monitorLog.length === 0
            ? <div className="admin-log-empty">暂无日志，启动监控后将在此显示运行状态</div>
            : monitorLog.map((entry, i) => (
              <div key={i} className={`admin-log-entry log-${entry.type}`}>
                <span className="admin-log-ts">{entry.ts}</span>
                <span className="admin-log-msg">{entry.msg}</span>
              </div>
            ))}
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
