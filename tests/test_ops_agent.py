"""Backup otomatis sebelum update lewat Ops Agent (ops/agent.py): backup
dibuat & diverifikasi SEBELUM POS dimatikan, /update dibatalkan kalau
backup gagal, tapi /rollback (jalur darurat) tetap jalan."""

import os
import shutil
import sqlite3
import zipfile

os.environ.setdefault("AGENT_TOKEN", "test-token-not-for-production")

import pytest

from ops import agent

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def fake_project(tmp_path, monkeypatch):
    """Folder proyek POS minimal: app/backup.py asli + database SQLite berisi
    1 baris + 1 foto upload."""

    (tmp_path / "app" / "static" / "uploads" / "menu").mkdir(parents=True)
    shutil.copy(os.path.join(REPO_ROOT, "app", "backup.py"), tmp_path / "app" / "backup.py")
    (tmp_path / "app" / "static" / "uploads" / "menu" / "menu-1.jpg").write_bytes(b"foto")
    (tmp_path / "instance").mkdir()

    conn = sqlite3.connect(str(tmp_path / "instance" / "cafe.db"))
    conn.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, note TEXT)")
    conn.execute("INSERT INTO orders (note) VALUES ('pesanan terakhir sebelum update')")
    conn.commit()
    conn.close()

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(agent, "PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr(agent, "BACKUP_FOLDER", str(tmp_path / "backups"))
    return tmp_path


def test_backup_before_deploy_writes_a_valid_restorable_zip(fake_project, tmp_path):
    ok, message = agent._backup_before_deploy()

    assert ok, message
    zips = list((fake_project / "backups").glob("cafepos_backup_*_sebelum_update.zip"))
    assert len(zips) == 1

    with zipfile.ZipFile(zips[0]) as zf:
        assert "static/uploads/menu/menu-1.jpg" in [n.replace("\\", "/") for n in zf.namelist()]
        extracted = zf.extract("instance/cafe.db", str(tmp_path / "pulih"))
    row = sqlite3.connect(extracted).execute("SELECT note FROM orders").fetchone()
    assert row[0] == "pesanan terakhir sebelum update"


def _stub_deploy_steps(monkeypatch):
    calls = []
    monkeypatch.setattr(agent, "_run", lambda cmd, **kw: (0, ""))
    monkeypatch.setattr(agent, "_stop_pos", lambda log: calls.append("stop") or "nssm")
    monkeypatch.setattr(agent, "_start_pos", lambda mode, log: calls.append("start"))
    return calls


def test_update_is_cancelled_before_stopping_pos_when_backup_fails(fake_project, monkeypatch):
    os.remove(fake_project / "instance" / "cafe.db")  # backup tidak mungkin berhasil
    calls = _stub_deploy_steps(monkeypatch)
    log = []

    assert agent._deploy_to("origin/main", log, require_fetch=True) is False

    assert calls == []  # POS tidak pernah dimatikan
    assert any("DIBATALKAN" in line for line in log)


def test_update_makes_the_backup_before_stopping_pos(fake_project, monkeypatch):
    calls = _stub_deploy_steps(monkeypatch)
    real_backup = agent._backup_before_deploy
    monkeypatch.setattr(agent, "_backup_before_deploy", lambda: calls.append("backup") or real_backup())

    assert agent._deploy_to("origin/main", [], require_fetch=True) is True

    assert calls == ["backup", "stop", "start"]


def test_rollback_still_proceeds_when_backup_fails(fake_project, monkeypatch):
    os.remove(fake_project / "instance" / "cafe.db")
    calls = _stub_deploy_steps(monkeypatch)
    log = []

    assert agent._deploy_to("abc1234", log, require_fetch=False, require_backup=False) is True

    assert calls == ["stop", "start"]
    assert any("rollback tidak boleh tertahan" in line for line in log)
