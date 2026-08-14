export interface ComponentStatus {
  id: string;
  state: string;
  detail?: string | null;
}

export interface Device {
  serial: string;
  state: string;
  [k: string]: string;
}

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json() as Promise<T>;
}

export const api = {
  getStatus: () =>
    json<{
      components: ComponentStatus[];
      selinux: string;
      boot_id: string;
      temporary_root: ComponentStatus;
    }>("/api/status"),
  getDevices: () => json<{ devices: Device[] }>("/api/devices"),
  selectDevice: (serial: string | null) =>
    json<{ ok: boolean }>("/api/devices/select", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ serial }),
    }),
  getComponents: () =>
    json<{ commands: any[]; components: string[] }>("/api/components"),
  exec: (command: string[]) =>
    json<{ stdout: string; stderr: string; exit_code: number; status: string }>(
      "/api/exec",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command }),
      }
    ),
  openRunSocket: (
    command: string,
    onLine: (stream: string, line: string) => void,
    onDone: () => void
  ) => {
    const protocol = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(
      `${protocol}://${location.host}/ws/run?command=${encodeURIComponent(command)}`
    );
    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.type === "line") onLine(msg.stream, msg.line);
      else if (msg.type === "done") {
        onDone();
        ws.close();
      }
    };
    return ws;
  },
};
