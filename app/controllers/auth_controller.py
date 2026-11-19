"""Authentication controller – login, register, logout routes."""

from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        auth_service = current_app.extensions.get('auth_service')
        user = auth_service.verify_login(username, password)
        if user:
            session['user_id'] = user['id']
            flash('Logged in successfully.', 'success')
            return redirect(url_for('web.dashboard'))
        flash('Invalid username or password.', 'danger')
    return render_template('login.html')

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        auth_service = current_app.extensions.get('auth_service')
        try:
            auth_service.register_user(username, password)
            flash('User registered, please log in.', 'success')
            return redirect(url_for('auth.login'))
        except Exception as e:
            flash(f'Registration failed: {e}', 'danger')
    return render_template('register.html')

@auth_bp.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('Logged out.', 'info')
    return redirect(url_for('auth.login'))
