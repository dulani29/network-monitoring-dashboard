// Rendering helpers (all user data goes through textContent -> XSS safe).
export const $ = (sel, root = document) => root.querySelector(sel);

export function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  Object.entries(props).forEach(([k, v]) => {
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  });
  children.flat().forEach((c) => c != null && node.append(c));
  return node;
}

export const LABELS = { online: "Online", degraded: "Degraded", offline: "Offline", unknown: "Not checked" };

export function badge(status, extra = "") {
  return el("span", { class: `badge ${status} ${extra}`, text: LABELS[status] || status });
}

export const fmtMs = (v) => (v == null ? "—" : `${Number(v).toFixed(v < 10 ? 1 : 0)} ms`);
export const fmtPct = (v) => (v == null ? "—" : `${Number(v).toFixed(v % 1 ? 1 : 0)}%`);

export function fmtTime(iso) {
  if (!iso) return "never";
  const d = new Date(iso), s = Math.round((Date.now() - d) / 1000);
  if (s < 5) return "just now";
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  return d.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

// 75 -> "1m 15s", 3900 -> "1h 05m", 200000 -> "2d 7h"; 0 -> "0s"
export function fmtDuration(seconds) {
  if (seconds == null) return "—";
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${String(s % 60).padStart(2, "0")}s`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ${String(m % 60).padStart(2, "0")}m`;
  return `${Math.floor(h / 24)}d ${h % 24}h`;
}

// legend row: [{label, value, color}]
export function legend(container, items) {
  container.replaceChildren(...items.map((i) => {
    const s = el("span", { text: `${i.label}: ${i.value}` });
    s.style.setProperty("--c", i.color);
    return s;
  }));
}

export function toast(message, type = "info") {
  const t = el("div", { class: `toast ${type}`, text: message });
  $("#toasts").append(t);
  setTimeout(() => t.remove(), 3500);
}
