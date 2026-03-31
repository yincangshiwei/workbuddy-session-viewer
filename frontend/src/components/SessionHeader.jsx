export default function SessionHeader({ activePage, setActivePage }) {
  return (
    <div className="header">
      <h1>WorkBuddy 后台管理</h1>
      <p>数据来源：codebuddy-sessions.vscdb · todos · file-changes · media-index · %USERPROFILE%/.workbuddy/models.json</p>
      <div className="header-nav">
        <button
          className={`header-nav-btn ${activePage === "sessions" ? "active" : ""}`}
          onClick={() => setActivePage("sessions")}
        >
          会话管理
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

