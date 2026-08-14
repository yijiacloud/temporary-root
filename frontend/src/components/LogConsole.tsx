import { useRef, useState } from "react";
import { api } from "../lib/api";

export default function LogConsole({ command }: { command: string }) {
  const [lines, setLines] = useState<{ stream: string; line: string }[]>([]);
  const [done, setDone] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  function run() {
    setLines([]);
    setDone(false);
    wsRef.current?.close();
    wsRef.current = api.openRunSocket(
      command,
      (stream, line) => setLines((p) => [...p, { stream, line }]),
      () => setDone(true)
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <button
        onClick={run}
        className="w-fit rounded-lg bg-neutral-800 px-3 py-2 text-sm ring-1 ring-neutral-700"
      >
        运行
      </button>
      <pre className="h-64 overflow-auto rounded-lg bg-black/40 p-3 font-mono text-xs">
        {lines.map((l, i) => (
          <div
            key={i}
            className={l.stream === "stderr" ? "text-rose-300" : "text-neutral-200"}
          >
            {l.stream === "stderr" ? "[err] " : ""}
            {l.line}
          </div>
        ))}
        {done && <div className="text-emerald-400">—— 完成 ——</div>}
      </pre>
    </div>
  );
}
