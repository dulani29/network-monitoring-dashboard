// "Scan my network": find live devices on a subnet and add them with one click.
import { api } from "./api.js";
import { $, el, fmtMs, fmtTime, toast } from "./ui.js";

export function initScanner({ onDevicesChanged }) {
  const dlg = $("#scanDialog");
  const ui = {
    subnet: $("#scanSubnet"), auth: $("#scanAuth"), start: $("#scanStart"), err: $("#eScan"),
    progress: $("#scanProgress"), bar: $("#scanBar"), status: $("#scanStatus"),
    results: $("#scanResults"), rows: $("#scanRows"), addAll: $("#scanAddAll"),
  };
  let snap = { state: "idle", devices: [] };
  let timer = null;
  let busy = false;                        // an add is in progress

  const running = () => snap.state === "running";

  // ---------------------------------------------------------------- rendering
  function statusText() {
    const n = snap.devices.length, found = `${n} device${n === 1 ? "" : "s"} found`;
    switch (snap.state) {
      case "running": return `Scanning ${snap.subnet}… ${snap.scanned} / ${snap.total} addresses · ${found}`;
      case "done": return `Scan of ${snap.subnet} finished ${fmtTime(snap.finished_at)}: ${found}.`;
      case "cancelled": return `Scan stopped · ${found} before stopping.`;
      case "error": return snap.error || "The scan failed.";
      default: return "";
    }
  }

  function render() {
    const isRunning = running();
    ui.start.textContent = isRunning ? "Stop" : "Start scan";
    ui.start.classList.toggle("danger", isRunning);
    ui.start.classList.toggle("primary", !isRunning);
    ui.start.disabled = !isRunning && !(ui.auth.checked && ui.subnet.value.trim());
    ui.subnet.disabled = ui.auth.disabled = isRunning;

    ui.progress.hidden = !isRunning;
    ui.bar.style.width = snap.total ? `${Math.round((100 * snap.scanned) / snap.total)}%` : "0%";
    ui.status.textContent = statusText();

    ui.results.hidden = snap.devices.length === 0;
    ui.rows.replaceChildren(...snap.devices.map(row));

    const fresh = snap.devices.filter((d) => !d.already_added).length;
    ui.addAll.textContent = fresh ? `Add all new (${fresh})` : "Add all new";
    ui.addAll.disabled = busy || isRunning || fresh === 0;
  }

  function row(d) {
    const tags = [d.is_gateway && "router", d.is_self && "this computer"].filter(Boolean)
      .map((t) => el("span", { class: "tag", text: t }));
    let action;
    if (d.already_added) {
      action = el("span", { class: "muted", text: "✓ Monitored" });
    } else {
      action = el("button", { class: "btn small", text: "Add", onclick: (e) => addOne(d, e.currentTarget) });
      action.disabled = busy;
    }
    return el("tr", {},
      el("td", { class: "mono", text: d.host }),
      el("td", {}, d.hostname || (tags.length ? null : "—"), ...tags),
      el("td", { class: "mono muted", text: d.mac || "—" }),
      el("td", { class: "mono", text: fmtMs(d.latency_ms) }),
      el("td", {}, action));
  }

  // ---------------------------------------------------------------- polling
  async function refresh() {
    snap = await api.scanStatus();
    render();
    if (running()) { clearTimeout(timer); timer = setTimeout(() => refresh().catch(stopPolling), 800); }
    else stopPolling();
    return snap;
  }
  function stopPolling() { clearTimeout(timer); timer = null; }

  // ---------------------------------------------------------------- actions
  async function startOrStop() {
    ui.err.textContent = "";
    try {
      if (running()) { snap = await api.scanCancel(); render(); await refresh(); return; }
      snap = await api.scanStart(ui.subnet.value.trim(), ui.auth.checked);
      render();
      await refresh();
    } catch (e) {
      ui.err.textContent = e.fields?.subnet || e.fields?.authorized || e.message;
      if (/already running/i.test(e.message)) refresh().catch(() => {});
    }
  }

  const payloadFor = (d) => ({ name: d.suggested_name, host: d.host, device_type: d.suggested_type, enabled: true });

  async function addOne(d, btn) {
    btn.disabled = true;
    busy = true;
    try {
      const saved = await api.createDevice(payloadFor(d));
      await api.checkDevice(saved.id).catch(() => {});       // first reading so it shows a status
      toast(`Added ${saved.name}`);
      onDevicesChanged();
    } catch (e) {
      toast(e.message, "error");
    } finally {
      busy = false;
      await refresh().catch(() => {});                        // re-flags rows from the server
    }
  }

  async function addAll() {
    const todo = snap.devices.filter((d) => !d.already_added);
    if (!todo.length) return;
    busy = true; render();
    let added = 0, failed = 0;
    for (const d of todo) {
      try {
        const saved = await api.createDevice(payloadFor(d));
        added++;
        api.checkDevice(saved.id).catch(() => {});
      } catch (_) { failed++; }
    }
    busy = false;
    toast(failed ? `Added ${added}, ${failed} could not be added` : `Added ${added} device${added === 1 ? "" : "s"}`,
          failed ? "error" : "info");
    onDevicesChanged();
    setTimeout(onDevicesChanged, 4000);                       // pick up the first readings
    await refresh().catch(() => {});
  }

  // ---------------------------------------------------------------- dialog wiring
  async function open() {
    ui.err.textContent = "";
    ui.auth.checked = false;                                  // permission is confirmed every time
    dlg.showModal();
    try {
      await refresh();                                        // resume a running scan / show the last result
      if (!ui.subnet.value) {
        ui.subnet.value = snap.subnet || (await api.scanDefault()).subnet || "";
        if (!ui.subnet.value) ui.subnet.placeholder = "e.g. 192.168.1.0/24";
      }
    } catch (e) { toast(e.message, "error"); }
    render();
    ui.subnet.focus();
  }

  $("#scanBtn").addEventListener("click", open);
  $("#scanClose").addEventListener("click", () => dlg.close());
  dlg.addEventListener("close", stopPolling);
  ui.start.addEventListener("click", startOrStop);
  ui.addAll.addEventListener("click", addAll);
  ui.auth.addEventListener("change", render);
  ui.subnet.addEventListener("input", render);
  ui.subnet.addEventListener("keydown", (e) => { if (e.key === "Enter" && !ui.start.disabled) startOrStop(); });
}
