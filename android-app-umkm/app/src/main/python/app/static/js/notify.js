// Semua nada notifikasi dibikin langsung lewat Web Audio API (bukan
// file .mp3/.wav) supaya tidak butuh internet/CDN sama sekali - cocok
// untuk jaringan lokal tanpa akses luar. Tiap preset cuma daftar nada
// (frekuensi + waktu mulai + durasi) yang dimainkan berurutan/tumpang
// tindih untuk bikin karakter bunyi yang beda-beda. "type" nentuin
// bentuk gelombang osilatornya - "sine" buat karakter lonceng yang
// bersih, "square"/"sawtooth"/"triangle" buat karakter alarm/sirine
// yang lebih keras & mendesak (kaya gelombang kotak/gergaji secara
// alami punya lebih banyak harmonik, jadi kedengaran lebih "tajam").
const NOTIFICATION_SOUNDS = {
  church_bell: {
    label_id: "Lonceng Gereja",
    label_en: "Church Bell",
    type: "sine",
    notes: [
      { freq: 440.0, offset: 0, duration: 1.1 },
      { freq: 659.25, offset: 0, duration: 1.1 },
    ],
  },
  double_bell_loud: {
    label_id: "Bel Ganda Keras",
    label_en: "Loud Double Bell",
    type: "sine",
    notes: [
      { freq: 1046.5, offset: 0, duration: 0.4 },
      { freq: 1318.5, offset: 0.2, duration: 0.5 },
    ],
  },
  fire_alarm: {
    label_id: "Alarm Kebakaran",
    label_en: "Fire Alarm",
    type: "square",
    notes: [
      { freq: 1200, offset: 0, duration: 0.1 },
      { freq: 900, offset: 0.12, duration: 0.1 },
      { freq: 1200, offset: 0.24, duration: 0.1 },
      { freq: 900, offset: 0.36, duration: 0.1 },
      { freq: 1200, offset: 0.48, duration: 0.1 },
      { freq: 900, offset: 0.6, duration: 0.1 },
    ],
  },
  siren_alarm: {
    label_id: "Sirine Alarm",
    label_en: "Siren Alarm",
    type: "triangle",
    notes: [
      { freq: 700, offset: 0, duration: 0.1 },
      { freq: 950, offset: 0.1, duration: 0.1 },
      { freq: 1200, offset: 0.2, duration: 0.1 },
      { freq: 950, offset: 0.3, duration: 0.1 },
      { freq: 700, offset: 0.4, duration: 0.1 },
      { freq: 950, offset: 0.5, duration: 0.1 },
      { freq: 1200, offset: 0.6, duration: 0.1 },
    ],
  },
  door_bell_loud: {
    label_id: "Bel Pintu Keras",
    label_en: "Loud Doorbell",
    type: "sine",
    notes: [
      { freq: 1318.5, offset: 0, duration: 0.4 },
      { freq: 987.77, offset: 0.3, duration: 0.6 },
    ],
  },
  kitchen_alarm_urgent: {
    label_id: "Alarm Dapur Mendesak",
    label_en: "Urgent Kitchen Alarm",
    type: "square",
    notes: [
      { freq: 880, offset: 0, duration: 0.13 },
      { freq: 660, offset: 0.16, duration: 0.13 },
      { freq: 880, offset: 0.32, duration: 0.13 },
      { freq: 660, offset: 0.48, duration: 0.13 },
    ],
  },
  metal_gong: {
    label_id: "Gong Logam",
    label_en: "Metal Gong",
    type: "sawtooth",
    notes: [{ freq: 220, offset: 0, duration: 1.4 }],
  },
  alarm_clock: {
    label_id: "Alarm Jam Weker",
    label_en: "Alarm Clock",
    type: "square",
    notes: [
      { freq: 1500, offset: 0, duration: 0.09 },
      { freq: 1500, offset: 0.18, duration: 0.09 },
      { freq: 1500, offset: 0.36, duration: 0.09 },
      { freq: 1500, offset: 0.54, duration: 0.09 },
    ],
  },
  emergency_beacon: {
    label_id: "Alarm Darurat",
    label_en: "Emergency Beacon",
    type: "triangle",
    notes: [
      { freq: 1000, offset: 0, duration: 0.2 },
      { freq: 1400, offset: 0.22, duration: 0.2 },
      { freq: 1000, offset: 0.44, duration: 0.2 },
      { freq: 1400, offset: 0.66, duration: 0.2 },
    ],
  },
  warning_horn: {
    label_id: "Klakson Peringatan",
    label_en: "Warning Horn",
    type: "sawtooth",
    notes: [
      { freq: 349.23, offset: 0, duration: 0.45 },
      { freq: 349.23, offset: 0.55, duration: 0.45 },
    ],
  },
};

const DEFAULT_SOUND_KEY = "church_bell";

// Browser (terutama Chrome di Android/tablet) memblokir AudioContext
// sampai ada interaksi user di halaman - sekali di-unlock lewat tap/klik
// apa saja, context ini dipakai ulang terus (bukan bikin baru tiap bunyi)
// supaya tetap aktif selama tab tidak di-reload/navigasi ulang. Halaman
// Dapur & Kasir sengaja sudah diubah untuk refresh data lewat AJAX (lihat
// refreshKitchenList/refreshCashierList), bukan window.location.reload(),
// justru supaya context ini tidak ke-reset tiap ada pesanan baru.
let _sharedAudioCtx = null;

function getAudioCtx() {
  if (!_sharedAudioCtx) {
    try {
      _sharedAudioCtx = new (window.AudioContext || window.webkitAudioContext)();
    } catch (e) {
      return null;
    }
  }
  return _sharedAudioCtx;
}

