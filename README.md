# WorkBuddy 会话管理器（前后端分离版）

基于 `FastAPI + React(Vite)` 的本地会话管理工具，用于查看、导出、分享、删除和恢复 WorkBuddy 本地历史会话，并提供工作空间管理功能。

> 界面功能图文说明请查看 **[FEATURES.md](./FEATURES.md)**

## 目录结构

- `servers/`：后端服务（FastAPI）
- `frontend/`：前端项目（React + Vite）

后端当前采用按职责分层：

```text
servers/
  app/
    main.py                 # 应用装配（FastAPI/CORS/静态托管，读取 WORKBUDDY_ADMIN 环境变量）
    api/
      router.py             # API 总路由聚合
      routes/
        health.py           # 健康检查
        sessions.py         # 会话列表
        chat.py             # 会话聊天记录
        transfer.py         # 导入/导出
        delete.py           # 删除会话（彻底删除 DB 记录与本地文件）
        restore.py          # 恢复逻辑删除会话
        title.py            # 修改会话标题
        workspaces.py       # 工作空间列表与删除
        admin.py            # 管理员接口（模式状态、监控配置、上传触发）
    services/
      common.py             # 通用工具（时间/JSON/transcript索引等）
      session_service.py    # sessions 业务聚合
      chat_service.py       # chat 读取与解析
      export_service.py     # 导出（原始会话/HTML）
      import_service.py     # ZIP 导入
      delete_service.py     # DB与本地文件删除
      monitor_service.py    # 数据监控上传（指纹缓存/变化检测/HTTP推送）
    schemas/
      session.py            # 请求/响应模型
    core/
      settings.py           # 环境变量与路径配置
      admin_state.py        # 管理员模式全局状态
      monitor_config.py     # 监控上传配置持久化（.monitor_config.json）
      monitor_db.py         # 监控同步状态 SQLite 数据库（monitor_sync.db，启动时自动创建）
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

普通模式：

```bash
cd servers
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 9877
```

管理员模式（Windows PowerShell）：

```powershell
cd servers
$env:WORKBUDDY_ADMIN="1"; python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 9877
```

管理员模式（Windows CMD）：

```cmd
cd servers
set WORKBUDDY_ADMIN=1 && python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 9877
```

管理员模式（Linux / macOS）：

```bash
cd servers
WORKBUDDY_ADMIN=1 python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 9877
```

启动后访问 `http://localhost:9877?admin=true` 即可进入管理员界面。

后端接口：

- `GET /api/health`
- `GET /api/sessions`：读取并聚合本地会话基础数据（含逻辑删除字段 `deletedAt`）
- `GET /api/session/{conversationId}/chat`：读取指定会话的完整聊天记录（用户/AI/工具消息）
- `POST /api/export`：导出会话归档 ZIP
- `POST /api/export-chat`：导出聊天 HTML ZIP（支持 `multipart/form-data`：`ids`、`selectedMediaPaths`、`uploads`）
- `POST /api/share-chat`：生成可外网访问的分享链接（支持媒体选择与上传）
- `GET /shared/{shareId}/index.html`：访问分享页面（后端静态托管）
- `GET /api/local/workspace-files`：读取指定 `cwd` 的工作目录文件数据
- `GET /api/local/open-file`：打开本地文件（浏览器内联）
- `POST /api/local/locate-file`：在系统文件管理器中定位文件
- `POST /api/import`：导入会话归档 ZIP
- `POST /api/delete`：彻底删除会话及本地关联数据（从 DB 中物理删除记录）
- `POST /api/restore`：恢复逻辑删除的会话（从 DB JSON 中移除 `deletedAt` 字段，使客户端重新识别）
- `PUT /api/session/{conversationId}/title`：修改指定会话的标题
- `GET /api/workspaces`：按工作目录聚合所有会话，返回工作空间列表
- `DELETE /api/workspace`：删除工作目录（仅允许 DB 中该 cwd 下无任何会话记录时操作）

### 管理员模式接口（需以管理员模式启动）

