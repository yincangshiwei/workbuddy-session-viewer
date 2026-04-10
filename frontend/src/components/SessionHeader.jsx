export default function SessionHeader({ activePage, setActivePage, autoRefreshing, countdown }) {
  return (
    <div className="header">
      <div className="header-title-row">
        <h1>WorkBuddy 后台管理</h1>
        <span className={`header-countdown ${autoRefreshing ? "active" : ""}`}>{autoRefreshing ? "..." : `${countdown}s`}</span>
      </div>
      <p>数据来源：codebuddy-sessions.vscdb · todos · file-changes · media-index · %USERPROFILE%/.workbuddy/models.json</p>
      <div className="header-nav">
        <button
          className={`header-nav-btn ${activePage === "sessions" ? "active" : ""}`}
          onClick={() => setActivePage("sessions")}
        >
          会话管理
        </button>
        <button
          className={`header-nav-btn ${activePage === "workspaces" ? "active" : ""}`}
          onClick={() => setActivePage("workspaces")}
        >
          工作空间
        </button>
        <button
          className={`header-nav-btn ${activePage === "models" ? "active" : ""}`}
          onClick={() => setActivePage("models")}
        >
          模型配置
        </button>
      </div>
    </div>
  );
}
