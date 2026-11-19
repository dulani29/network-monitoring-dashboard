import { api } from "./api.js";
import { areaChart, shade } from "./chart.js";
import { initScanner } from "./scan.js";
import { $, el, badge, fmtDuration, fmtMs, fmtPct, fmtTime, legend, toast } from "./ui.js";

const PALETTE = ["#f2495c", "#b877d9", "#5794f2", "#73bf69", "#ff9830", "#19b6c9"];
const GREEN = "#73bf69", YELLOW = "#f2cc0c", RED = "#f2495c", ORANGE = "#ff9830";

const state = { devices: [], series: {}, editingId: null, pollTimer: null };

// ---------------------------------------------------------------- theme
const root = document.documentElement;
root.dataset.theme = localStorage.getItem("theme") || "dark";
$("#themeBtn").addEventListener("click", () => {
  root.dataset.theme = root.dataset.theme === "dark" ? "light" : "dark";
  try { localStorage.setItem("theme", root.dataset.theme); } catch (_) {}
  renderAll();
});

// ---------------------------------------------------------------- data helpers
const avg = (a) => { const v = a.filter((x) => x != null); return v.length ? v.reduce((s, x) => s + x, 0) / v.length : null; };

// Combine every device's readings into one series, aligned from the newest reading backwards.
function aggregate() {
  const lists = Object.values(state.series);
  const n = Math.max(0, ...lists.map((l) => l.length));
  const out = { ping: [], loss: [], up: [], labels: [] };
  for (let k = n - 1; k >= 0; k--) {                       // k = readings back from newest -> oldest first
    const pts = lists.map((l) => l[l.length - 1 - k]).filter(Boolean);
    out.ping.push(avg(pts.map((p) => p.latency_ms)));
    out.loss.push(avg(pts.map((p) => p.packet_loss)));
    out.up.push(pts.filter((p) => p.status !== "offline").length);
    out.labels.push(pts.length ? pts[pts.length - 1].checked_at : null);
  }
  return out;
}

// ---------------------------------------------------------------- render: top rows
function renderStats() {
  const c = { online: 0, degraded: 0, offline: 0, unknown: 0 };
  state.devices.forEach((d) => c[d.status]++);
  const known = c.online + c.degraded + c.offline;
  const pings = state.devices.map((d) => d.latency_ms);
  $("#sOnline").textContent = c.online;
  $("#sDegraded").textContent = c.degraded;
  $("#sOffline").textContent = c.offline;
  $("#sTotal").textContent = state.devices.length;
  const p = avg(pings);
  $("#sPing").textContent = p == null ? "N/A" : `${p.toFixed(p < 10 ? 1 : 0)}`;
  const health = known ? Math.round((100 * (c.online + c.degraded)) / known) : null;
  $("#sHealth").textContent = health == null ? "N/A" : `${health}%`;
  $("#sHealth").className = health == null || health >= 90 ? "c-online" : health >= 60 ? "c-degraded" : "c-offline";
  $("#sOffline").parentElement.querySelector(".ico").style.borderColor = c.offline ? RED : "";
}

function renderSparks(agg) {
  const last = (a) => [...a].reverse().find((v) => v != null);
  const ping = last(agg.ping), loss = last(agg.loss), up = agg.up.length ? agg.up[agg.up.length - 1] : null;
  $("#spPingV").textContent = ping == null ? "—" : `${ping.toFixed(1)} ms`;
  $("#spLossV").textContent = loss == null ? "—" : `${loss.toFixed(1)} %`;
  $("#spUpV").textContent = up == null ? "—" : `${up} / ${state.devices.length}`;
  areaChart($("#spPing"), agg.ping, { color: GREEN, axes: false, height: 70 });
  areaChart($("#spLoss"), agg.loss, { color: ORANGE, axes: false, height: 70, max: 100 });
  areaChart($("#spUp"), agg.up, { color: "#b877d9", axes: false, height: 70, min: 0, max: Math.max(1, state.devices.length) });
}

