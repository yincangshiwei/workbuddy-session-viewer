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
- `GET /api/sessions`：读取并聚合本地会话数据
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

## 根目录快捷命令

```bash
npm run dev:frontend
npm run build:frontend
```

> 后端启动命令在 `servers` 目录执行（见上方）。
