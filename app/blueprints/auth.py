from datetime import datetime
from urllib.parse import urlparse

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_babel import gettext as _
from flask_login import current_user, login_required, login_user, logout_user

from .. import db
from ..models import User, LoginLog
from ..rate_limit import clear_failures, is_blocked, record_failure

auth_bp = Blueprint("auth", __name__)

# Maks 10 percobaan login gagal / 5 menit per (IP, username) - cukup
# longgar buat staf yang salah ketik password berkali-kali, tapi
# menghambat script brute-force nebak password.
LOGIN_RATE_LIMIT = 10
LOGIN_RATE_WINDOW_SECONDS = 5 * 60


def is_safe_next_url(target):
    """Cuma terima path relatif di aplikasi ini sendiri (mis. "/cashier")
    sebagai tujuan ?next= setelah login - URL absolut ke domain lain
    ("https://..."), "//evil.com" atau "/\\evil.com" (dianggap browser
    sebagai URL ke host lain) ditolak supaya link login palsu tidak bisa
    melempar staf ke halaman phishing sesudah berhasil login."""

    if not target or not target.startswith("/") or target.startswith("//") or target.startswith("/\\"):
        return False
    parsed = urlparse(target)
    return not parsed.scheme and not parsed.netloc


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("staff.dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        rate_key = f"{request.remote_addr}:{username.lower()}"
        if is_blocked(rate_key, LOGIN_RATE_LIMIT, LOGIN_RATE_WINDOW_SECONDS):
            flash(_("Terlalu banyak percobaan login gagal. Coba lagi beberapa menit lagi."), "danger")
            return render_template("auth/login.html")

        user = User.query.filter_by(username=username).first()

        if user and user.is_active_user and user.check_password(password):
            clear_failures(rate_key)
            # Buang sisa session login sebelumnya (mis. status "PIN
            # developer sudah dibuka" milik Owner lain di tablet yang sama)
            # sebelum user baru masuk. Pilihan bahasa tetap dibawa.
            lang = session.get("lang")
            session.clear()
            if lang:
                session["lang"] = lang
            login_user(user)
            user.last_seen_at = datetime.now()
            user.is_logged_in = True
            db.session.add(LoginLog(
                username=user.username,
                event="login",
                ip_address=request.remote_addr,
            ))
            db.session.commit()
            next_url = request.args.get("next")
            if is_safe_next_url(next_url):
                return redirect(next_url)
            return redirect(url_for("staff.dashboard", show_login_loader=1))

        record_failure(rate_key, LOGIN_RATE_WINDOW_SECONDS)
        flash(_("Username atau password salah."), "danger")

    return render_template("auth/login.html")


@auth_bp.route("/logout", methods=["POST"])
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
    # Hapus seluruh session (bukan cuma key milik Flask-Login) - termasuk
    # status "PIN developer sudah dibuka" Mode Demo/Reset Pabrik, supaya
    # tidak ikut terbawa ke siapa pun yang login berikutnya di device ini.
    lang = session.get("lang")
    session.clear()
    if lang:
        session["lang"] = lang
    return redirect(url_for("auth.login"))