function unlockAudioCtx() {
  const ctx = getAudioCtx();
  if (ctx && ctx.state === "suspended") {
    ctx.resume().catch(function () {});
  }
}

["click", "touchstart", "keydown"].forEach(function (evt) {
  document.addEventListener(evt, unlockAudioCtx, { passive: true });
});

// Label nada notifikasi mengikuti bahasa aktif (document.documentElement.lang,
// diset base.html dari session Flask-Babel) - notify.js file statis, tidak
// lewat Jinja, jadi terjemahan label dipilih di sisi client seperti ini.
function getSoundLabel(soundKey) {
  const preset = NOTIFICATION_SOUNDS[soundKey] || NOTIFICATION_SOUNDS[DEFAULT_SOUND_KEY];
  const lang = (document.documentElement.lang || "id").toLowerCase();
  return lang.startsWith("en") ? preset.label_en : preset.label_id;
}

// Mainkan satu preset nada pada level volume tertentu (0-100). Dipakai
// baik oleh poller notifikasi maupun tombol "coba" di halaman Pengaturan.
// Kalau soundKey "custom" dan customUrl ada isinya, mainkan file yang
// diupload Owner (bukan nada sintesis) - fallback otomatis ke nada
// bawaan kalau belum ada file yang diupload.
function playOrderChime(soundKey, volume, customUrl) {
  try {
    const vol = Math.max(0, Math.min(100, typeof volume === "number" ? volume : 70)) / 100;

    if (vol <= 0) return;

    if (soundKey === "custom" && customUrl) {
      const audio = new Audio(customUrl);
      audio.volume = vol;
      audio.play().catch(function () {});
      return;
    }

    const preset = NOTIFICATION_SOUNDS[soundKey] || NOTIFICATION_SOUNDS[DEFAULT_SOUND_KEY];

    const ctx = getAudioCtx();
    if (!ctx) return;
    if (ctx.state === "suspended") ctx.resume().catch(function () {});
    const now = ctx.currentTime;

    preset.notes.forEach(function (note) {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.type = preset.type || "sine";
      osc.frequency.value = note.freq;

      const peak = Math.max(0.0001, 0.75 * vol);
      gain.gain.setValueAtTime(0.0001, now + note.offset);
      gain.gain.exponentialRampToValueAtTime(peak, now + note.offset + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + note.offset + note.duration);

      osc.start(now + note.offset);
      osc.stop(now + note.offset + note.duration + 0.05);
    });
  } catch (e) {
    // Browser blokir audio (belum ada interaksi user) - biarkan saja,
    // tidak perlu ganggu tampilan dengan error.
  }
}

// Poll berkala satu endpoint JSON berisi {order_ids: [...]}, bandingkan
// dengan hasil poll sebelumnya, bunyikan chime kalau ada ID baru yang
// belum pernah terlihat. Preferensi mute per-device disimpan di
// localStorage, terpisah dari master on/off & pilihan nada yang
// diatur Owner lewat Pengaturan Toko.
function startOrderPoller(options) {
  const muteKey = options.muteKey;
  let knownIds = null;

  function isMuted() {
    try {
      return localStorage.getItem(muteKey) === "1";
    } catch (e) {
      return false;
    }
  }

  function setMuted(muted) {
    try {
      localStorage.setItem(muteKey, muted ? "1" : "0");
    } catch (e) {
      // ignore - private mode dll, cukup tidak tersimpan antar sesi
    }
  }

  function poll() {
    fetch(options.statusUrl)
      .then((res) => {
        if (!res.ok || res.redirected) throw new Error("poll failed");
        return res.json();
      })
      .then((data) => {
        const ids = data.order_ids || [];

        if (knownIds === null) {
          knownIds = new Set(ids);
          return;
        }

        const newOnes = ids.filter((id) => !knownIds.has(id));
        const removedAny = Array.from(knownIds).some((id) => !ids.includes(id));
        knownIds = new Set(ids);

        // Bunyi cuma untuk yang BARU, tapi daftar tetap di-refresh juga
        // kalau ada yang hilang (dibayar/dibatalkan/diantar dari device
        // lain) - supaya layar ini tidak menampilkan pesanan yang sudah
        // tidak ada.
        if (newOnes.length > 0 && options.enabled !== false && !isMuted()) {
          playOrderChime(options.soundKey, options.volume, options.customSoundUrl);
        }
        if ((newOnes.length > 0 || removedAny) && options.onNewOrder) {
          options.onNewOrder(newOnes);
        }
      })
      .catch(() => {});
  }

  setInterval(poll, options.intervalMs || 8000);

  return { isMuted: isMuted, setMuted: setMuted };
}

// Dipasang di tombol toggle suara supaya ikonnya berubah & preferensi
// tersimpan. Panggil sekali setelah startOrderPoller().
function wireMuteToggle(buttonId, iconId, poller) {
  const button = document.getElementById(buttonId);
  const icon = document.getElementById(iconId);

  if (!button || !icon) return;

  function refreshIcon() {
    const lang = (document.documentElement.lang || "id").toLowerCase();
    const isEn = lang.startsWith("en");
    icon.className = poller.isMuted() ? "bi bi-volume-mute-fill" : "bi bi-volume-up-fill";
    button.classList.toggle("muted", poller.isMuted());
    button.title = poller.isMuted()
      ? (isEn ? "Notification sound off - click to enable" : "Suara notifikasi mati - klik untuk aktifkan")
      : (isEn ? "Notification sound on - click to mute" : "Suara notifikasi aktif - klik untuk matikan");
  }

  button.addEventListener("click", function () {
    poller.setMuted(!poller.isMuted());
    refreshIcon();
  });

  refreshIcon();
}
