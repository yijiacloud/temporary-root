# xpad2 Console

本地 Web 控制台，通过 adb 驱动设备上的 xpad2 二进制。后端 FastAPI + 前端 React(Vite + TypeScript + Tailwind)。

## 架构

```
React 前端 (Vite + TS + Tailwind)  ← REST + WebSocket →  FastAPI 后端  ← adb →  设备 /data/local/tmp/xpad2
```

后端把 xpad2 的每个命令封装成 REST/WebSocket 接口，前端提供设备下拉、组件状态仪表盘、命令执行面板和实时日志控制台。

## 前置

- Node.js 20+（`node -v` / `npm -v`）
- Python 3.11+（已附一份 3.12 到 `D:\superroot\python`；如无则自行安装）
- 一台已授权 USB/无线调试的 XPad2 / PD2P 设备

## 首次准备

依赖已固化在项目内，无需额外下载：

- adb：`tools\platform-tools\adb.exe`（缺失时运行 `tools\bootstrap.ps1` 补齐）
- xpad2 二进制：`tools\xpad2\xpad2`（已固定）

首次连接设备时推送一次：

```powershell
.\tools\push-xpad2.ps1        # 默认用 tools\xpad2\xpad2；可加 -Serial <serial>
```

> 若设备上已有可正常工作的 xpad2，请改用设备内更新（`xpad2 update`），不要裸 push 覆盖。

## 一键启动

双击 **`start.bat`**：

- 自动检测已授权设备并推送 xpad2（真实模式）
- 启动后端（127.0.0.1:8000）与前端（127.0.0.1:5173），并自动打开浏览器

无设备演示（mock 模式，所有命令返回回放数据）：

```powershell
.\start-mock.bat
```

### 手动启动（可选）

```powershell
# 终端 1：后端（用 D 盘 Python）
& "D:\superroot\python\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --app-dir backend

# 终端 2：前端
cd frontend
npm install
npm run dev
```

浏览器打开 http://127.0.0.1:5173 。

## 无设备演示（mock 模式）

后端以 mock 模式启动时，所有命令返回内置回放数据，无需设备/ADB：

```powershell
$env:XPAD2_MOCK = "1"
& "D:\superroot\python\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --app-dir backend
```

## 测试

```powershell
cd backend
& "D:\superroot\python\python.exe" -m pytest -v
```

## 注意

- 默认仅监听 127.0.0.1，请勿暴露公网。
- 临时 Root 链可能导致设备重启或 kernel panic，仅在你有权处置的设备上使用。
