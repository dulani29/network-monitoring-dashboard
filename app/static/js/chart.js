// Dependency-free area charts (gradient fill) on <canvas>.
// Optional "mirror" mode: a second series is drawn inverted below the zero line
// (same look as an IN/OUT throughput chart: latency up, packet loss down).
const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

function rgba(hex, a) {
  const h = hex.replace("#", "");
  const n = parseInt(h.length === 3 ? h.split("").map((c) => c + c).join("") : h, 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}

/** Darker shade of a hex colour (for the "OUT" / lower series). */
export function shade(hex, f = 0.6) {
  const n = parseInt(hex.replace("#", ""), 16);
  const c = (v) => Math.round(v * f).toString(16).padStart(2, "0");
  return `#${c((n >> 16) & 255)}${c((n >> 8) & 255)}${c(n & 255)}`;
}

/**
 * @param canvas target <canvas>
 * @param values upper series, number|null (null = failed check)
 * @param opts   { color, axes, labels:[iso], min, max, height,
 *                 down: { values, color, max } }   // optional mirrored series
 */
export function areaChart(canvas, values, opts = {}) {
  const { color = "#73bf69", axes = true, labels = [], min = 0, down = null } = opts;
  const dpr = window.devicePixelRatio || 1;
  const W = canvas.clientWidth || 300;
  // Remember the *logical* height once. Setting canvas.height below rewrites the
  // "height" attribute (x devicePixelRatio), so reading it again would double it each redraw.
  if (!canvas.dataset.h) canvas.dataset.h = String(opts.height || Number(canvas.getAttribute("height")) || 200);
  const H = Number(canvas.dataset.h);
  canvas.width = W * dpr; canvas.height = H * dpr; canvas.style.height = H + "px";
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, W, H);
  ctx.font = "11px Roboto, system-ui, sans-serif";

  const pad = axes ? { l: 46, r: 10, t: 8, b: 24 } : { l: 0, r: 0, t: 6, b: 4 };
  const w = W - pad.l - pad.r, h = H - pad.t - pad.b;
  const n = values.length;
  if (!n) { ctx.fillStyle = css("--muted"); ctx.fillText("No data", pad.l + 6, H / 2); return; }

  const upFrac = down ? 0.66 : 1;
  const zeroY = pad.t + h * upFrac, upH = h * upFrac, dnH = h - upH;
  const nums = values.filter((v) => v != null);
  const max = opts.max ?? Math.max(1, ...nums) * 1.2;
  const dmax = down ? (down.max ?? Math.max(1, ...down.values.filter((v) => v != null)) * 1.2) : 1;
  const x = (i) => pad.l + (n === 1 ? w / 2 : (i / (n - 1)) * w);
  const yUp = (v) => zeroY - ((v - min) / (max - min)) * upH;
  const yDn = (v) => zeroY + (v / dmax) * dnH;

  // ---- grid + axes
  const grid = rgba(css("--muted"), 0.25), muted = css("--muted");
  if (axes) {
    ctx.lineWidth = 1; ctx.fillStyle = muted; ctx.textAlign = "right";
    const line = (yy) => { ctx.strokeStyle = grid; ctx.beginPath(); ctx.moveTo(pad.l, Math.round(yy) + .5); ctx.lineTo(pad.l + w, Math.round(yy) + .5); ctx.stroke(); };
    const upSteps = down ? 3 : 5;
    for (let i = 0; i <= upSteps; i++) {
      const v = min + ((max - min) / upSteps) * i;
      line(yUp(v)); ctx.fillText(v.toFixed(max < 5 ? 1 : 0), pad.l - 6, yUp(v) + 4);
    }
    if (down) for (let i = 1; i <= 2; i++) {
      const v = (dmax / 2) * i;
      line(yDn(v)); ctx.fillText("-" + v.toFixed(0), pad.l - 6, yDn(v) + 4);
    }
    const ticks = Math.min(n, 6);
    ctx.textAlign = "center";
    for (let t = 0; t < ticks; t++) {
      const i = Math.round((t / Math.max(1, ticks - 1)) * (n - 1)), xx = x(i);
      ctx.strokeStyle = rgba(css("--muted"), 0.12);
      ctx.beginPath(); ctx.moveTo(Math.round(xx) + .5, pad.t); ctx.lineTo(Math.round(xx) + .5, pad.t + h); ctx.stroke();
      if (labels[i]) ctx.fillText(new Date(labels[i]).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        Math.min(Math.max(xx, pad.l + 14), W - 16), H - 7);
    }
  }

  // ---- one series (smooth line + gradient area, broken at null gaps)
  function drawSeries(vals, yFn, col, fromY, toY) {
    const segs = []; let cur = [];
    vals.forEach((v, i) => { if (v == null) { if (cur.length) segs.push(cur); cur = []; } else cur.push([x(i), yFn(v)]); });
    if (cur.length) segs.push(cur);
    const g = ctx.createLinearGradient(0, fromY, 0, toY);
    g.addColorStop(0, rgba(col, 0.05)); g.addColorStop(1, rgba(col, 0.55));
    segs.forEach((pts) => {
      const trace = () => {
        ctx.moveTo(pts[0][0], pts[0][1]);
        if (pts.length === 1) { ctx.lineTo(pts[0][0] + 0.01, pts[0][1]); return; }
        for (let i = 1; i < pts.length - 1; i++)
          ctx.quadraticCurveTo(pts[i][0], pts[i][1], (pts[i][0] + pts[i + 1][0]) / 2, (pts[i][1] + pts[i + 1][1]) / 2);
        ctx.lineTo(pts[pts.length - 1][0], pts[pts.length - 1][1]);
      };
      ctx.beginPath(); trace(); ctx.lineTo(pts[pts.length - 1][0], zeroY); ctx.lineTo(pts[0][0], zeroY); ctx.closePath();
      ctx.fillStyle = g; ctx.fill();
      ctx.beginPath(); trace(); ctx.strokeStyle = col; ctx.lineWidth = axes ? 1.5 : 1.3; ctx.stroke();
      if (pts.length === 1) { ctx.beginPath(); ctx.fillStyle = col; ctx.arc(pts[0][0], pts[0][1], 3, 0, 7); ctx.fill(); }
    });
  }
  // upper: gradient strongest at the line (top) ; lower: strongest at the line (bottom)
  drawSeries(values, yUp, color, zeroY, pad.t);
  if (down) drawSeries(down.values, yDn, down.color || shade(color), zeroY, pad.t + h);

  // zero line
  if (down) { ctx.strokeStyle = rgba(css("--muted"), 0.6); ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(pad.l, Math.round(zeroY) + .5); ctx.lineTo(pad.l + w, Math.round(zeroY) + .5); ctx.stroke(); }

  // failed checks -> red dots on the zero line
  ctx.fillStyle = css("--offline");
  values.forEach((v, i) => { if (v == null) { ctx.beginPath(); ctx.arc(x(i), zeroY - 3, axes ? 3.5 : 2.5, 0, 7); ctx.fill(); } });
}
