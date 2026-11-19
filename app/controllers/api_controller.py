"""JSON REST API. Controllers only translate HTTP <-> services/repositories."""
import csv
import io
import sqlite3

from flask import Blueprint, Response, current_app, jsonify, request

from ..services.traceroute_service import run_traceroute as traceroute_run
from ..services.scanner_service import ScanBusyError
from ..services.validators import ValidationError, validate_device_payload, validate_scan_payload
from ..services.incident_service import parse_iso
from ..services.validators import ValidationError, validate_device_payload, validate_scan_payload

api_bp = Blueprint("api", __name__)


def _ctx():
    return current_app.extensions["netmon"]


def _error(message, status=400, **extra):
    return jsonify({"error": message, **extra}), status


@api_bp.errorhandler(ValidationError)
def _handle_validation(exc: ValidationError):
    return _error("Validation failed", 422, fields=exc.errors)


@api_bp.get("/devices/<int:device_id>/traceroute")
def traceroute_device(device_id):
    device = _ctx()["devices"].get(device_id)
    if not device:
        return _error("Device not found", 404)
    try:
        hops = _ctx()["traceroute"].run_traceroute(device.host)
    except Exception as exc:
        return _error(str(exc), 500)
    # Serialize hop results
    data = [{"hop": h.hop, "host": h.host, "latency_ms": h.latency_ms, "raw": h.raw} for h in hops]
    return jsonify(data)

@api_bp.get("/health")
def health():
    return jsonify({"status": "ok"})


# ---------------------------------------------------------------- devices
@api_bp.get("/devices")
def list_devices():
    return jsonify(_ctx()["monitor"].devices_with_status())


@api_bp.post("/devices")
def create_device():
    data = validate_device_payload(request.get_json(silent=True) or {})
    try:
        device = _ctx()["devices"].create(**data)
    except sqlite3.IntegrityError:
        return _error("A device with this IP/hostname already exists.", 409)
    return jsonify(device.to_dict()), 201


@api_bp.put("/devices/<int:device_id>")
def update_device(device_id):
    repo = _ctx()["devices"]
    if not repo.get(device_id):
        return _error("Device not found", 404)
    data = validate_device_payload(request.get_json(silent=True) or {})
    try:
        device = repo.update(device_id, **data)
    except sqlite3.IntegrityError:
        return _error("A device with this IP/hostname already exists.", 409)
    if not device.enabled:                       # paused devices are no longer checked,
        _ctx()["incidents"].close_for_device(device_id)   # so they can't recover by themselves
    return jsonify(device.to_dict())


@api_bp.delete("/devices/<int:device_id>")
def delete_device(device_id):
    if not _ctx()["devices"].delete(device_id):
        return _error("Device not found", 404)
    return "", 204


# ---------------------------------------------------------------- checks
@api_bp.post("/devices/<int:device_id>/check")
def check_device(device_id):
    device = _ctx()["devices"].get(device_id)
    if not device:
        return _error("Device not found", 404)
    return jsonify(_ctx()["monitor"].check_device(device).to_dict())


@api_bp.post("/check-all")
def check_all():
    results = _ctx()["monitor"].check_all()
    return jsonify({"checked": len(results), "results": [r.to_dict() for r in results]})


# ---------------------------------------------------------------- history
@api_bp.get("/devices/<int:device_id>/history")
def device_history(device_id):
    limit = min(max(request.args.get("limit", 60, type=int), 1), 500)
    rows = _ctx()["history"].for_device(device_id, limit)
    return jsonify([r.to_dict() for r in reversed(rows)])   # oldest -> newest (for charts)


@api_bp.get("/history")
def history():
    limit = min(max(request.args.get("limit", 100, type=int), 1), 1000)
    status = request.args.get("status") or None
    device_id = request.args.get("device_id", type=int)
    return jsonify(_ctx()["history"].recent(limit, device_id, status))


@api_bp.get("/history/series")
def history_series():
    limit = min(max(request.args.get("limit", 40, type=int), 2), 200)
    return jsonify(_ctx()["history"].series(limit))


@api_bp.delete("/history")
def clear_history():
    removed = _ctx()["history"].clear(request.args.get("device_id", type=int))
    return jsonify({"removed": removed})


@api_bp.get("/export/history.csv")
def export_history():
    rows = _ctx()["history"].recent(limit=5000)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["checked_at", "device", "host", "status", "latency_ms",
                     "min_ms", "max_ms", "packet_loss_pct", "error"])
    for r in rows:
        writer.writerow([r["checked_at"], r["device_name"], r["device_host"], r["status"],
                         r["latency_ms"], r["min_ms"], r["max_ms"], r["packet_loss"], r["error"] or ""])
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=monitoring_history.csv"})


# ---------------------------------------------------------------- incidents
@api_bp.get("/incidents")
def incidents():
    """Outage log + 'downtime today' / 'longest outage'.

    ?since=<ISO time>  start of "today" (the browser sends its local midnight)
    ?device_id=<id>    only list this device's outages
    ?limit=<n>         max rows in the log (default 200)
    """
    since = None
    raw = request.args.get("since")
    if raw:
        try:
            since = parse_iso(raw)
        except ValueError:
            return _error("since must be an ISO-8601 timestamp", 422)
    limit = min(max(request.args.get("limit", 200, type=int), 1), 1000)
    device_id = request.args.get("device_id", type=int)
    return jsonify(_ctx()["incidents"].report(since=since, device_id=device_id, limit=limit))


# ---------------------------------------------------------------- network scanner
@api_bp.get("/scan/default")
def scan_default():
    """Suggested subnet to scan (the one this machine is on), or null if unknown."""
    return jsonify({"subnet": _ctx()["scanner"].default_subnet()})


@api_bp.get("/scan")
def scan_status():
    """Progress and results of the latest scan (state: idle / running / done / cancelled / error)."""
    return jsonify(_ctx()["scanner"].snapshot())


@api_bp.post("/scan")
def scan_start():
    """Start a scan: {"subnet": "192.168.1.0/24", "authorized": true}. Runs in the background."""
    network = validate_scan_payload(request.get_json(silent=True) or {})
    try:
        return jsonify(_ctx()["scanner"].start(network)), 202
    except ScanBusyError as exc:
        return _error(str(exc), 409)


@api_bp.post("/scan/cancel")
def scan_cancel():
    return jsonify(_ctx()["scanner"].cancel())


# ---------------------------------------------------------------- summary & auto mode
@api_bp.get("/summary")
def summary():
    return jsonify(_ctx()["monitor"].summary())


@api_bp.get("/monitor/auto")
def auto_status():
    return jsonify(_ctx()["scheduler"].status())


@api_bp.post("/monitor/auto")
def auto_configure():
    body = request.get_json(silent=True) or {}
    interval = body.get("interval")
    if interval is not None:
        try:
            interval = int(interval)
        except (TypeError, ValueError):
            return _error("interval must be a number of seconds", 422)
    enabled = body.get("enabled")
    return jsonify(_ctx()["scheduler"].configure(
        enabled=None if enabled is None else bool(enabled), interval=interval))
