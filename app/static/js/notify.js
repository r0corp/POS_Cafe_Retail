// Semua nada notifikasi dibikin langsung lewat Web Audio API (bukan
// file .mp3/.wav) supaya tidak butuh internet/CDN sama sekali - cocok
// untuk jaringan lokal tanpa akses luar. Tiap preset cuma daftar nada
// (frekuensi + waktu mulai + durasi) yang dimainkan berurutan/tumpang
// tindih untuk bikin karakter bunyi yang beda-beda.
const NOTIFICATION_SOUNDS = {
  bell_double: {
    label_id: "Bel Ganda",
    label_en: "Double Bell",
    notes: [
      { freq: 880.0, offset: 0, duration: 0.35 },
      { freq: 1046.5, offset: 0.18, duration: 0.35 },
    ],
  },
  ding_dong: {
    label_id: "Ding Dong",
    label_en: "Ding Dong",
    notes: [
      { freq: 1046.5, offset: 0, duration: 0.4 },
      { freq: 783.99, offset: 0.28, duration: 0.55 },
    ],
  },
  single_beep: {
    label_id: "Bip Tunggal",
    label_en: "Single Beep",
    notes: [{ freq: 1000.0, offset: 0, duration: 0.28 }],
  },
  triple_beep: {
    label_id: "Bip Cepat 3x",
    label_en: "Triple Beep",
    notes: [
      { freq: 1200.0, offset: 0, duration: 0.12 },
      { freq: 1200.0, offset: 0.16, duration: 0.12 },
      { freq: 1200.0, offset: 0.32, duration: 0.12 },
    ],
  },
  cashier_bell: {
    label_id: "Lonceng Kasir",
    label_en: "Cashier Bell",
    notes: [{ freq: 1568.0, offset: 0, duration: 0.65 }],
  },
  soft_chime: {
    label_id: "Notifikasi Lembut",
    label_en: "Soft Chime",
    notes: [{ freq: 523.25, offset: 0, duration: 0.75 }],
  },
  kitchen_alarm: {
    label_id: "Alarm Dapur",
    label_en: "Kitchen Alarm",
    notes: [
      { freq: 660.0, offset: 0, duration: 0.14 },
      { freq: 880.0, offset: 0.17, duration: 0.14 },
      { freq: 660.0, offset: 0.34, duration: 0.14 },
      { freq: 880.0, offset: 0.51, duration: 0.14 },
    ],
  },
  marimba: {
    label_id: "Marimba",
    label_en: "Marimba",
    notes: [
      { freq: 1046.5, offset: 0, duration: 0.3 },
      { freq: 880.0, offset: 0.16, duration: 0.3 },
      { freq: 698.46, offset: 0.32, duration: 0.42 },
    ],
  },
  electronic_ping: {
    label_id: "Elektronik",
    label_en: "Electronic Ping",
    notes: [{ freq: 1500.0, offset: 0, duration: 0.16 }],
  },
  classic_restaurant: {
    label_id: "Restoran Klasik",
    label_en: "Classic Restaurant",
    notes: [
      { freq: 783.99, offset: 0, duration: 0.3 },
      { freq: 783.99, offset: 0.34, duration: 0.48 },
    ],
  },
};

const DEFAULT_SOUND_KEY = "bell_double";

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
function playOrderChime(soundKey, volume) {
  try {
    const preset = NOTIFICATION_SOUNDS[soundKey] || NOTIFICATION_SOUNDS[DEFAULT_SOUND_KEY];
    const vol = Math.max(0, Math.min(100, typeof volume === "number" ? volume : 70)) / 100;

    if (vol <= 0) return;

    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const now = ctx.currentTime;

    preset.notes.forEach(function (note) {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.type = "sine";
      osc.frequency.value = note.freq;

      const peak = Math.max(0.0001, 0.5 * vol);
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
      .then((res) => res.json())
      .then((data) => {
        const ids = data.order_ids || [];

        if (knownIds === null) {
          knownIds = new Set(ids);
          return;
        }

        const newOnes = ids.filter((id) => !knownIds.has(id));
        knownIds = new Set(ids);

        if (newOnes.length > 0) {
          if (options.enabled !== false && !isMuted()) {
            playOrderChime(options.soundKey, options.volume);
          }
          if (options.onNewOrder) options.onNewOrder(newOnes);
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
