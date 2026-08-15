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
  product_version?: string | null;
  selinux?: string | null;
  temporary_root?: TempRoot;
}

type Page = "cover" | "scan" | "choose" | "root" | "install";

export default function App() {
  const [page, setPage] = useState<Page>("cover");
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

  // install-apps page state
  const [apkRemote, setApkRemote] = useState<string | null>(null);
  const [apkName, setApkName] = useState<string | null>(null);
  const [apkSize, setApkSize] = useState<number | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState<string>("");
  const [installing, setInstalling] = useState(false);
  const [installDone, setInstallDone] = useState(false);
  const [installLines, setInstallLines] = useState<{ stream: string; line: string }[]>(
    []
  );
  const fileRef = useRef<HTMLInputElement>(null);
  const installWsRef = useRef<WebSocket | null>(null);
  const installLogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    document.documentElement.classList.toggle("light", theme === "light");
  }, [theme]);

  // scan page: poll adb devices live
  useEffect(() => {
    if (page !== "scan") return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;

    async function scan() {
      if (cancelled) return;
      try {
        const d = await api.getDevices();
        if (cancelled) return;
        setDevices(d.devices);
        const online = d.devices.filter((x) => x.state === "device");
        if (online.length > 0) {
          const s = online[0].serial;
          setSerial(s);
          api.selectDevice(s).catch(() => {});
          setPage("choose");
          return;
        }
      } catch {
        /* backend not up yet; keep polling */
      }
      timer = setTimeout(scan, 1200);
    }
    scan();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [page]);

  // root page: load components + status
  useEffect(() => {
    if (page !== "root") return;
    api.getComponents().then((c) => setComponents(c.components)).catch(() => {});
    refreshStatus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page]);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [lines]);

  useEffect(() => {
    if (installLogRef.current)
      installLogRef.current.scrollTop = installLogRef.current.scrollHeight;
  }, [installLines]);

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

  async function onPickFile(file: File | null) {
    if (!file) return;
    setUploading(true);
    setUploadMsg("");
    setApkRemote(null);
    setApkName(file.name);
    setApkSize(file.size);
    setInstallLines([]);
    setInstallDone(false);
    try {
      const r = await api.uploadApk(file);
      if (r.pushed) {
        setApkRemote(r.remote_path);
        setUploadMsg(
          `已推送到设备 ${r.remote_path}（${(r.size / 1024 / 1024).toFixed(2)} MB）`
        );
      } else {
        setUploadMsg(`推送失败：${r.detail || "未知错误"}`);
      }
    } catch (e) {
      setUploadMsg(`上传失败：${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setUploading(false);
    }
  }

  function doInstallApk() {
    if (!apkRemote || installing) return;
    setInstalling(true);
    setInstallDone(false);
    setInstallLines([]);
    installWsRef.current = api.openInstallSocket(
      apkRemote,
      "",
      (stream, line) => setInstallLines((p) => [...p, { stream, line }]),
      () => {
        setInstalling(false);
        setInstallDone(true);
      }
    );
  }

  function stopApkInstall() {
    installWsRef.current?.close();
    setInstalling(false);
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
          <button
            className="btn btn-outlined"
            style={{ height: 40, padding: "0 14px" }}
            onClick={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
          >
            {theme === "dark" ? "☀️" : "🌙"}
          </button>
        </div>
      </header>

      <main className={`page ${page === "root" ? "top" : ""}`} key={page}>
        {page === "cover" && (
          <>
            <div className="cover-icon">⚡</div>
            <h1 className="cover-title">临时root</h1>
            <p className="cover-sub">
              通过 IonStack 内核利用，为 XPad2 / PD2P 学而思学习平板取得临时
              Root 并安装 KernelSU / SukiSU
            </p>
            <p className="cover-author">
              原作者{" "}
              <a
                href="https://github.com/yoyicue/xpad2-cli"
                target="_blank"
                rel="noreferrer"
              >
                @yoyicue · xpad2-cli
              </a>
            </p>
            <button
              className="btn btn-filled"
              style={{ marginTop: "0.5rem", padding: "0 40px" }}
              onClick={() => setPage("scan")}
            >
              开始
            </button>
          </>
        )}

        {page === "scan" && (
          <>
            <div className="spinner lg" />
            <div className="scan-title">正在寻找设备…</div>
            <p className="scan-status">
              正在通过 adb 实时扫描已连接的设备。
              <br />
              请确保设备已通过 USB 或无线调试连接，并在设备端允许本计算机的调试授权。
            </p>
            {devices.length > 0 ? (
              <div className="card" style={{ minWidth: 300, textAlign: "left" }}>
                {devices
                  .filter((d) => d.state === "device")
                  .map((d) => (
                    <div
                      key={d.serial}
                      style={{
                        fontFamily: "ui-monospace, monospace",
                        fontSize: "0.85rem",
                        padding: "4px 0",
                      }}
                    >
                      ✓ {d.serial} · {d.model ?? d.state}
                    </div>
                  ))}
                {devices.every((d) => d.state !== "device") && (
                  <div className="scan-status">
                    检测到设备但未授权，请在设备上点击「允许调试」
                  </div>
                )}
              </div>
            ) : (
              <div className="scan-status">尚未检测到设备，正在扫描…</div>
            )}
          </>
        )}

        {page === "choose" && (
          <>
            <div className="scan-title">选择操作</div>
            <p className="scan-status">
              设备已连接：{" "}
              <span style={{ fontFamily: "ui-monospace, monospace" }}>
                {serial ?? "未选择"}
              </span>
              ，请选择要执行的操作。
            </p>
            <div
              className="w-full"
              style={{
                maxWidth: 560,
                display: "flex",
                flexDirection: "column",
                gap: "1rem",
              }}
            >
              <button
                className="card choose-card"
                onClick={() => setPage("root")}
              >
                <div className="choose-icon">⚡</div>
                <div style={{ textAlign: "left" }}>
                  <div className="card-title" style={{ marginBottom: 4 }}>
                    临时 Root
                  </div>
                  <div className="card-subtitle" style={{ margin: 0 }}>
                    通过 IonStack 取得临时 Root，安装 KernelSU / SukiSU / Zygisk
                  </div>
                </div>
              </button>
              <button
                className="card choose-card"
                onClick={() => setPage("install")}
              >
                <div className="choose-icon">📦</div>
                <div style={{ textAlign: "left" }}>
                  <div className="card-title" style={{ marginBottom: 4 }}>
                    安装 Apps
                  </div>
                  <div className="card-subtitle" style={{ margin: 0 }}>
                    上传 APK，经 xpad-install 静默安装到设备
                  </div>
                </div>
              </button>
            </div>
          </>
        )}

        {page === "install" && (
          <div
            className="w-full"
            style={{
              maxWidth: 920,
              margin: "0 auto",
              display: "flex",
              flexDirection: "column",
              gap: "1rem",
            }}
          >
            {/* device bar */}
            <div
              className="card"
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: "1rem",
                flexWrap: "wrap",
              }}
            >
              <div style={{ textAlign: "left" }}>
                <div className="card-title" style={{ marginBottom: 0 }}>
                  设备
                </div>
                <div
                  style={{
                    fontFamily: "ui-monospace, monospace",
                    fontSize: "0.85rem",
                    color: "var(--md-on-surface-variant)",
                  }}
                >
                  {serial ?? "未选择"}
                </div>
              </div>
              <button
                className="btn btn-outlined"
                style={{ height: 40 }}
                onClick={() => setPage("choose")}
              >
                返回选择
              </button>
            </div>

            {/* upload card */}
            <section className="card">
              <div className="card-title" style={{ textAlign: "left" }}>
                上传 APK
              </div>
              <div className="card-subtitle" style={{ textAlign: "left" }}>
                选择要静默安装到设备的 APK，将自动 push 到 /data/local/tmp
              </div>
              <input
                ref={fileRef}
                type="file"
                accept=".apk,.APK"
                hidden
                onChange={(e) => onPickFile(e.target.files?.[0] ?? null)}
              />
              <div
                className="flex flex-wrap items-center gap-3"
                style={{ justifyContent: "flex-start" }}
              >
                <button
                  className="btn btn-tonal"
                  style={{ height: 40 }}
                  onClick={() => fileRef.current?.click()}
                  disabled={uploading}
                >
                  {uploading ? "上传中…" : "选择 APK"}
                </button>
                {apkName && !uploading && (
                  <span
                    className="text-sm"
                    style={{ color: "var(--md-on-surface-variant)" }}
                  >
                    {apkName}（{((apkSize ?? 0) / 1024 / 1024).toFixed(2)} MB）
                  </span>
                )}
              </div>
              {uploadMsg && (
                <div
                  className="text-sm"
                  style={{
                    textAlign: "left",
                    marginTop: 8,
                    color: "var(--md-on-surface-variant)",
                  }}
                >
                  {uploadMsg}
                </div>
              )}
            </section>

            {/* actions */}
            <div
              className="flex flex-wrap items-center gap-3"
              style={{ justifyContent: "flex-start" }}
            >
              <button
                className="btn btn-filled"
                onClick={doInstallApk}
                disabled={!apkRemote || installing}
              >
                {installing ? "安装中…" : "开始安装"}
              </button>
              {installing && (
                <button className="btn btn-outlined" onClick={stopApkInstall}>
                  停止
                </button>
              )}
            </div>

            {/* log */}
            <section className="card" style={{ padding: "0.6rem" }}>
              <div className="log" ref={installLogRef} style={{ textAlign: "left" }}>
                {installLines.length === 0 && !installing && (
                  <div
                    className="log-line"
                    style={{ color: "var(--md-outline)" }}
                  >
                    等待安装……
                  </div>
                )}
                {installLines.map((l, i) => (
                  <div
                    key={i}
                    className={`log-line ${l.stream === "stderr" ? "err" : ""}`}
                  >
                    {l.stream === "stderr" ? "[err] " : ""}
                    {l.line || "\u00a0"}
                  </div>
                ))}
                {installing && <div className="log-line">▍</div>}
                {installDone && <div className="log-line done">—— 完成 ——</div>}
              </div>
            </section>
          </div>
        )}

        {page === "root" && (
          <div
            className="w-full"
            style={{
              maxWidth: 920,
              margin: "0 auto",
              display: "flex",
              flexDirection: "column",
              gap: "1rem",
            }}
          >
            {/* device bar */}
            <div
              className="card"
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: "1rem",
                flexWrap: "wrap",
              }}
            >
              <div style={{ textAlign: "left" }}>
                <div className="card-title" style={{ marginBottom: 0 }}>
                  设备
                </div>
                <div
                  style={{
                    fontFamily: "ui-monospace, monospace",
                    fontSize: "0.85rem",
                    color: "var(--md-on-surface-variant)",
                  }}
                >
                  {serial ?? "未选择"}
                </div>
              </div>
              <button
                className="btn btn-outlined"
                style={{ height: 40 }}
                onClick={() => setPage("choose")}
              >
                返回选择
              </button>
            </div>

            {/* status card */}
            <section className="card">
              <div className="card-title" style={{ textAlign: "left" }}>
                临时 Root 状态
              </div>
              <div
                className="card-subtitle"
                style={{ textAlign: "left" }}
              >
                通过 IonStack 内核利用在本次启动周期内取得临时 Root 权限
              </div>
              <div
                className="flex flex-wrap items-center gap-2"
                style={{ justifyContent: "flex-start" }}
              >
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
                <div
                  className="mt-3 text-sm"
                  style={{
                    color: "var(--md-on-surface-variant)",
                    textAlign: "left",
                  }}
                >
                  {status.temporary_root.detail}
                </div>
              )}
            </section>

            {/* component selection */}
            <section className="card">
              <div className="card-title" style={{ textAlign: "left" }}>
                安装组件
              </div>
              <div className="card-subtitle" style={{ textAlign: "left" }}>
                可选：勾选要安装的组件；不勾选则直接安装默认完整套装
              </div>
              <div
                className="flex flex-wrap gap-2"
                style={{ justifyContent: "flex-start" }}
              >
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

            {/* actions */}
            <div
              className="flex flex-wrap items-center gap-3"
              style={{ justifyContent: "flex-start" }}
            >
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

            {/* log */}
            <section className="card" style={{ padding: "0.6rem" }}>
              <div className="log" ref={logRef} style={{ textAlign: "left" }}>
                {lines.length === 0 && !running && (
                  <div
                    className="log-line"
                    style={{ color: "var(--md-outline)" }}
                  >
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
          </div>
        )}
      </main>

      <footer>
        <div className="dots">
          <button
            aria-label="封面"
            className={page === "cover" ? "active" : ""}
            onClick={() => !running && !installing && setPage("cover")}
          />
          <button
            aria-label="寻找设备"
            className={page === "scan" ? "active" : ""}
            onClick={() => !running && !installing && setPage("scan")}
          />
          <button
            aria-label="选择操作"
            className={page === "choose" ? "active" : ""}
            onClick={() => !running && !installing && setPage("choose")}
          />
          <button
            aria-label="执行"
            className={page === "root" || page === "install" ? "active" : ""}
            onClick={() => !running && !installing && setPage("choose")}
          />
        </div>
      </footer>

      {done && (
        <div className="dialog-overlay" onClick={() => setDone(false)}>
          <div className="dialog" onClick={(e) => e.stopPropagation()}>
            <div className="dialog-icon">✓</div>
            <div className="dialog-title">安装完成</div>
            <div className="dialog-body">
              组件已成功安装。
            </div>
            <div className="dialog-actions">
              <button
                className="btn btn-filled"
                style={{ height: 40, padding: "0 28px" }}
                onClick={() => setDone(false)}
              >
                知道了
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