- `GET /api/admin/status`：查询当前是否为管理员模式（所有人可访问，用于前端判断）
- `GET /api/admin/monitor/config`：获取监控上传配置
- `POST /api/admin/monitor/config`：保存监控上传配置
- `POST /api/admin/monitor/initialize`：初始化同步数据库（清空并重新写入所有活跃会话消息，状态置为未同步）
- `GET /api/admin/monitor/stats`：获取 DB 中消息的同步状态统计（总数/已同步/未同步/涉及会话数）
- `GET /api/admin/monitor/messages`：分页查询 DB 中的消息记录（支持按 conversation_id、synced 过滤）
- `POST /api/admin/monitor/upload`：立即上传所有未同步记录（可指定单个会话）
- `POST /api/admin/monitor/poll`：执行一次完整轮询（扫描变化 + 上传未同步）
- `GET /api/admin/monitor/errors`：获取最近上传失败错误日志
- `GET /api/admin/machine-info`：获取本机环境信息（主机名、域账号、内外网IP、OS等）
- `POST /api/admin/machine-info/refresh`：强制重新采集机器信息（公网IP变化时使用）


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
      SessionHeader.jsx          # 顶部标题区（含自动刷新倒计时）
      SessionStats.jsx           # 统计卡片区（含逻辑删除数量）
      SessionToolbar.jsx         # 筛选与操作栏
      SessionTable.jsx           # 会话表格
      Pagination.jsx             # 分页条（含显示条数）
      SessionDetailModal.jsx     # 会话详情弹窗（含标题编辑、逻辑删除恢复）
      DeleteConfirmModal.jsx     # 删除确认弹窗
      ProcessingModal.jsx        # 全屏处理中遮罩
      ShareConfigModal.jsx       # 导出/分享配置弹窗（媒体选择/上传）
      ShareResultModal.jsx       # 分享结果弹窗（复制/打开链接）
      ModelConfigPanel.jsx       # 模型配置页面
      WorkspacePanel.jsx         # 工作空间页面（工作目录聚合管理）
      AdminPanel.jsx             # 管理配置页面（仅管理员模式可见）

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

前端以开发模式启动后，根据后端启动方式访问对应地址：

- 普通模式：`http://localhost:5173` 或 `http://<局域网IP>:5173`
- 管理员模式：`http://localhost:5173?admin=true` 或 `http://<局域网IP>:5173?admin=true`

> Vite 已配置 `host: "0.0.0.0"`，局域网内其他设备可通过 IP 直接访问前端开发服务器。

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
- `NGROK_PATH`：本地 ngrok 可执行文件路径（显式指定，优先级最高）
- `NGROK_AUTHTOKEN`：ngrok 认证 token

> 若服务已部署在公网地址，则会优先直接使用当前请求域名；若仅本地地址，则会尝试通过 ngrok 建立临时公网访问。

### ngrok 内置二进制（离线可用）

项目已在 `servers/bin/ngrok.exe`（Windows）预置了 ngrok 可执行文件，**无需外网下载**。

ngrok 路径解析优先级：
1. 环境变量 `NGROK_PATH`（用户显式指定）
2. 项目内置 `servers/bin/ngrok.exe`（Windows）/ `servers/bin/ngrok`（Linux/macOS）
3. pyngrok 默认行为（首次使用时从官网下载，需要外网）

若在 Linux/macOS 环境部署，可手动将对应平台的 ngrok 二进制放到 `servers/bin/ngrok` 并赋予执行权限：
```bash
chmod +x servers/bin/ngrok
```

## 字段映射清单


### 任务列表与基础信息（`GET /api/sessions`）

| 页面字段 | 返回字段 | 来源位置 |
|---|---|---|
| 任务ID | `conversationId` | `%APPDATA%\WorkBuddy\codebuddy-sessions.vscdb` -> `ItemTable.key=session:{conversationId}` |
| 标题 | `title` | 同上，`ItemTable.value` JSON |
| 状态 | `status` | 同上，`ItemTable.value` JSON |
| 工作目录 | `cwd` / `cwdExists` | 同上，`cwdExists` 为本地路径存在性检查 |
| 创建/更新时间 | `createdAtTs`/`updatedAtTs` + `createdAt`/`updatedAt` | 同上，时间戳转文本 |
| 逻辑删除时间 | `deletedAtTs` / `deletedAt` | 同上，客户端删除后写入的 `deletedAt` 时间戳；正常会话无此字段 |
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

### 工作空间列表（`GET /api/workspaces`）

