from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_babel import gettext as _
from flask_login import current_user, login_required, login_user, logout_user

from .. import db
from ..models import User, LoginLog

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("staff.dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = User.query.filter_by(username=username).first()

        if user and user.is_active_user and user.check_password(password):
            login_user(user)
            user.last_seen_at = datetime.now()
            user.is_logged_in = True
            db.session.add(LoginLog(
                username=user.username,
                event="login",
                ip_address=request.remote_addr,
            ))
            db.session.commit()
            return redirect(request.args.get("next") or url_for("staff.dashboard"))

        flash(_("Username atau password salah."), "danger")

    return render_template("auth/login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    db.session.add(LoginLog(
        username=current_user.username,
        event="logout",
        ip_address=request.remote_addr,
    ))
    # Set is_logged_in=False supaya langsung kelihatan offline (bukan
    # nunggu ONLINE_THRESHOLD_MINUTES habis dulu), tapi last_seen_at
    # dibiarkan supaya "Terakhir aktif" tetap kelihatan setelah logout.
    current_user.is_logged_in = False
    db.session.commit()

    logout_user()
    return redirect(url_for("auth.login"))
