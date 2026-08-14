# xpad2 Web Console — 设计规格 (Spec)

- 日期：2026-08-14
- 状态：已确认方向，待用户审阅

## 1. 目标

构建一个 **Python(FastAPI) + React(Vite) 的网页控制台**，作为 xpad2-cli 的桌面控制面。
它通过 **adb** 驱动 Android 设备上 `/data/local/tmp/xpad2` 的二进制，把 xpad2 的约 20 个
命令转化为可视化的 Web 操作面板与实时日志仪表盘。

xpad2-cli 官方明确「不提供桌面 CLI/GUI」，本项目在其之上补充一个本地 Web 控制台，
不改动、不复刻 xpad2 本身，只做「调用 + 可视化 + 编排」。

## 2. 技术栈（已确认）

- 后端：FastAPI（含 `uvicorn`、原生 WebSocket、`asyncio.subprocess`）。
- 前端：React + Vite + TypeScript + TailwindCSS + 精选组件库。
- 调用链：Python 后端 → `adb -s <serial> shell /data/local/tmp/xpad2 <cmd>`。
- 运行环境：Windows 本机，Python 3.14（已知可用），adb 由 bootstrap 脚本补齐。

## 3. 架构

```
React 前端 (Vite + TS + Tailwind)
   │  REST（命令/状态） + WebSocket（实时日志流）
   ▼
FastAPI 后端
   ├── 设备层   device.py      adb devices -l / 选择 / serial 记忆
   ├── 命令层   commands.py    xpad2 命令注册表 + 参数化拼接与转义
   ├── 执行层   executor.py    异步 subprocess；长命令流式输出；取消/超时
   ├── 状态层   snapshot.py    轮询 status --json，缓存为组件快照
   └── adb 运行时 adb.py       封装 adb；路径配置；可用性探测；--mock 回放
```

单一职责与接口：

- 命令层只负责「由声明表拼接参数并做 shell 转义」。
- 执行层只负责「跑 + 流式回传 + 生命周期」。
- 设备层只负责「选对目标设备」。
- adb 运行时是唯一接触 `adb` 与 `subprocess` 的底层边界。

## 4. 关键组件

### 4.1 adb 运行时（adb.py）

- 统一入口 `run(command: list[str], serial: str | None) -> ...`，前缀 `adb [-s SERIAL] shell`。
- 参数转义：对 `root -- COMMAND ARG...` 这类含 `--` 与 shell 引号的命令，按 xpad2 的
  `shell_quote` 语义正确拼接；禁止用户输入直接拼进 shell。
- 启动探测：探明 adb 是否在 PATH、版本、是否有已连接设备；缺失时给出明确状态。
- `--mock` 模式：`XPAD2_MOCK=1` 或启动参数 `--mock` 时，返回内嵌回放数据
  （`status --json` 返回假 DeviceStatus，长命令返回假进度事件），供无设备自测。

### 4.2 命令注册表（commands.py）

一张声明式表，前端据此自动生成表单。每条包含：

```text
id | title | 只读? | 危险级别(none|confirm|danger) | 长运行? | args 定义 | flags 定义
```

完整命令清单（与 xpad2 `--help` 对齐）：

| id | 只读 | 危险 | 长运行 | 参数 |
|----|------|------|--------|------|
| version | ✓ | none | | |
| status | ✓ | none | | `--json` |
| list | ✓ | none | | |
| info | ✓ | none | | `COMPONENT` |
| doctor | ✓ | none | ✓ | |
| verify | ✓ | none | | `[COMPONENT]` |
| root | | danger | ✓ | `[-- COMMAND...]` |
| freeze | | confirm | | `ota` |
| unfreeze | | confirm | | `ota` |
| install | | danger | ✓ | `[组件...]` / `cli FILE [--name N]` / `apk FILE` |
| hooks | | danger | ✓ | `activate` / `disable` |
| repair | | confirm | ✓ | `COMPONENT` |
| cleanup | | confirm | ✓ | |
| logs | ✓ | none | | `export DIR` |
| cache | 部分只读* | none | | `path`/`list`/`verify`/`import DIR`/`prune`/`clear` |
| update | ✓(check)/变更 | confirm | ✓ | `--check`/`--version V`/`--offline`/`--reinstall`/`--allow-downgrade` |

内置组件枚举（供 install/doctor/info 选择）：`ota, ksu, suu, zygisk, vector,
ksu-manager, suu-manager, xpad-installer, installer-backup, boominstaller, full, suu-full`
（`lsposed` 为 `vector` 兼容别名）。

> \* `cache` 的 `path/list/verify` 为只读，`import/prune/clear` 为变更操作，前端据此分区。

