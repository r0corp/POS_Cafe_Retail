"""PRODUCT_NAME opsional: tampil di footer & login hanya kalau diisi."""

from .conftest import login


def test_hidden_by_default(client, owner_user):
    # .env di mesin pengembang boleh berisi PRODUCT_NAME; tes ini memeriksa kondisi kosong
    client.application.config["PRODUCT_NAME"] = ""
    assert b"Oru POS Pro" not in client.get("/login").data
    login(client, "owner")
    assert b"Oru POS Pro" not in client.get("/").data


def test_shown_when_configured(client, owner_user):
    client.application.config["PRODUCT_NAME"] = "Oru POS Pro"
    assert b"Oru POS Pro" in client.get("/login").data
    login(client, "owner")
    page = client.get("/").data
    assert b"Oru POS Pro" in page
    assert b"Orulabs" in page  # kredit pembuat tetap ada
