// Tes Worker memakai SQLite sungguhan (node:sqlite) lewat adaptor tipis berbentuk D1.
import test from "node:test";
import assert from "node:assert/strict";
import { DatabaseSync } from "node:sqlite";
import { readFileSync } from "node:fs";

import worker, { validate } from "../src/worker.js";

function makeEnv(overrides = {}) {
  const db = new DatabaseSync(":memory:");
  db.exec(readFileSync(new URL("../schema.sql", import.meta.url), "utf8"));
  const DB = {
    prepare(sql) {
      const make = (args) => ({
        bind: (...a) => make(a),
        first: async () => db.prepare(sql).get(...args) ?? null,
        all: async () => ({ results: db.prepare(sql).all(...args) }),
        run: async () => { db.prepare(sql).run(...args); return { success: true }; },
      });
      return make([]);
    },
  };
  return { DB, ADMIN_TOKEN: "rahasia-admin", MAX_DEVICES: "5000", _db: db, ...overrides };
}

const BASE = "https://monitor.example";
const hb = (body, env) => worker.fetch(new Request(BASE + "/v1/hb", { method: "POST", body: typeof body === "string" ? body : JSON.stringify(body) }), env);
const list = (env, token = "rahasia-admin") =>
  worker.fetch(new Request(BASE + "/v1/devices", { headers: token ? { authorization: "Bearer " + token } : {} }), env);
const good = { d: "K7QM2XPD4VR5WZ3T", v: "1.0.6", m: "trial", x: "", p: "android", l: "id" };

test("heartbeat valid disimpan lalu muncul di daftar", async () => {
  const env = makeEnv();
  const res = await hb(good, env);
  assert.equal(res.status, 200);
  assert.equal((await res.json()).new, true);
  const data = await (await list(env)).json();
  assert.equal(data.devices.length, 1);
  assert.equal(data.devices[0].device, "K7QM2XPD4VR5WZ3T");
  assert.equal(data.devices[0].version, "1.0.6");
  assert.equal(data.devices[0].mode, "trial");
});

test("kode perangkat huruf kecil dinormalkan; sewa menyimpan tanggal berakhir", async () => {
  const env = makeEnv();
  await hb({ ...good, d: "k7qm2xpd4vr5wz3t", m: "rental", x: "20261108" }, env);
  const d = (await (await list(env)).json()).devices[0];
  assert.equal(d.device, "K7QM2XPD4VR5WZ3T");
  assert.equal(d.expiry, "20261108");
});

test("kiriman beruntun dalam 60 detik tidak menulis ulang", async () => {
  const env = makeEnv();
  await hb(good, env);
  const second = await (await hb({ ...good, v: "9.9.9" }, env)).json();
  assert.equal(second.skipped, true);
  assert.equal((await (await list(env)).json()).devices[0].version, "1.0.6");
});

test("setelah lewat 60 detik, status diperbarui (versi baru)", async () => {
  const env = makeEnv();
  await hb(good, env);
  env._db.exec("UPDATE devices SET last_seen = last_seen - 120");
  const res = await (await hb({ ...good, v: "1.0.7", m: "permanent" }, env)).json();
  assert.equal(res.ok, true);
  const d = (await (await list(env)).json()).devices[0];
  assert.equal(d.version, "1.0.7");
  assert.equal(d.mode, "permanent");
  assert.ok(d.last_seen > d.first_seen - 1);
});

test("kiriman tidak sah ditolak", async () => {
  const env = makeEnv();
  for (const bad of [
    "bukan json",
    { ...good, d: "pendek" },
    { ...good, d: "K7QM2XPD4VR9WZ3!" },
    { ...good, m: "hacker" },
    { ...good, p: "windows" },
    { ...good, v: "<script>" },
    { ...good, x: "besok" },
  ]) {
    const res = await hb(bad, env);
    assert.equal(res.status, 400, JSON.stringify(bad));
  }
  assert.equal((await (await list(env)).json()).devices.length, 0);
});

test("badan terlalu besar ditolak", async () => {
  const env = makeEnv();
  const res = await hb(JSON.stringify({ ...good, pad: "x".repeat(2000) }), env);
  assert.equal(res.status, 413);
});

test("daftar butuh token admin yang benar", async () => {
  const env = makeEnv();
  await hb(good, env);
  assert.equal((await list(env, "")).status, 401);
  assert.equal((await list(env, "salah")).status, 401);
  assert.equal((await list(env, "rahasia-admin")).status, 200);
  const noToken = makeEnv({ ADMIN_TOKEN: "" });
  assert.equal((await list(noToken, "")).status, 401);
});

test("batas jumlah perangkat baru", async () => {
  const env = makeEnv({ MAX_DEVICES: "2" });
  await hb({ ...good, d: "AAAAAAAAAAAAAAAA" }, env);
  await hb({ ...good, d: "BBBBBBBBBBBBBBBB" }, env);
  const full = await hb({ ...good, d: "CCCCCCCCCCCCCCCC" }, env);
  assert.equal(full.status, 507);
  // perangkat yang sudah terdaftar tetap boleh memperbarui status
  env._db.exec("UPDATE devices SET last_seen = last_seen - 500");
  assert.equal((await hb({ ...good, d: "AAAAAAAAAAAAAAAA", v: "2.0.0" }, env)).status, 200);
});

test("data tidak aktif lebih dari 180 hari dibersihkan saat daftar dibuka", async () => {
  const env = makeEnv();
  await hb(good, env);
  env._db.exec("UPDATE devices SET last_seen = last_seen - 200*24*3600");
  assert.equal((await (await list(env)).json()).devices.length, 0);
});

test("rute tak dikenal 404, root ok", async () => {
  const env = makeEnv();
  assert.equal((await worker.fetch(new Request(BASE + "/lain"), env)).status, 404);
  assert.equal(await (await worker.fetch(new Request(BASE + "/"), env)).text(), "ok");
});

test("validate mengembalikan null untuk bukan objek", () => {
  assert.equal(validate(null), null);
  assert.equal(validate("x"), null);
});
