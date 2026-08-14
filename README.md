# 临时root

一个本地 Web 工具，通过 adb 驱动设备上的 xpad2 二进制，用 IonStack 内核利用取得**临时 Root** 并安装 KernelSU / SukiSU 等组件。前端采用 **Material Design 3** 设计语言（参考 `md3.html`）。

## 架构

```
React 前端 (Vite + TS + MD3)  ← REST + WebSocket →  FastAPI 后端  ← adb →  设备 /data/local/tmp/xpad2
```

前端只保留核心操作面板：设备选择、组件多选（install 入参）、临时 Root 状态仪表、一键安装与实时日志。后端启动时自动把 `tools\xpad2\xpad2` 推送到设备的 `/data/local/tmp/xpad2`。

## 前置

- Node.js 20+（`node -v` / `npm -v`）
- Python 3.11+（已附一份 3.12 到 `D:\superroot\python`；如无则自行安装）
- 一台已授权 USB/无线调试的 XPad2 / PD2P 设备

## 首次准备

依赖已固化在项目内，无需额外下载：

- adb：`tools\platform-tools\adb.exe`（缺失时运行 `tools\bootstrap.ps1` 补齐）
- xpad2 二进制：`tools\xpad2\xpad2`（已固定）

## 一键启动

双击 **`start.bat`**：

- 自动检测已授权设备并推送 xpad2（真实模式）
- 启动后端（127.0.0.1:8000）与前端（localhost:5173），并自动打开浏览器
- 后端启动时也会自动兜底推送 xpad2

无设备演示（mock 模式，install 等命令返回回放数据）：

```powershell
.\start-mock.bat
```

### 手动启动（可选）

```powershell
# 终端 1：后端
& "D:\superroot\python\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --app-dir backend

# 终端 2：前端
cd frontend
npm install
npm run dev
```

浏览器打开 http://localhost:5173 。

## 使用

1. 顶部「设备」下拉选择已授权的目标设备。
2. 在「安装组件」中勾选要安装的组件（`完整套装`/`KernelSU`/`SukiSU` 等）。
3. 点击「开始安装」，实时日志会滚动显示临时 Root 探测与安装进度。
4. 安装完成后按提示重启设备使 Root 生效。

## 测试

```powershell
cd backend
& "D:\superroot\python\python.exe" -m pytest -v
```

## 注意

- 默认仅监听 127.0.0.1，请勿暴露公网。
- 临时 Root 链可能导致设备重启或 kernel panic，仅在你有权处置的设备上使用。
