// Pantau Aplikasi Oru POS GO - Cloudflare Worker + D1.
//
//   POST /v1/hb       heartbeat dari aplikasi GO (tanpa login; hanya status ringan)
//   GET  /v1/devices  daftar perangkat untuk penjual (butuh header Authorization: Bearer <ADMIN_TOKEN>)
//   GET  /            "ok" (cek hidup)
//
// Data yang diterima per perangkat: Kode Perangkat, versi aplikasi, mode lisensi, tanggal berakhir sewa,
// platform, bahasa. TIDAK ada nama toko, data penjualan, atau lokasi.

const DEVICE_RE = /^[A-Z2-7]{16}$/;
const VERSION_RE = /^[0-9A-Za-z.\-+]{1,20}$/;
const MODES = new Set(["trial", "permanent", "rental", "expired", "unknown"]);
const PLATFORMS = new Set(["android", "ios"]);
const LANGS = new Set(["id", "en"]);
const MIN_INTERVAL_S = 60; // heartbeat yang lebih rapat dari ini diabaikan (tidak menulis ulang)
const RETENTION_S = 180 * 24 * 3600;
const MAX_BODY = 512;

const json = (body, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" } });

function safeEqual(a, b) {
  // pembanding waktu-tetap supaya token tidak bisa ditebak lewat selisih waktu respons
  const enc = new TextEncoder();
  const x = enc.encode(a || "");
  const y = enc.encode(b || "");
  let diff = x.length ^ y.length;
  for (let i = 0; i < Math.max(x.length, y.length); i++) diff |= (x[i] || 0) ^ (y[i] || 0);
  return diff === 0;
}

export function validate(payload) {
  if (!payload || typeof payload !== "object") return null;
  const device = String(payload.d || "").toUpperCase();
  const version = String(payload.v || "");
  const mode = String(payload.m || "unknown");
  const expiry = String(payload.x || "");
  const platform = String(payload.p || "android");
  const lang = String(payload.l || "id");
  if (!DEVICE_RE.test(device) || !VERSION_RE.test(version) || !MODES.has(mode) || !PLATFORMS.has(platform) || !LANGS.has(lang)) return null;
  if (expiry && !/^\d{8}$/.test(expiry)) return null;
  return { device, version, mode, expiry, platform, lang };
}

async function heartbeat(request, env, now) {
  const raw = await request.text();
  if (raw.length > MAX_BODY) return json({ ok: false, error: "too_large" }, 413);
  let data;
  try {
    data = validate(JSON.parse(raw));
  } catch {
    data = null;
  }
  if (!data) return json({ ok: false, error: "bad_request" }, 400);

  const existing = await env.DB.prepare("SELECT last_seen FROM devices WHERE device = ?").bind(data.device).first();
  if (existing) {
    if (now - existing.last_seen < MIN_INTERVAL_S) return json({ ok: true, skipped: true });
    await env.DB.prepare(
      "UPDATE devices SET version = ?, mode = ?, expiry = ?, platform = ?, lang = ?, last_seen = ? WHERE device = ?"
    ).bind(data.version, data.mode, data.expiry, data.platform, data.lang, now, data.device).run();
    return json({ ok: true });
  }

  // perangkat baru: batasi jumlah total supaya kiriman palsu tidak memenuhi database
  const max = parseInt(env.MAX_DEVICES || "5000", 10);
  const count = await env.DB.prepare("SELECT COUNT(*) AS n FROM devices").first();
  if (count && count.n >= max) return json({ ok: false, error: "full" }, 507);
  await env.DB.prepare(
    "INSERT INTO devices (device, version, mode, expiry, platform, lang, first_seen, last_seen) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
  ).bind(data.device, data.version, data.mode, data.expiry, data.platform, data.lang, now, now).run();
  return json({ ok: true, new: true });
}

async function listDevices(request, env, now) {
  const header = request.headers.get("authorization") || "";
  const token = header.startsWith("Bearer ") ? header.slice(7) : "";
  if (!env.ADMIN_TOKEN || !safeEqual(token, env.ADMIN_TOKEN)) return json({ ok: false, error: "unauthorized" }, 401);

  // buang data basi (tidak aktif > 180 hari) sebelum menampilkan
  await env.DB.prepare("DELETE FROM devices WHERE last_seen < ?").bind(now - RETENTION_S).run();
  const rows = await env.DB.prepare(
    "SELECT device, version, mode, expiry, platform, lang, first_seen, last_seen FROM devices ORDER BY last_seen DESC LIMIT 2000"
  ).all();
  return json({ ok: true, now, devices: rows.results || [] });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const now = Math.floor(Date.now() / 1000);
    try {
      if (request.method === "POST" && url.pathname === "/v1/hb") return await heartbeat(request, env, now);
      if (request.method === "GET" && url.pathname === "/v1/devices") return await listDevices(request, env, now);
      if (request.method === "GET" && url.pathname === "/") return new Response("ok", { headers: { "content-type": "text/plain" } });
    } catch (err) {
      return json({ ok: false, error: "server_error" }, 500);
    }
    return json({ ok: false, error: "not_found" }, 404);
  },
};
