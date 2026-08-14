import { useEffect, useRef, useState } from "react";
import { api, Device } from "./lib/api";

const COMPONENT_META: Record<string, string> = {
  full: "完整套装",
  "suu-full": "SukiSU 完整",
  ksu: "KernelSU",
  suu: "SukiSU",
  zygisk: "Zygisk",
  vector: "LSPosed",
  "ksu-manager": "KSU 管理器",
  "suu-manager": "SukiSU 管理器",
  "xpad-installer": "XPad 安装器",
  "installer-backup": "安装备份",
  boominstaller: "Boom 安装器",
  ota: "OTA",
};

interface TempRoot {
  id: string;
  state: string;
  detail?: string | null;
}

interface Status {
  product_version?: string;
  selinux?: string;
  temporary_root?: TempRoot;
}

export default function App() {
  const [devices, setDevices] = useState<Device[]>([]);
  const [serial, setSerial] = useState<string | null>(null);
  const [components, setComponents] = useState<string[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [running, setRunning] = useState(false);
  const [done, setDone] = useState(false);
  const [lines, setLines] = useState<{ stream: string; line: string }[]>([]);
  const [status, setStatus] = useState<Status | null>(null);
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  const wsRef = useRef<WebSocket | null>(null);
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.getDevices().then((d) => setDevices(d.devices)).catch(() => {});
    api.getComponents().then((c) => setComponents(c.components)).catch(() => {});
    refreshStatus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    document.documentElement.classList.toggle("light", theme === "light");
  }, [theme]);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [lines]);

  function refreshStatus() {
    api.getStatus().then(setStatus).catch(() => setStatus(null));
  }

  function toggleComponent(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function onSelectSerial(v: string | null) {
    setSerial(v);
    api.selectDevice(v).catch(() => {});
  }

  function startInstall() {
    if (running) return;
    setRunning(true);
    setDone(false);
    setLines([]);
    const cmd = selected.size ? "install " + [...selected].join(" ") : "install";
    wsRef.current = api.openRunSocket(
      cmd,
      (stream, line) => setLines((p) => [...p, { stream, line }]),
      () => {
        setRunning(false);
        setDone(true);
        refreshStatus();
      }
    );
  }

  function stopInstall() {
    wsRef.current?.close();
    setRunning(false);
  }

  const rootState = status?.temporary_root?.state ?? "unknown";
  const rooted = ["present", "active", "running"].includes(rootState);

  return (
    <div className="flex h-full flex-col">
      <header className="glass-header">
        <div className="shimmer" />
        <div className="header-icon">⚡</div>
        <span className="header-title">临时root</span>
        <div className="ml-auto flex items-center gap-3">
          <div className="field">
            <span className="field-label">设备</span>
            <select
              value={serial ?? ""}
              onChange={(e) => onSelectSerial(e.target.value || null)}
            >
              <option value="">未选择</option>
              {devices.map((d) => (
                <option key={d.serial} value={d.serial}>
                  {d.serial} · {d.model ?? d.state}
                </option>
              ))}
            </select>
          </div>
          <button
            className="btn btn-outlined"
            style={{ height: 40, padding: "0 14px" }}
            onClick={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
          >
            {theme === "dark" ? "☀️" : "🌙"}
          </button>
        </div>
      </header>

      <main
        className="flex-1 space-y-4 overflow-y-auto p-6"
        style={{ maxWidth: 920, width: "100%", margin: "0 auto" }}
      >
        {/* 状态卡片 */}
        <section className="card">
          <div className="card-title">临时 Root 状态</div>
          <div className="card-subtitle">
            通过 IonStack 内核利用在本次启动周期内取得临时 Root 权限
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className={`pill ${rooted ? "ok" : "off"}`}>
              <span className="pill-dot" />
              {rooted ? "已取得临时 Root" : "未激活 Root"}
            </span>
            {status?.selinux && (
              <span className="pill off">
                <span className="pill-dot" />
                SELinux {status.selinux}
              </span>
            )}
            {status?.product_version && (
              <span className="pill info">
                <span className="pill-dot" />
                {status.product_version}
              </span>
            )}
          </div>
          {status?.temporary_root?.detail && (
            <div className="mt-3 text-sm" style={{ color: "var(--md-on-surface-variant)" }}>
              {status.temporary_root.detail}
            </div>
          )}
        </section>

        {/* 安装组件 */}
        <section className="card">
          <div className="card-title">安装组件</div>
          <div className="card-subtitle">
            可选：勾选要安装的组件；不勾选则直接安装默认完整套装
          </div>
          <div className="flex flex-wrap gap-2">
            {components.map((c) => {
              const sel = selected.has(c);
              return (
                <button
                  key={c}
                  className={`chip ${sel ? "selected" : ""}`}
                  onClick={() => toggleComponent(c)}
                >
                  <span className="chip-dot" />
                  {COMPONENT_META[c] ?? c}
                </button>
              );
            })}
          </div>
        </section>

        {/* 操作 */}
        <div className="flex flex-wrap items-center gap-3">
          <button
            className="btn btn-filled"
            onClick={startInstall}
            disabled={running}
          >
            {running
              ? "安装中…"
              : selected.size
                ? `开始安装 (${selected.size})`
                : "直接安装（默认完整套装）"}
          </button>
          {running && (
            <button className="btn btn-outlined" onClick={stopInstall}>
              停止
            </button>
          )}
          {selected.size > 0 && !running && (
            <span
              className="text-sm"
              style={{ color: "var(--md-on-surface-variant)" }}
            >
              已选：{[...selected].map((c) => COMPONENT_META[c] ?? c).join("、")}
            </span>
          )}
        </div>

        {/* 日志 */}
        <section className="card" style={{ padding: "0.6rem" }}>
          <div className="log" ref={logRef}>
            {lines.length === 0 && !running && (
              <div className="log-line" style={{ color: "var(--md-outline)" }}>
                等待开始……
              </div>
            )}
            {lines.map((l, i) => (
              <div
                key={i}
                className={`log-line ${l.stream === "stderr" ? "err" : ""}`}
              >
                {l.stream === "stderr" ? "[err] " : ""}
                {l.line || "\u00a0"}
              </div>
            ))}
            {running && <div className="log-line">▍</div>}
            {done && <div className="log-line done">—— 完成 ——</div>}
          </div>
        </section>
      </main>
    </div>
  );
}
