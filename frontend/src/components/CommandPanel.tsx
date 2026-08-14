import { useState } from "react";
import { api } from "../lib/api";
import LogConsole from "./LogConsole";
import ConfirmDialog from "./ConfirmDialog";

const COMMANDS = [
  "status",
  "doctor",
  "list",
  "version",
  "root",
  "install",
  "freeze",
  "unfreeze",
  "verify",
  "cleanup",
  "update",
];

export default function CommandPanel() {
  const [cmd, setCmd] = useState("status");
  const [args, setArgs] = useState("");
  const [result, setResult] = useState("");
  const [confirm, setConfirm] = useState<string | null>(null);

  const command = args.trim() ? `${cmd} ${args.trim()}` : cmd;

  function submit() {
    api.exec(command.split(/\s+/)).then((r) => {
      setResult(`[${r.status}] exit=${r.exit_code}\n${r.stdout}${r.stderr}`);
    });
  }

  function maybeSubmit() {
    const dangerous = ["root", "install", "freeze", "unfreeze", "hooks"].includes(cmd);
    if (dangerous) setConfirm(command);
    else submit();
  }

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        <select
          value={cmd}
          onChange={(e) => setCmd(e.target.value)}
          className="rounded-lg bg-neutral-800 px-3 py-2 text-sm ring-1 ring-neutral-700"
        >
          {COMMANDS.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
        <input
          value={args}
          onChange={(e) => setArgs(e.target.value)}
          placeholder="参数（如 --json、ota、ksu）"
          className="flex-1 rounded-lg bg-neutral-800 px-3 py-2 text-sm ring-1 ring-neutral-700"
        />
        <button
          onClick={maybeSubmit}
          className="rounded-lg bg-neutral-200 px-4 py-2 text-sm font-medium text-black"
        >
          执行
        </button>
      </div>
      <pre className="whitespace-pre-wrap rounded-lg bg-black/40 p-3 font-mono text-xs">
        {result || "（无输出）"}
      </pre>
      <LogConsole command={command} />
      <ConfirmDialog
        open={confirm !== null}
        message={`确定执行高危命令？\n\n${confirm}\n\n临时 Root 链可能导致设备重启或 kernel panic。`}
        onCancel={() => setConfirm(null)}
        onConfirm={() => {
          submit();
          setConfirm(null);
        }}
      />
    </div>
  );
}
