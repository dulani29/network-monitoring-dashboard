"""Application factory – wires together the layers.

Layers (top → bottom):
    controllers  – HTTP routes (Flask blueprints), request/response only
    services     – business logic (ping, monitoring, scheduling)
    repositories – SQL / persistence
    models       – plain data classes
"""
from flask import Flask

from .database import Database
from .repositories.device_repository import DeviceRepository
from .repositories.history_repository import HistoryRepository
from .repositories.incident_repository import IncidentRepository
from .repositories.settings_repository import SettingsRepository
from .services.incident_service import IncidentService
from .services.ping_service import PingService
from .services.traceroute_service import run_traceroute as traceroute_run

from .services.monitor_service import MonitorService
from .repositories.user_repository import UserRepository
from .services.auth_service import AuthService
from flask_bcrypt import Bcrypt
import os, secrets


from .services.scanner_service import ScannerService
from .services.scheduler import MonitorScheduler

from .services.network_utils import detect_default_gateway
from .controllers.api_controller import api_bp
from .controllers.web_controller import web_bp
from .controllers.auth_controller import auth_bp


def create_app(config_object) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_object)

    # Secret key for session signing
    app.secret_key = os.getenv('SECRET_KEY', secrets.token_hex(32))
    # Bcrypt instance for password hashing
    bcrypt = Bcrypt(app)
    app.extensions['bcrypt'] = bcrypt

    # --- persistence ---
    db = Database(app.config["DATABASE_PATH"])
    db.init_schema()
    devices = DeviceRepository(db)
    history = HistoryRepository(db)
    settings = SettingsRepository(db)
    incident_repo = IncidentRepository(db)
    # user repo and auth service
    user_repo = UserRepository(db)
    auth_service = AuthService(user_repo, app.extensions.get('bcrypt'))

    # --- services ---
    ping = PingService(
        count=app.config["PING_COUNT"],
        timeout=app.config["PING_TIMEOUT"],
    )
    incidents = IncidentService(incident_repo, devices)
    monitor = MonitorService(
        devices=devices,
        history=history,
        ping=ping,
        max_workers=app.config["MAX_WORKERS"],
        high_latency_ms=app.config["HIGH_LATENCY_MS"],
        incidents=incidents,
    )
    scanner = ScannerService(
        devices=devices,
        ping=PingService(count=1, timeout=app.config["SCAN_PING_TIMEOUT"]),
        max_workers=app.config["SCAN_WORKERS"],
        enrich=app.config["SCAN_ENRICH"],
    )
    scheduler = MonitorScheduler(
        monitor=monitor,
        history=history,
        settings=settings,
        retention_days=app.config["HISTORY_RETENTION_DAYS"],
        default_enabled=app.config["AUTO_MONITOR_DEFAULT"],
        default_interval=app.config["AUTO_INTERVAL_DEFAULT"],
        min_interval=app.config["MIN_INTERVAL"],
        incidents=incident_repo,
    )

    # Expose to controllers through one container.
    app.extensions["netmon"] = {
        "devices": devices,
        "history": history,
        "monitor": monitor,
        "scheduler": scheduler,
        "incidents": incidents,
        "scanner": scanner,
    }
    # expose auth service
    app.extensions["auth_service"] = auth_service

    # Register blueprints
    app.register_blueprint(web_bp)
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(auth_bp, url_prefix="/auth")


    if app.config.get("SEED_DEFAULT_DEVICES") and devices.count() == 0:
        _seed_defaults(devices)


    if not app.config.get("TESTING"):
        scheduler.start()

    return app


def _seed_defaults(devices: DeviceRepository) -> None:
    gateway = detect_default_gateway()
    if gateway:
        devices.create("Default Gateway (Router)", gateway, "router")
    devices.create("This Computer (loopback)", "127.0.0.1", "laptop")
    devices.create("Google DNS", "8.8.8.8", "dns")
    devices.create("Cloudflare DNS", "1.1.1.1", "dns")
