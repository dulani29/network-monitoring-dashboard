// Thin wrapper around the REST API.
async function request(method, url, body) {
  const res = await fetch(url, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(data.error || `Request failed (${res.status})`);
    err.fields = data.fields || {};
    throw err;
  }
  return data;
}

export const api = {
  devices: () => request("GET", "/api/devices"),
  createDevice: (d) => request("POST", "/api/devices", d),
  updateDevice: (id, d) => request("PUT", `/api/devices/${id}`, d),
  deleteDevice: (id) => request("DELETE", `/api/devices/${id}`),
  checkDevice: (id) => request("POST", `/api/devices/${id}/check`),
  checkAll: () => request("POST", "/api/check-all"),
  deviceHistory: (id, limit = 60) => request("GET", `/api/devices/${id}/history?limit=${limit}`),
  history: (status = "", limit = 100) =>
    request("GET", `/api/history?limit=${limit}${status ? `&status=${status}` : ""}`),
  series: (limit = 40) => request("GET", `/api/history/series?limit=${limit}`),
  clearHistory: () => request("DELETE", "/api/history"),
  incidents: (since, deviceId = "", limit = 200) =>
    request("GET", `/api/incidents?since=${encodeURIComponent(since)}&limit=${limit}${deviceId ? `&device_id=${deviceId}` : ""}`),
  scanDefault: () => request("GET", "/api/scan/default"),
  scanStatus: () => request("GET", "/api/scan"),
  scanStart: (subnet, authorized) => request("POST", "/api/scan", { subnet, authorized }),
  scanCancel: () => request("POST", "/api/scan/cancel"),
  summary: () => request("GET", "/api/summary"),
  autoStatus: () => request("GET", "/api/monitor/auto"),
  setAuto: (cfg) => request("POST", "/api/monitor/auto", cfg),
};
