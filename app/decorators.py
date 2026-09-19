from functools import wraps

from flask import abort
from flask_login import current_user, login_required


def roles_required(*roles):
    """Batasi route hanya untuk role tertentu. Otomatis mengarahkan ke
    halaman login kalau belum login, dan 403 kalau role tidak sesuai."""

    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapped(*args, **kwargs):
            if current_user.role not in roles:
                abort(403)
            return view_func(*args, **kwargs)

        return wrapped

    return decorator
