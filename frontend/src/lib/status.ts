export function statusMeta(state: string): { label: string; color: string } {
  switch (state) {
    case "active":
      return { label: "active", color: "bg-emerald-500/20 text-emerald-300 ring-emerald-500/40" };
    case "installed":
      return { label: "installed", color: "bg-sky-500/20 text-sky-300 ring-sky-500/40" };
    case "ready":
      return { label: "ready", color: "bg-cyan-500/20 text-cyan-300 ring-cyan-500/40" };
    case "absent":
      return { label: "absent", color: "bg-neutral-700/40 text-neutral-400 ring-neutral-600/40" };
    case "outdated":
    case "incompatible":
      return { label: state, color: "bg-amber-500/20 text-amber-300 ring-amber-500/40" };
    case "broken":
    case "needs-reboot":
      return { label: state, color: "bg-rose-500/20 text-rose-300 ring-rose-500/40" };
    default:
      return { label: state, color: "bg-neutral-700/40 text-neutral-400" };
  }
}
