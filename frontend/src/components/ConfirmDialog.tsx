export default function ConfirmDialog({
  open,
  message,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  message: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 grid place-items-center bg-black/60">
      <div className="w-96 rounded-xl bg-neutral-900 p-6 ring-1 ring-neutral-700">
        <pre className="mb-4 whitespace-pre-wrap text-sm text-neutral-200">
          {message}
        </pre>
        <div className="flex justify-end gap-2">
          <button
            onClick={onCancel}
            className="rounded-lg px-3 py-2 text-sm ring-1 ring-neutral-700"
          >
            取消
          </button>
          <button
            onClick={onConfirm}
            className="rounded-lg bg-rose-600 px-3 py-2 text-sm"
          >
            确认
          </button>
        </div>
      </div>
    </div>
  );
}
