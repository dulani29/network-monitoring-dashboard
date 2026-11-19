"""Serves the dashboard page (the 'View' entry point)."""
from flask import Blueprint, render_template, session, redirect, url_for, flash

from ..models import DEVICE_TYPES

web_bp = Blueprint("web", __name__)


@web_bp.route("/")
def dashboard():
    if "user_id" not in session:
        flash('Please log in to view the dashboard.', 'warning')
        return redirect(url_for('auth.login'))
    return render_template("dashboard.html", device_types=DEVICE_TYPES)
