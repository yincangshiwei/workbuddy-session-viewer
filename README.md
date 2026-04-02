# WorkBuddy 会话管理器（前后端分离版）

基于 `FastAPI + React(Vite)` 的本地会话管理工具，用于查看、导出、分享和删除 WorkBuddy 本地历史会话。


## 目录结构

- `servers/`：后端服务（FastAPI）
- `frontend/`：前端项目（React + Vite）

后端当前采用按职责分层：

```text
servers/
  app/
    main.py                 # 应用装配（FastAPI/CORS/静态托管）
    api/
      router.py             # API 总路由聚合
      routes/
        health.py           # 健康检查
        sessions.py         # 会话列表
        chat.py             # 会话聊天记录
        transfer.py         # 导入/导出
        delete.py           # 删除会话
    services/
      common.py             # 通用工具（时间/JSON/transcript索引等）
      session_service.py    # sessions 业务聚合
      chat_service.py       # chat 读取与解析
      export_service.py     # 导出（原始会话/HTML）
      import_service.py     # ZIP 导入
      delete_service.py     # DB与本地文件删除
    schemas/
      session.py            # 请求/响应模型
    core/
      settings.py           # 环境变量与路径配置
```

## 后端（servers）

### 技术栈

- FastAPI
- Uvicorn

### 架构约定（维护建议）

- `routes`：仅处理 HTTP 协议（参数校验、状态码、响应结构）
- `services`：承载业务逻辑（会话聚合、导入导出、删除流程）
- `schemas`：统一请求/响应模型，减少隐式字段漂移
- `core`：集中管理环境变量与路径，避免硬编码散落

### 启动（开发）

```bash
cd servers
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 9877
```

后端接口：

- `GET /api/health`
- `GET /api/sessions`：读取并聚合本地会话基础数据
- `GET /api/session/{conversationId}/chat`：读取指定会话的完整聊天记录（用户/AI/工具消息）
- `POST /api/export`：导出会话归档 ZIP
- `POST /api/export-chat`：导出聊天 HTML ZIP（支持 `multipart/form-data`：`ids`、`selectedMediaPaths`、`uploads`）
- `POST /api/share-chat`：生成可外网访问的分享链接（支持媒体选择与上传）
- `GET /shared/{shareId}/index.html`：访问分享页面（后端静态托管）
- `GET /api/local/workspace-files`：读取指定 `cwd` 的工作目录文件数据
- `GET /api/local/open-file`：打开本地文件（浏览器内联）
- `POST /api/local/locate-file`：在系统文件管理器中定位文件
- `POST /api/import`：导入会话归档 ZIP
- `POST /api/delete`：删除会话及本地关联数据


## 前端（frontend）

### 技术栈

- React 18
- Vite 5

### 当前前端模块结构

```text
frontend/
  src/
    App.jsx                      # 页面容器：状态编排与业务流转
    main.jsx                     # 应用入口
    styles.css                   # 全局样式
    constants/
      session.js                 # 会话页面常量（分页大小、状态色）
    utils/
      session.js                 # 会话页面工具函数（复制/格式化/文本提取）
    components/
      SessionHeader.jsx          # 顶部标题区
      SessionStats.jsx           # 统计卡片区
      SessionToolbar.jsx         # 筛选与操作栏
      SessionTable.jsx           # 会话表格
      Pagination.jsx             # 分页条
      SessionDetailModal.jsx     # 会话详情弹窗
      DeleteConfirmModal.jsx     # 删除确认弹窗
      ProcessingModal.jsx        # 全屏处理中遮罩
      ShareConfigModal.jsx       # 导出/分享配置弹窗（媒体选择/上传）
      ShareResultModal.jsx       # 分享结果弹窗（复制/打开链接）
      ModelConfigPanel.jsx       # 模型配置页面

```

### 架构约定（维护建议）

- `App.jsx`：只做页面级状态管理、接口编排、组件组装
- `components/*`：只负责展示与交互，不承载跨模块业务逻辑
- `utils/*`：沉淀纯函数，避免在组件中重复实现
- `constants/*`：集中维护页面常量，避免魔法数字/字符串散落

### 启动（开发）

```bash
cd frontend
npm install
npm run dev
```

开发阶段通过 Vite 代理 `/api` 到 `http://127.0.0.1:9877`。

## 生产构建与部署模式

前端构建结果直接输出到后端静态目录：`servers/static`。

```bash
cd frontend
npm run build
```

然后只需启动 FastAPI，后端会直接托管前端静态资源（同端口提供页面和 API）。

## 数据来源

默认读取 `%APPDATA%\WorkBuddy` 下的数据，可通过环境变量覆盖路径：

- `WORKBUDDY_BASE`
- `WORKBUDDY_SESSIONS_DB`
- `WORKBUDDY_TODOS_BASE`
- `WORKBUDDY_FILE_CHANGES_BASE`
- `WORKBUDDY_HISTORY_BASE`
- `WORKBUDDY_MEDIA_BASE`
- `WORKBUDDY_TRANSCRIPTS_BASE`（完整对话 transcript 根目录，默认 `%LOCALAPPDATA%\WorkBuddyExtension\Data`）
- `WORKBUDDY_SHARE_BASE`（分享页面落盘目录，默认 `%LOCALAPPDATA%\WorkBuddySessionViewer\shared`）