| 返回字段 | 含义 |
|---|---|
| `cwd` | 工作目录绝对路径 |
| `cwdExists` | 本地目录是否存在 |
| `totalSessions` | 该工作目录下的会话总数（含逻辑删除） |
| `activeSessions` | 正常会话数（无 `deletedAt` 字段） |
| `deletedSessions` | 逻辑删除会话数（有 `deletedAt` 字段） |
| `canDelete` | 是否可删除目录（DB 中该 cwd 下无任何记录时为 `true`） |
| `sessions[*]` | 该工作目录下的会话列表（含 `isDeleted` 标记） |

## 逻辑删除说明

WorkBuddy 客户端删除任务时，不会物理删除数据库记录，而是在会话 JSON 中写入 `deletedAt` 时间戳字段，客户端据此将该会话从列表中隐藏。

本后台管理的处理逻辑：

| 操作 | 行为 |
|---|---|
| **恢复**（`POST /api/restore`） | 从 DB JSON 中彻底移除 `deletedAt` 字段（而非置 0），使会话结构与正常会话完全一致，客户端重启后即可重新显示 |
| **彻底删除**（`POST /api/delete`） | 从 DB 中物理删除记录，并清理本地 todos、file-changes、history 等关联文件 |

> **注意**：恢复操作需要重启 WorkBuddy 客户端后生效。

## 一键启动（推荐）

项目根目录提供两种启动脚本，双击即可完成自动更新、环境检查、依赖安装并启动后端服务，浏览器会自动打开。

**适用系统：** Windows

### 普通启动

**使用方式：** 直接双击 `start_server.bat`

**执行流程：**

| 步骤 | 内容 | 说明 |
|---|---|---|
| 第 1 步 | 检测 Python 环境 | 检查是否已安装 Python 3.9+，未安装或版本过低时给出引导提示 |
| 第 2 步 | 拉取最新程序 | 检测 Git 是否可用并执行 `git pull`；无法更新时由用户选择跳过或退出，不会自动跳过 |
| 第 3 步 | 安装所需组件 | 自动执行 `pip install -r requirements.txt`，已安装的依赖会跳过，首次运行约需 1-3 分钟 |
| 第 4 步 | 启动服务 | 启动 FastAPI 后端，3 秒后自动用默认浏览器打开 `http://localhost:9877` |

### 管理员模式启动

**使用方式：** 直接双击 `start_server_admin.bat`

与普通启动流程相同，但会额外设置环境变量 `WORKBUDDY_ADMIN=1`，激活管理员模式，浏览器自动打开 `http://localhost:9877?admin=true`。

