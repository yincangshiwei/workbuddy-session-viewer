# WorkBuddy 会话管理器（前后端分离版）

基于 `FastAPI + React(Vite)` 的本地会话管理工具，用于查看和删除 WorkBuddy 本地历史会话。

## 目录结构

- `servers/`：后端服务（FastAPI）
- `frontend/`：前端项目（React + Vite）

## 后端（servers）

### 技术栈

- FastAPI
- Uvicorn

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
- `POST /api/delete`：删除会话及本地关联数据


## 前端（frontend）

### 技术栈

- React 18
- Vite 5

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
| `messages[*].isComplete` | 是否完整 | `index.json.messages[*].isComplete` |
| `messages[*].text` | 文本化消息内容（含工具调用标识） | `messages/{messageId}.json` -> `message`(JSON字符串) -> `content[*]` |
| `messages[*].raw` | 原始消息对象（透传） | 同上 |
| `requests` | 请求分组与token统计 | `index.json.requests` |

## 根目录快捷命令


```bash
npm run dev:frontend
npm run build:frontend
```

> 后端启动命令在 `servers` 目录执行（见上方）。