分享功能相关环境变量：

- `WORKBUDDY_SHARE_TTL_SECONDS`：分享目录过期清理时间（默认 `86400`，最小 `300`）
- `WORKBUDDY_SHARE_PUBLIC_BASE_URL`：显式指定公网访问前缀（优先级最高）
- `WORKBUDDY_SHARE_PORT`：创建公网隧道时使用的端口（默认从请求 URL 推断）
- `NGROK_PATH`：本地 ngrok 可执行文件路径（避免运行时下载）
- `NGROK_AUTHTOKEN`：ngrok 认证 token

> 若服务已部署在公网地址，则会优先直接使用当前请求域名；若仅本地地址，则会尝试通过 ngrok 建立临时公网访问。

## 字段映射清单


### 任务列表与基础信息（`GET /api/sessions`）

| 页面字段 | 返回字段 | 来源位置 |
|---|---|---|
| 任务ID | `conversationId` | `%APPDATA%\WorkBuddy\codebuddy-sessions.vscdb` -> `ItemTable.key=session:{conversationId}` |
| 标题 | `title` | 同上，`ItemTable.value` JSON |
| 状态 | `status` | 同上，`ItemTable.value` JSON |
| 工作目录 | `cwd` / `cwdExists` | 同上，`cwdExists` 为本地路径存在性检查 |
| 创建/更新时间 | `createdAtTs`/`updatedAtTs` + `createdAt`/`updatedAt` | 同上，时间戳转文本 |
| Todos | `todos` | `%APPDATA%\WorkBuddy\User\globalStorage\tencent-cloud.coding-copilot\todos\{conversationId}.json` |
| 文件变更 | `fileChanges[*]` | `%APPDATA%\WorkBuddy\User\globalStorage\tencent-cloud.coding-copilot\file-changes\{conversationId}\*.json` |
| 媒体文件 | `mediaFiles[*]` | `%APPDATA%\WorkBuddy\User\globalStorage\tencent-cloud.coding-copilot\media-index\*.json` |
| 关联对话 | `related` | 同一 `cwd` 下其它会话聚合 |

### 完整对话记录（`GET /api/session/{conversationId}/chat`）

| 返回字段 | 含义 | 来源位置 |
|---|---|---|
| `conversationId` | 会话ID | 路径参数 |
| `indexPath` | 实际命中的 transcript 索引文件 | `%LOCALAPPDATA%\WorkBuddyExtension\Data\...\history\...\{conversationId}\index.json` |
| `messageCount` | 消息总数 | `index.json.messages` 长度 |
| `messages[*].id` | 消息ID | `index.json.messages[*].id` |
| `messages[*].role` | 角色（`user`/`assistant`/`tool`） | `index.json.messages[*].role` |
| `messages[*].type` | 消息类型 | `index.json.messages[*].type` |
| `messages[*].isComplete` | 是否完整 | `index.json.messages[*].isComplete` |
| `messages[*].createdAtTs` / `createdAt` | 消息时间戳/文本时间 | `messages/{messageId}.json` 文件创建时间（后端换算） |
| `messages[*].requestId` | 请求ID（若存在） | `messages/{messageId}.json` -> `extra.requestId` |
| `messages[*].modelId` / `modelName` / `mode` | 模型标识、模型名、会话模式 | `messages/{messageId}.json` -> `extra` / `extra.sourceContentBlocks[*]._meta.codebuddy.ai` |
| `messages[*].text` | 文本化消息内容（含工具调用标识） | `messages/{messageId}.json` -> `message`(JSON字符串) -> `content[*]` |
| `messages[*].toolEvents` | 工具调用/结果事件数组 | 同上 `content[*]` 解析 |
| `messages[*].messagePath` | 本地消息文件绝对路径 | `messages/{messageId}.json` |
| `messages[*].raw` | 原始消息对象（透传） | `messages/{messageId}.json` -> `message` 反序列化结果 |
| `requests` | 请求分组与token统计 | `index.json.requests` |

### 工作目录文件（`GET /api/local/workspace-files`）

| 页面字段 | 返回字段 | 来源位置 |
|---|---|---|
| 工作目录路径 | `cwd` | 请求参数 `cwd` 对应的本地目录绝对路径 |
| 工作目录文件数量（Tab） | `fileCount` | 后端递归扫描 `cwd` 下全部文件计数 |
| 工作目录目录数量（详情） | `dirCount` | 后端递归扫描 `cwd` 下全部子目录计数 |
| 工作目录文件列表 | `tree.children`（前端扁平化后展示） | 本地文件系统目录树（按名称排序） |
| 文件名/相对路径/大小 | `tree.children[*].name` / `relativePath` / `size` | 本地文件系统文件元数据 |

## 根目录快捷命令


```bash
npm run dev:frontend
npm run build:frontend
```

> 后端启动命令在 `servers` 目录执行（见上方）。