管理员模式下，页面顶部导航会出现「🔧 管理配置」入口，可访问管理功能模块（见下方[管理员模式](#管理员模式)说明）。

> 运行期间请保持命令窗口开启，关闭窗口即停止服务。

**前提条件：**
- 已安装 Python 3.9 或以上版本，且安装时勾选了 "Add Python to PATH"
- Git（可选）：安装后可享受自动更新功能，下载地址：https://git-scm.com/download/win

---

## 管理员模式

### 激活方式

启动时设置环境变量 `WORKBUDDY_ADMIN=1`（推荐使用 `start_server_admin.bat`），然后在浏览器 URL 中附加 `?admin=true`：

```
http://localhost:9877?admin=true
```

前端会向后端 `GET /api/admin/status` 确认是否真的以管理员模式启动，**两者同时满足才会显示管理菜单**，单独修改 URL 参数无效。

### 管理配置页面

进入「🔧 管理配置」页面后，目前包含以下功能模块：

#### 本机环境信息

页面顶部展示当前运行机器的环境信息，这些信息会随每次上传数据一起发送到目标服务器，用于接收端判断数据来源。

| 字段 | 说明 |
|---|---|
| 主机名 | `socket.gethostname()` 获取 |
| 域账号 | Windows 下取 `USERDOMAIN\USERNAME`，其他系统取 `USER` |
| 主网卡 IP（`local_ip`） | 通过 UDP connect trick 让路由表自动选出出口 IP，天然排除 VMware/VirtualBox/VPN 等虚拟网卡 |
| 所有本地 IP（`local_ips`） | 枚举本机所有非回环网卡 IP（含虚拟网卡，供参考） |
| 公网 IP | 依次请求 `ipify` / `ifconfig.me` / `ip.sb` 获取，全部失败则留空 |
| 操作系统 | 系统名称、发行版本、完整版本号 |
| 架构 | 处理器架构（如 AMD64） |

> 机器信息在服务进程启动后**只采集一次**并缓存，避免重复请求外网。公网 IP 变化时可点击「重新采集」按钮手动刷新。

#### 数据监控上传

实时监控所有活跃会话的对话内容，检测到新消息或内容变化时自动上传到指定服务器，可用于行为分析等场景。

同步状态通过本地 SQLite 数据库（`servers/monitor_sync.db`）持久化，服务重启后状态不丢失。

**操作流程（三步）：**

```
第一步：保存配置（协议 / 目标地址 / 数据范围等）
    ↓
第二步：执行初始化（⚡ 每次换地址或修改数据范围后必须重新执行）
    清空 DB 全部记录，重新扫描所有活跃会话，写入消息，状态全部置为「未同步」
    ↓
第三步：启动监控（每 10s 自动轮询）
    扫描会话变化 → 更新 DB → 上传未同步记录 → 标记已同步
```

**核心特性：**

| 特性 | 说明 |
|---|---|
| SQLite 持久化 | 同步状态写入本地 DB，服务重启后已同步记录不会重复上传 |
| 变化检测 | 对每条消息计算 MD5 指纹（基于 role/text/toolEvents/isComplete），内容变化时重置为未同步 |
| 去重上传 | 已同步且无变化的消息不会重复推送 |
| 初始化重置 | 换服务地址或修改数据范围后，执行初始化可清空 DB 并重新全量同步 |
| 实时轮询 | 前端每 10 秒自动检测一次，发现变化立即上传 |
| 失败重试 | 上传失败时按配置次数自动重试，错误日志在页面内实时展示 |

**DB 同步状态字段说明：**

| 字段 | 说明 |
|---|---|
| `id` | `conversationId:messageId`（主键） |
| `conversation_id` | 会话 ID |
| `message_id` | 消息 ID |
| `role` | 角色（user / assistant / tool） |
| `fingerprint` | 消息内容 MD5 指纹 |
| `synced` | 0 = 未同步，1 = 已同步 |
| `synced_at` | 同步时间 |
| `updated_at` | 记录最后更新时间 |

**上传数据范围（可选）：**

| 维度 | 选项 | 默认 |
|---|---|---|
| 对话类型 | 基础对话（user/assistant 文本，不含工具调用）/ 完整对话（含工具调用/结果） | 基础对话 ✓ |
| 角色筛选 | user 消息 / assistant 消息 | 仅 user ✓ |

**上传数据格式（HTTP/HTTPS POST JSON）：**

```json
{
  "conversationId": "xxx",
  "timestamp": 1712345678000,
  "machine": {
    "hostname": "PC-NAME",
    "domain_user": "DOMAIN\\username",
    "local_ip": "192.168.1.100",
    "local_ips": ["192.168.1.100", "192.168.154.1", "fe80::..."],
    "public_ip": "1.2.3.4",
    "os": "Windows",
    "os_release": "10",
    "os_version": "10.0.19045",
    "machine": "AMD64",
    "python_version": "3.11.0",
    "collected_at": "2026-04-10 16:30:00"
  },
  "messages": [
    {
      "id": "msg-id",
      "role": "user",
      "text": "用户输入内容",
      "createdAt": "2026-04-10 16:00:00"
    }
  ]
}
```

**支持协议：** HTTPS POST（默认）/ HTTP POST

**配置项说明：**

| 配置项 | 默认值 | 说明 |
|---|---|---|
| 启用监控上传 | 关 | 总开关，关闭时不会进行任何上传 |
| 上传协议 | HTTPS | HTTP 或 HTTPS |
| 目标上传地址 | 空 | 接收数据的服务器 URL |
| 自定义请求头 | 空 | 可添加鉴权 Token 等 Header |
| 失败重试次数 | 3 | 上传失败后的重试次数（1-10） |
| 上传 user 消息 | ✓ | 是否包含用户发送的消息 |
| 上传 assistant 消息 | 关 | 是否包含 AI 回复内容 |

**本地文件说明：**

| 文件 | 说明 |
|---|---|
| `servers/monitor_sync.db` | 同步状态 SQLite 数据库，服务启动时自动创建，**不提交 Git** |
| `servers/.monitor_config.json` | 监控上传配置（含服务地址/Token等），**不提交 Git** |

> 两个文件均已加入 `.gitignore`，克隆仓库后首次启动服务会自动创建 `monitor_sync.db` 及表结构。

---

## 根目录快捷命令


```bash
npm run dev:frontend
npm run build:frontend
```

> 后端启动命令在 `servers` 目录执行（见上方）。
