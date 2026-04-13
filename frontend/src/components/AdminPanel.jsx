import { useCallback, useEffect, useRef, useState } from "react";

const POLL_INTERVAL = 10;

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
  success_field: "",
  success_value: "",
  success_http_codes: "",
};

const STEPS = [
  { key: "machine", label: "本机信息", icon: "🖥" },
  { key: "config",  label: "上传配置", icon: "⚙️" },
  { key: "init",    label: "初始化",   icon: "⚡" },
  { key: "monitor", label: "启动监控", icon: "📡" },
];

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

// ── 响应示例输入 + 自动解析字段 ─────────────────────────────
function ResponseExampleInput({ cfg, setCfg }) {
  const [raw, setRaw] = useState("");
  const [parseErr, setParseErr] = useState("");
  const [parsedKeys, setParsedKeys] = useState([]);

  function handleChange(val) {
    setRaw(val);
    setParseErr("");
    setParsedKeys([]);
    if (!val.trim()) return;
    try {
      const obj = JSON.parse(val);
      if (typeof obj !== "object" || Array.isArray(obj)) {
        setParseErr("需要是 JSON 对象格式，如 {\"success\":true}");
        return;
      }
      setParsedKeys(Object.keys(obj));
    } catch {
      setParseErr("JSON 格式有误，请检查");
    }
  }

  function pickKey(key, obj) {
    // 自动填入字段名和示例值（转字符串）
    const val = JSON.parse(raw)[key];
    setCfg((p) => ({
      ...p,
      success_field: key,
      success_value: String(val),
    }));
  }

  return (
    <div>
      <textarea
        className="admin-input admin-textarea"
        rows={3}
        placeholder={'{"success":true,"message":"ok"}'}
        value={raw}
        onChange={(e) => handleChange(e.target.value)}
        spellCheck={false}
      />
      {parseErr && <div className="admin-hint" style={{ color: "#fc8181", marginTop: 4 }}>{parseErr}</div>}
      {parsedKeys.length > 0 && (
        <div className="admin-parsed-keys">
          <span className="admin-hint">点击字段自动填入：</span>
          {parsedKeys.map((k) => (
            <button key={k} className="admin-key-chip" onClick={() => pickKey(k)}>
              {k}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ── 当前生效规则预览 ─────────────────────────────────────────
function SuccessRulePreview({ cfg }) {
  const parts = [];
  if (cfg.success_http_codes.trim()) {
    parts.push(`HTTP 状态码在 [${cfg.success_http_codes.trim()}] 中`);
  }
  if (cfg.success_field.trim() && cfg.success_value.trim()) {
    parts.push(`响应体字段 "${cfg.success_field}" = ${cfg.success_value}`);
  }
  if (parts.length === 0) {
    parts.push("HTTP 状态码 < 400（默认）");
  }

  return (
    <div className="admin-success-preview">
      <span className="admin-hint">当前判断规则：</span>
      <span className="admin-success-preview-rule">{parts.join(" 且 ")}</span>
    </div>
  );
}

// ── Payload 预览组件 ─────────────────────────────────────────
const PREVIEW_CONV_ID = "aaa94cd5c789493db44f390c20aaa634";

function PayloadPreview() {
  const [preview, setPreview] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [convId, setConvId] = useState(PREVIEW_CONV_ID);
  const [expanded, setExpanded] = useState(false);

  async function fetchPreview() {
    setLoading(true);
    setError("");
    setPreview(null);
    try {
      const r = await fetch(
        `/api/admin/monitor/payload-preview?conversation_id=${encodeURIComponent(convId)}&max_messages=3`
      );
      const d = await r.json();
      if (!r.ok) throw new Error(d?.detail || "请求失败");
      if (d.error) throw new Error(d.error);
      setPreview(d);
      setExpanded(true);
    } catch (e) {
      setError(e.message || "预览失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="admin-payload-preview-wrap">
      <div className="admin-payload-preview-header" onClick={() => setExpanded((v) => !v)}>
        <span className="admin-payload-preview-title">📋 上传内容示例预览</span>
        <span className="admin-hint">查看按当前配置实际会上传什么内容到服务端</span>
        <span className="admin-payload-toggle">{expanded ? "▲" : "▼"}</span>
      </div>

      {expanded && (
        <div className="admin-payload-preview-body">
          <div className="admin-payload-conv-row">
            <input
              className="admin-input"
              style={{ flex: 1 }}
              placeholder="会话ID"
              value={convId}
              onChange={(e) => setConvId(e.target.value)}
            />
            <button className="btn-primary" onClick={fetchPreview} disabled={loading || !convId.trim()}>
              {loading ? "加载中..." : "获取示例"}
            </button>
          </div>

          {error && <div className="admin-hint" style={{ color: "#fc8181", marginTop: 6 }}>{error}</div>}

          {preview && (
            <>
              <div className="admin-payload-meta">
                按当前配置过滤后共 <strong>{preview.total_messages}</strong> 条消息，
                展示前 <strong>{preview.sample_count}</strong> 条
                （{preview.config_summary.include_full ? "完整对话" : "基础对话"}
                {preview.config_summary.include_user ? " · user" : ""}
                {preview.config_summary.include_assistant ? " · assistant" : ""}）
              </div>
              <pre className="admin-payload-json">
                {JSON.stringify(preview.payload, null, 2)}
              </pre>
            </>
          )}
        </div>
      )}
    </div>
  );
}

// ── 主组件 ───────────────────────────────────────────────────
export default function AdminPanel() {
  const { cfg, setCfg, loading, saving, error: cfgError, saveOk, saveConfig } = useMonitorConfig();
  const [activeStep, setActiveStep] = useState("machine");

  // 请求头
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

  // 同步状态
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

  // 监控
  const [monitorRunning, setMonitorRunning] = useState(false);
  const [monitorLog, setMonitorLog] = useState([]);
  const [uploadErrors, setUploadErrors] = useState([]);
  const monitorTimer = useRef(null);
  const abortCtrlRef = useRef(null); // 当前 poll 的 AbortController
  const logRef = useRef(null);
  const liveLogTimer = useRef(null);  // 实时日志轮询定时器
  const liveLogSinceRef = useRef(0);  // 上次拉取的日志 id

  const addLog = useCallback((msg, type = "info") => {
    const ts = new Date().toLocaleTimeString();
    setMonitorLog((prev) => [...prev, { ts, msg, type }].slice(-300));
  }, []);

  // 拉取后端实时日志（增量）
  async function pullLiveLogs() {
    try {
      const r = await fetch(`/api/admin/monitor/live-logs?since=${liveLogSinceRef.current}`);
      if (!r.ok) return;
      const d = await r.json();
      if (d.logs && d.logs.length > 0) {
        d.logs.forEach((entry) => {
          addLog(entry.msg, entry.type || "info");
          liveLogSinceRef.current = entry.id;
        });
      }
    } catch (_) {}
  }

  // 启动实时日志轮询（每 1 秒拉取一次）
  function startLiveLogPolling() {
    stopLiveLogPolling();
    liveLogTimer.current = setInterval(pullLiveLogs, 1000);
  }

  function stopLiveLogPolling() {
    if (liveLogTimer.current) { clearInterval(liveLogTimer.current); liveLogTimer.current = null; }
  }

  async function runPoll() {
    // 每次 poll 创建新的 AbortController，取消上一次未完成的请求
    if (abortCtrlRef.current) abortCtrlRef.current.abort();
    const ctrl = new AbortController();
    abortCtrlRef.current = ctrl;
    const signal = ctrl.signal;

    try {
      const r = await fetch("/api/admin/monitor/poll", { method: "POST", signal });
      if (!r.ok) throw new Error(`轮询请求失败: ${r.status}`);
      const d = await r.json();

      if (d.cancelled) {
        addLog("本次轮询已被取消", "info");
      }

      if (signal.aborted) return;
      // poll 结束后再拉一次日志确保不遗漏
      await pullLiveLogs();
      fetchStats();
      const errR = await fetch("/api/admin/monitor/errors", { signal });
      if (errR.ok) setUploadErrors((await errR.json()).errors || []);
    } catch (e) {
      if (e.name === "AbortError") return;
      addLog(`轮询错误: ${e.message}`, "error");
    }
  }

  function startMonitor() {
    if (monitorRunning) return;
    setMonitorRunning(true);
    // 清空后端日志缓冲区，重置游标
    fetch("/api/admin/monitor/live-logs/clear", { method: "POST" }).catch(() => {});
    liveLogSinceRef.current = 0;
    addLog("监控已启动，开始第一次轮询...", "success");
    startLiveLogPolling();
    runPoll();
    monitorTimer.current = setInterval(runPoll, POLL_INTERVAL * 1000);
  }

  function stopMonitor() {
    // 停止定时器
    if (monitorTimer.current) { clearInterval(monitorTimer.current); monitorTimer.current = null; }
    // 取消正在进行中的 fetch 请求
    if (abortCtrlRef.current) { abortCtrlRef.current.abort(); abortCtrlRef.current = null; }
    // 通知后端取消正在执行的轮询/上传
    fetch("/api/admin/monitor/stop", { method: "POST" }).catch(() => {});
    // 停止前最后拉一次日志
    pullLiveLogs().finally(() => stopLiveLogPolling());
    setMonitorRunning(false);
    addLog("监控已停止", "info");
  }

  useEffect(() => () => {
    if (monitorTimer.current) clearInterval(monitorTimer.current);
    if (abortCtrlRef.current) abortCtrlRef.current.abort();
    stopLiveLogPolling();
  }, []);
  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [monitorLog]);

  if (loading) return <div className="admin-panel"><div className="empty-state">配置加载中...</div></div>;

  const canStartMonitor = cfg.enabled && cfg.url.trim() && syncStats && syncStats.total > 0;

  // ── 步骤状态徽标 ──────────────────────────────────────────
  function stepBadge(key) {
    if (key === "machine") return machineInfo ? "ok" : "warn";
    if (key === "config")  return (cfg.enabled && cfg.url.trim()) ? "ok" : "warn";
    if (key === "init")    return syncStats && syncStats.total > 0 ? "ok" : "warn";
    if (key === "monitor") return monitorRunning ? "running" : "idle";
    return "idle";
  }

  // ── 各步骤内容 ────────────────────────────────────────────
  function renderContent() {
    switch (activeStep) {

      // ── 本机信息 ──
      case "machine":
        return (
          <div className="admin-content-body">
            <div className="admin-content-title">🖥 本机环境信息</div>
            <p className="admin-content-desc">以下信息将随每次上传数据一起发送到目标服务器，用于标识数据来源。</p>
            {machineLoading ? (
              <div className="empty-state" style={{ padding: "20px 0" }}>采集中...</div>
            ) : machineInfo ? (
              <div className="admin-machine-grid">
                {[
                  ["主机名",      machineInfo.hostname],
                  ["域账号",      machineInfo.domain_user],
                  ["主网卡 IP",   machineInfo.local_ip || "获取失败"],
                  ["所有本地 IP", (machineInfo.local_ips || []).join("  /  ") || "-"],
                  ["公网 IP",     machineInfo.public_ip || "获取失败"],
                  ["操作系统",    `${machineInfo.os} ${machineInfo.os_release}`],
                  ["OS 版本",     machineInfo.os_version],
                  ["架构",        machineInfo.machine],
                  ["采集时间", machineInfo.collected_at],
                ].map(([label, val]) => (
                  <div className="admin-machine-row" key={label}>
                    <span className="admin-machine-label">{label}</span>
                    <span className="admin-machine-val mono">{val || "-"}</span>
                  </div>
                ))}
              </div>
            ) : <div className="empty-state" style={{ padding: "20px 0" }}>暂无数据</div>}
            <div className="admin-actions" style={{ marginTop: 16 }}>
              <button className="btn-outline" onClick={() => fetchMachineInfo(true)} disabled={machineLoading}>
                {machineLoading ? "刷新中..." : "🔄 重新采集（含公网IP）"}
              </button>
            </div>
          </div>
        );

      // ── 上传配置 ──
      case "config":
        return (
          <div className="admin-content-body">
            <div className="admin-content-title">⚙️ 上传配置</div>
            <p className="admin-content-desc">配置完成后点击「保存配置」，修改数据范围后需重新执行初始化。</p>
            {cfgError ? <div className="error" style={{ marginBottom: 12 }}>{cfgError}</div> : null}

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

              {/* ── 响应成功判断 ── */}
              <div className="admin-config-row full">
                <div className="admin-label-text">响应成功判断</div>
                <div className="admin-success-judge-box">
                  <div className="admin-success-judge-desc">
                    填写服务响应示例，系统自动解析字段名用于判断请求是否成功。未配置时默认以 HTTP 状态码 &lt;400 为成功。
                  </div>

                  {/* 响应示例输入 */}
                  <div className="admin-success-example-row">
                    <div className="admin-label-text" style={{ marginBottom: 6 }}>
                      响应示例 JSON
                      <span className="admin-hint" style={{ marginLeft: 8 }}>
                        如 {`{"success":true}`} 或 {`{"code":0,"message":"ok"}`}
                      </span>
                    </div>
                    <ResponseExampleInput cfg={cfg} setCfg={setCfg} />
                  </div>

                  {/* 字段 + 期望值 */}
                  <div className="admin-success-field-row">
                    <div style={{ flex: 1 }}>
                      <div className="admin-label-text" style={{ marginBottom: 4 }}>判断字段名</div>
                      <input
                        className="admin-input"
                        placeholder='如 success 或 code'
                        value={cfg.success_field}
                        onChange={(e) => setCfg((p) => ({ ...p, success_field: e.target.value }))}
                      />
                    </div>
                    <div className="admin-success-eq">=</div>
                    <div style={{ flex: 1 }}>
                      <div className="admin-label-text" style={{ marginBottom: 4 }}>成功时的值</div>
                      <input
                        className="admin-input"
                        placeholder='如 true 或 0'
                        value={cfg.success_value}
                        onChange={(e) => setCfg((p) => ({ ...p, success_value: e.target.value }))}
                      />
                    </div>
                  </div>

                  {/* 分隔 */}
                  <div className="admin-success-or">
                    <span>或</span>
                  </div>

                  {/* 状态码 */}
                  <div>
                    <div className="admin-label-text" style={{ marginBottom: 4 }}>
                      指定成功 HTTP 状态码
                      <span className="admin-hint" style={{ marginLeft: 8 }}>逗号分隔，如 200,201；为空则 &lt;400 即成功</span>
                    </div>
                    <input
                      className="admin-input"
                      placeholder="200,201"
                      value={cfg.success_http_codes}
                      onChange={(e) => setCfg((p) => ({ ...p, success_http_codes: e.target.value }))}
                    />
                  </div>

                  {/* 当前生效规则预览 */}
                  <SuccessRulePreview cfg={cfg} />
                </div>
              </div>
            </div>

            <div className="admin-actions" style={{ marginTop: 16 }}>
              <button className="btn-primary" onClick={handleSave} disabled={saving}>
                {saving ? "保存中..." : saveOk ? "✓ 已保存" : "保存配置"}
              </button>
              {saveOk && (
                <button className="btn-outline" onClick={() => setActiveStep("init")}>
                  下一步：执行初始化 →
                </button>
              )}
            </div>

            {/* ── Payload 预览 ── */}
            <PayloadPreview />
          </div>
        );

      // ── 初始化 ──
      case "init":
        return (
          <div className="admin-content-body">
            <div className="admin-content-title">⚡ 初始化同步数据</div>
            <p className="admin-content-desc">
              清空 DB 中的所有同步记录，重新从所有活跃会话读取消息并写入，状态全部置为「未同步」。<br />
              <strong>换服务地址、修改数据范围配置后，需重新初始化。</strong>
            </p>

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
                  : `✓ 初始化完成：写入 ${initResult.total} 条消息（${initResult.conversations} 个会话），全部标记为未同步`}
              </div>
            )}

            <div className="admin-actions" style={{ marginTop: 16 }}>
              <button
                className="btn-primary"
                style={{ background: "#744210", borderColor: "#c05621" }}
                onClick={handleInitialize}
                disabled={initializing}
              >
                {initializing ? "初始化中..." : "⚡ 执行初始化"}
              </button>
              <button className="btn-outline" onClick={fetchStats}>刷新统计</button>
              {initResult && !initResult.error && (
                <button className="btn-outline" onClick={() => setActiveStep("monitor")}>
                  下一步：启动监控 →
                </button>
              )}
            </div>
          </div>
        );

      // ── 监控 ──
      case "monitor":
        return (
          <div className="admin-content-body">
            <div className="admin-content-title">📡 启动监控</div>
            <p className="admin-content-desc">
              每 {POLL_INTERVAL} 秒自动扫描所有活跃会话，检测变化后更新 DB，并将所有未同步记录上传到目标服务器。
            </p>

            {/* 前置检查提示 */}
            {!cfg.enabled && <div className="admin-preflight-warn">⚠ 请先在「上传配置」中启用监控上传并保存</div>}
            {cfg.enabled && !cfg.url.trim() && <div className="admin-preflight-warn">⚠ 请先在「上传配置」中填写目标上传地址并保存</div>}
            {cfg.enabled && cfg.url.trim() && syncStats && syncStats.total === 0 && (
              <div className="admin-preflight-warn">⚠ DB 中暂无数据，请先执行「初始化」</div>
            )}

            {/* 同步统计概览 */}
            {syncStats && syncStats.total > 0 && (
              <div className="admin-sync-stats" style={{ marginBottom: 16 }}>
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
              </div>
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

            <div className="admin-log-box" ref={logRef} style={{ marginTop: 12 }}>
              {monitorLog.length === 0
                ? <div className="admin-log-empty">暂无日志，启动监控后将在此显示运行状态</div>
                : monitorLog.map((entry, i) => (
                  <div key={i} className={`admin-log-entry log-${entry.type}`}>
                    <span className="admin-log-ts">{entry.ts}</span>
                    <span className="admin-log-msg">{entry.msg}</span>
                  </div>
                ))}
            </div>

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
        );

      default:
        return null;
    }
  }

  return (
    <div className="admin-panel">
      <div className="admin-panel-header">
        <h2>管理配置</h2>
        <p className="admin-panel-desc">以下功能仅在管理员模式下可见，普通启动方式无法访问。</p>
      </div>

      <div className="admin-layout">
        {/* ── 左侧步骤导航 ── */}
        <div className="admin-nav">
          {STEPS.map((step, idx) => {
            const badge = stepBadge(step.key);
            return (
              <button
                key={step.key}
                className={`admin-nav-item ${activeStep === step.key ? "active" : ""}`}
                onClick={() => setActiveStep(step.key)}
              >
                <div className="admin-nav-step-num">{idx + 1}</div>
                <div className="admin-nav-step-body">
                  <div className="admin-nav-step-icon">{step.icon}</div>
                  <div className="admin-nav-step-label">{step.label}</div>
                </div>
                <div className={`admin-nav-badge badge-${badge}`}>
                  {badge === "running" ? "运行中"
                    : badge === "ok" ? "✓"
                    : badge === "warn" ? "!"
                    : "—"}
                </div>
              </button>
            );
          })}
        </div>

        {/* ── 右侧内容区 ── */}
        <div className="admin-content">
          {renderContent()}
        </div>
      </div>
    </div>
  );
}
