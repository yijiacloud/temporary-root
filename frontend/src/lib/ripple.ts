// Global MD3 ripple effect via pointer event delegation.
// Attaches once; works for any dynamically rendered .btn / .chip elements.

export function initRipple(): void {
  document.addEventListener("pointerdown", (e) => {
    const target = e.target as HTMLElement | null;
    const el = target?.closest?.(".btn, .chip") as HTMLElement | null;
    if (!el) return;

    const r = document.createElement("span");
    r.className = "btn-ripple";
    const rect = el.getBoundingClientRect();
    const size = Math.max(rect.width, rect.height) * 2.5;
    r.style.width = r.style.height = `${size}px`;
    r.style.left = `${e.clientX - rect.left}px`;
    r.style.top = `${e.clientY - rect.top}px`;
    el.appendChild(r);
    requestAnimationFrame(() => r.classList.add("expand"));
    r.addEventListener("animationend", () => r.remove());
  });
}