### 4.3 执行层（executor.py）

- 快命令：同步子进程，返回 stdout/stderr/exit_code。
- 长命令：`asyncio.create_subprocess_exec`，逐行经 WebSocket 推送；维护 task id、
  状态（running/succeeded/failed/needs-reboot/cancelled）、可选取消、硬超时
  （默认 20 分钟，与 IonStack 上限一致，可配置）。
- `exit 75` 识别为「需要普通重启」的专门状态，不当作普通失败。

### 4.4 状态层（snapshot.py）

- `GET /api/status` 时执行 `xpad2 status --json`，解析为组件列表
  （`temporary-root` + 各组件 `{id, state, detail}`）。
- 前端渲染为状态徽章：`active`(绿) / `installed`(蓝) / `ready`(青) / `absent`(灰) /
  `outdated`/`incompatible`(黄) / `broken`/`needs-reboot`(红)。

## 5. API 契约

REST：

```
GET  /api/health           adb/设备/二进制 探测状态
GET  /api/devices          adb devices -l 列表
POST /api/devices/select   {serial} 记忆选择
GET  /api/status           status --json 快照
GET  /api/components       命令注册表 + 内核组件枚举
POST /api/exec             {command:[...], serial} 同步执行（快命令）
POST /api/run              {command:[...], serial} 创建长运行任务 → {task_id}
POST /api/run/{id}/cancel  取消任务
GET  /api/logs/export      logs export 触发并返回路径
```

WebSocket：

```
/ws/run/{task_id}          逐行 stdout/stderr + 事件(holder-attempt/progress/done/failed/needs-reboot)
```

## 6. 前端页面

单一管理台，左侧导航 + 主内容区：

1. **仪表盘 Dashboard**：设备下拉 + 连接状态；`status --json` 组件徽章墙；`doctor` 一键摘要；`action-required`/需要重启的醒目横幅。
2. **命令 Control**：由命令注册表驱动的表单 + 参数/flag 输入；只读/变更分区；危险操作二次确认弹窗。
3. **安装 Install**：组件多选（checkbox）拼装 `install ...`；`cli/apk` 文件路径输入。
4. **Root**：`root` / `root -- CMD`；长运行进度（holder 轮次）；结束后提示 cleanup。
5. **更新 Update**：`--check` 结果展示 + 一键 update/指定版本/离线包。
6. **日志 Logs**：实时 WebSocket 控制台（流式输出、语法着色、退出码/75 高亮）；`logs export` 下载。
7. **缓存 Cache**：path/list/verify/import/prune/clear 操作面板。

## 7. 错误处理

| 场景 | 行为 |
|------|------|
| adb 缺失 | 顶部引导 + 一键运行 bootstrap 下载 |
| 无设备 / unauthorized | 警告条 + 授权指引 |
| 命令 exit 75 | 高亮「需要普通重启」 |
| adb 进程被终止 | 任务标记 cancelled，前端即时体现 |
| 危险命令 | 二次确认 + 风险文案（临时 Root 可能重启/kernel panic） |

## 8. 测试策略

- 单元：命令参数拼接与转义（`root -- CMD`、`install cli`、`--cache-dir=`）；exit-code→状态映射。
- 集成：`--mock` 模式下全 API 契约 + WebSocket 流回放断言。
- 真实链路（尽力）：装好 adb 后，若有任意 Android 设备，跑通 `adb version` / `adb devices` /
  `adb shell echo`；对 XPad2 真实 Root 无法端到端复现，明确不承诺。

## 9. 目录结构

```
xpad2-console/
  backend/
    app/  __init__.py main.py adb.py commands.py executor.py snapshot.py
    tests/
    requirements.txt
  frontend/
    src/  components/ pages/ lib/
    package.json vite.config.ts tailwind.config.*
  tools/  bootstrap.ps1  bootstrap.sh  push-xpad2.ps1
  docs/   本 spec 与使用说明
  README.md
```

## 10. 交付范围

- 通用命令执行器（覆盖全部命令）。
- 专属面板：status/doctor、install、root、freeze/unfreeze ota、update、logs、cache。
- 设备下拉 + serial 记忆、实时日志流、危险操作确认。
- `tools/bootstrap.ps1`：下载 Android Platform Tools(adb)、下载 xpad2 arm64 Release、
  `adb push` + `chmod 700`。

## 11. 明确的非目标

- 不复制/修改 xpad2-cli 源码逻辑。
- 不做移动端、不做多用户鉴权、不做云部署。
- 不把 web 直接暴露到公网（默认仅 127.0.0.1 监听）。
- 不承诺在任何非 XPad2 设备上获得 Root。