function renderGateway(agg) {
  const gw = state.devices.find((d) => d.device_type === "router") || state.devices[0];
  const info = $("#gwInfo");
  if (!gw) { info.replaceChildren(el("span", { class: "empty", text: "Add a router/gateway device to see it here." })); return; }
  info.replaceChildren(
    el("div", { class: "info" }, el("i", { text: "i" }), el("span", { text: `${gw.name}: ${gw.host}` })),
    el("div", { class: "info" }, el("i", { text: "⚠" }), badge(gw.status), el("span", { text: gw.error ? gw.error : "" })),
    el("div", { class: "info" }, el("i", { text: "◔" }), el("span", { text: `Uptime 24h: ${fmtPct(gw.uptime_pct)}` })),
    el("div", { class: "info" }, el("i", { text: "⏱" }), el("span", { text: `Last check: ${fmtTime(gw.last_checked)}` })),
  );
  const pts = state.series[gw.id] || [];
  const labels = pts.map((p) => p.checked_at);
  const GW = "#73bf69";
  areaChart($("#gwChart"), pts.map((p) => p.latency_ms), { color: GW, labels,
    down: { values: pts.map((p) => p.packet_loss), color: shade(GW, 0.55), max: 100 } });
  legend($("#gwLegend"), [
    { label: "Latency", value: gw.latency_ms == null ? "—" : gw.latency_ms.toFixed(1) + " ms", color: GW },
    { label: "Loss", value: gw.packet_loss == null ? "—" : gw.packet_loss + " %", color: shade(GW, 0.55) }]);

  const AV = "#f5a623";
  areaChart($("#avgChart"), agg.ping, { color: AV, labels: agg.labels,
    down: { values: agg.loss, color: shade(AV, 0.55), max: 100 } });
  const a = avg(agg.ping), l = avg(agg.loss);
  legend($("#avgLegend"), [
    { label: "Avg latency", value: a == null ? "—" : a.toFixed(1) + " ms", color: AV },
    { label: "Avg loss", value: l == null ? "—" : l.toFixed(1) + " %", color: shade(AV, 0.55) }]);

  const UP = "#b877d9", total = Math.max(1, state.devices.length);
  areaChart($("#lossChart"), agg.up, { color: UP, labels: agg.labels, min: 0, max: total });
  legend($("#lossLegend"), [{ label: "Devices up", value: agg.up.length ? `${agg.up[agg.up.length - 1]} / ${state.devices.length}` : "—", color: UP }]);
}

// ---------------------------------------------------------------- render: device panels
function visibleDevices() {
  const q = $("#searchInput").value.trim().toLowerCase();
  const f = $("#statusFilter").value;
  return state.devices.filter((d) =>
    (!f || d.status === f) && (!q || d.name.toLowerCase().includes(q) || d.host.toLowerCase().includes(q)));
}

function devicePanel(d, index) {
  const color = PALETTE[index % PALETTE.length];
  const canvas = el("canvas", { height: "170", "data-h": "170" });
  const leg = el("div", { class: "legend" });
  const panel = el("section", { class: "panel device", "data-id": d.id },
    el("h3", { class: "ptitle" }, el("span", { text: d.name + (d.enabled ? "" : " (paused)") })),
    el("div", { class: "actions" },
      el("button", { class: "icon-btn", title: "Ping now", text: "⚡", onclick: (e) => checkOne(d, e.currentTarget) }),
      el("button", { class: "icon-btn", title: "Edit", text: "✎", onclick: () => openDialog(d) }),
      el("button", { class: "icon-btn", title: "Delete", text: "🗑", onclick: () => removeDevice(d) })),
    el("div", { class: "info-row" },
      el("div", { class: "info" }, el("i", { text: "i" }), el("span", { class: "mono", text: `${d.host} · ${d.device_type}` })),
      el("div", { class: "info" }, el("i", { text: "◔" }), el("span", { text: `Uptime 24h: ${fmtPct(d.uptime_pct)}` }))),
    el("div", { class: "status-line" }, badge(d.status), el("span", { class: "muted", text: fmtTime(d.last_checked) })),
    el("h3", { class: "ptitle sub" }, el("span", { text: "Ping Latency / Loss" })),
    canvas, leg);
  panel._draw = () => {
    const pts = state.series[d.id] || [];
    areaChart(canvas, pts.map((p) => p.latency_ms), { color, labels: pts.map((p) => p.checked_at),
      down: { values: pts.map((p) => p.packet_loss), color: shade(color, 0.55), max: 100 } });
    legend(leg, [
      { label: "Latency", value: d.latency_ms == null ? "—" : d.latency_ms.toFixed(1) + " ms", color },
      { label: "Loss", value: d.packet_loss == null ? "—" : d.packet_loss + " %", color: shade(color, 0.55) },
    ]);
  };
  return panel;
}

function renderDevices() {
  const list = visibleDevices();
  const grid = $("#deviceGrid");
  const panels = list.map((d) => devicePanel(d, state.devices.indexOf(d)));
  grid.replaceChildren(...panels);
  panels.forEach((p) => p._draw());      // draw after they are attached (so widths are known)
  $("#deviceEmpty").hidden = list.length > 0;
}

function renderAll() {
  const agg = aggregate();
  renderStats(); renderSparks(agg); renderGateway(agg); renderDevices();
}
$("#searchInput").addEventListener("input", renderDevices);
$("#statusFilter").addEventListener("change", renderDevices);
let rz; window.addEventListener("resize", () => { clearTimeout(rz); rz = setTimeout(renderAll, 150); });

// ---------------------------------------------------------------- load / actions
async function load() {
  [state.devices, state.series] = await Promise.all([api.devices(), api.series(40)]);
  renderAll();
  loadIncidents().catch(() => {});      // keeps the tab badge + open incident tab current
}

async function refreshAll(runChecks = true) {
  const btn = $("#refreshBtn");
  if (runChecks) {
    btn.disabled = true; btn.textContent = "Checking…";
    document.querySelectorAll(".device .badge").forEach((b) => b.classList.add("checking"));
  }
  try {
    if (runChecks) await api.checkAll();
    await load();
    if (!$("#tab-history").hidden) loadHistory();
  } catch (e) { toast(e.message, "error"); }
  finally { btn.disabled = false; btn.textContent = "↻ Refresh"; }
}
$("#refreshBtn").addEventListener("click", () => refreshAll(true));

async function checkOne(d, btn) {
  btn.disabled = true;
  try { await api.checkDevice(d.id); await load(); }
  catch (e) { toast(e.message, "error"); }
  finally { btn.disabled = false; }
}

async function removeDevice(d) {
  if (!confirm(`Delete "${d.name}" and its history?`)) return;
  try { await api.deleteDevice(d.id); toast("Device deleted"); load(); }
  catch (e) { toast(e.message, "error"); }
}

// ---------------------------------------------------------------- incidents tab
// "Today" = since local midnight in the *browser's* time zone.
const startOfToday = () => { const d = new Date(); d.setHours(0, 0, 0, 0); return d.toISOString(); };
const when = (iso) => new Date(iso).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit" });

function renderIncidents(data) {
  const { summary, devices, incidents } = data;

  // tab badge: number of devices that are down right now
  const badgeEl = $("#incidentCount");
  badgeEl.hidden = !summary.ongoing;
  badgeEl.textContent = summary.ongoing;

  if ($("#tab-incidents").hidden) return;

  const down = $("#iDowntime");
  down.textContent = fmtDuration(summary.downtime_today_seconds);
  down.className = summary.downtime_today_seconds ? "c-offline" : "c-online";

  const longest = summary.longest_outage, lo = $("#iLongest");
  lo.textContent = longest ? fmtDuration(longest.seconds) : "None";
  lo.className = longest ? "c-degraded" : "c-online";
  $("#iLongestSub").textContent = longest
    ? `${longest.device_name}${longest.ongoing ? " · still down" : ""}` : "";

  const cnt = $("#iCount");
  cnt.textContent = summary.incidents_total;
  cnt.className = summary.ongoing ? "c-offline" : summary.incidents_total ? "c-degraded" : "c-online";
  $("#iCountSub").textContent = summary.ongoing ? `${summary.ongoing} ongoing now` : "";

  $("#incidentDevices").replaceChildren(...devices.map((d) => el("tr", {},
    el("td", {}, d.device_name, d.ongoing ? el("span", { class: "badge offline", text: "Down", style: "margin-left:8px" }) : null),
    el("td", { class: d.downtime_today_seconds ? "c-offline" : "muted", text: d.downtime_today_seconds ? fmtDuration(d.downtime_today_seconds) : "0s" }),
    el("td", { class: "mono", text: d.longest_outage_seconds ? fmtDuration(d.longest_outage_seconds) : "—" }),
    el("td", { text: d.incidents }))));
  $("#incidentDevicesEmpty").hidden = devices.length > 0;

  // keep the device filter in sync with the device list (without losing the selection)
  const sel = $("#incidentDevice"), keep = sel.value;
  sel.replaceChildren(new Option("All devices", ""), ...devices
    .slice().sort((a, b) => a.device_name.localeCompare(b.device_name))
    .map((d) => new Option(d.device_name, d.device_id)));
  sel.value = keep;

  $("#incidentRows").replaceChildren(...incidents.map((i) => el("tr", {},
    el("td", { text: i.device_name }),
    el("td", { class: "mono", text: i.device_host }),
    el("td", { text: when(i.started_at) }),
    el("td", {}, i.ongoing ? el("span", { class: "badge offline", text: "Still down" }) : el("span", { text: when(i.ended_at) })),
    el("td", { class: "mono", text: fmtDuration(i.duration_seconds) + (i.ongoing ? " so far" : "") }),
    el("td", { class: "muted", text: i.error || "No reply" }))));
  $("#incidentEmpty").hidden = incidents.length > 0;
  $("#incidentHint").textContent = "Durations are accurate to the check interval.";
}

async function loadIncidents() {
  renderIncidents(await api.incidents(startOfToday(), $("#incidentDevice").value));
}
$("#incidentDevice").addEventListener("change", () => loadIncidents().catch((e) => toast(e.message, "error")));

// ---------------------------------------------------------------- history tab
async function loadHistory() {
  const rows = await api.history($("#historyStatus").value, 100);
  $("#historyRows").replaceChildren(...rows.map((r) => el("tr", {},
    el("td", { text: new Date(r.checked_at).toLocaleString() }),
    el("td", { text: r.device_name }),
    el("td", { class: "mono", text: r.device_host }),
    el("td", {}, badge(r.status)),
    el("td", { class: "mono", text: fmtMs(r.latency_ms) }),
    el("td", { text: fmtPct(r.packet_loss) }))));
  $("#historyEmpty").hidden = rows.length > 0;
}
$("#historyStatus").addEventListener("change", loadHistory);
$("#clearHistoryBtn").addEventListener("click", async () => {
  if (!confirm("Delete ALL monitoring history?")) return;
  await api.clearHistory(); toast("History cleared"); load(); loadHistory();
});
document.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => {
  document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("active", x === t));
  ["dashboard", "incidents", "history"].forEach((name) => { $(`#tab-${name}`).hidden = t.dataset.tab !== name; });
  if (t.dataset.tab === "history") loadHistory();
  else if (t.dataset.tab === "incidents") loadIncidents().catch((e) => toast(e.message, "error"));
  else renderAll();
}));

// ---------------------------------------------------------------- add / edit dialog
const dlg = $("#deviceDialog");
function openDialog(device = null) {
  state.editingId = device ? device.id : null;
  $("#dialogTitle").textContent = device ? "Edit device" : "Add device";
  $("#fName").value = device?.name || "";
  $("#fHost").value = device?.host || "";
  $("#fType").value = device?.device_type || "other";
  $("#fEnabled").checked = device ? device.enabled : true;
  $("#eName").textContent = $("#eHost").textContent = "";
  dlg.showModal(); $("#fName").focus();
}
$("#addBtn").addEventListener("click", () => openDialog());
$("#dialogCancel").addEventListener("click", () => dlg.close());
$("#deviceForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const payload = { name: $("#fName").value, host: $("#fHost").value,
                    device_type: $("#fType").value, enabled: $("#fEnabled").checked };
  const editing = state.editingId;
  try {
    const saved = editing ? await api.updateDevice(editing, payload) : await api.createDevice(payload);
    dlg.close(); toast(editing ? "Device updated" : "Device added");
    if (!editing) await api.checkDevice(saved.id);
    load();
  } catch (err) {
    $("#eName").textContent = err.fields?.name || "";
    $("#eHost").textContent = err.fields?.host || (err.fields?.name ? "" : err.message);
  }
});

// ---------------------------------------------------------------- network scanner
initScanner({ onDevicesChanged: () => load().catch(() => {}) });

// ---------------------------------------------------------------- auto monitoring
async function initAuto() {
  const s = await api.autoStatus();
  $("#autoToggle").checked = s.enabled;
  if (![...$("#intervalSelect").options].some((o) => o.value === String(s.interval)))
    $("#intervalSelect").append(new Option(`${s.interval} s`, s.interval));
  $("#intervalSelect").value = String(s.interval);
  schedulePoll(s.enabled, s.interval);
}
function schedulePoll(enabled, interval) {
  clearInterval(state.pollTimer);   // the server pings; the browser only re-reads results
  state.pollTimer = setInterval(() => load().catch(() => {}), enabled ? Math.max(5, interval) * 1000 : 15000);
}
async function pushAuto() {
  const enabled = $("#autoToggle").checked, interval = Number($("#intervalSelect").value);
  try { await api.setAuto({ enabled, interval }); schedulePoll(enabled, interval);
        toast(enabled ? `Auto-check every ${interval}s` : "Auto-check off"); }
  catch (e) { toast(e.message, "error"); }
}
$("#autoToggle").addEventListener("change", pushAuto);
$("#intervalSelect").addEventListener("change", pushAuto);

// ---------------------------------------------------------------- boot
(async function init() {
  await initAuto();
  await load();
  if (state.devices.length && state.devices.every((d) => d.status === "unknown")) refreshAll(true);
})();
