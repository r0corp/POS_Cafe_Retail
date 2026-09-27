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

// Ubah angka jadi kata Bahasa Indonesia ("50000" -> "lima puluh ribu"),
// dipakai speakPaymentAmount() di bawah supaya TTS mengucapkan nominal
// secara alami, bukan dieja digit-per-digit oleh mesin suaranya.
const _ONES_ID = ["", "satu", "dua", "tiga", "empat", "lima", "enam", "tujuh", "delapan", "sembilan"];

function _threeDigitsToWordsID(n) {
  const parts = [];
  const hundreds = Math.floor(n / 100);
  const rest = n % 100;

  if (hundreds > 0) parts.push(hundreds === 1 ? "seratus" : _ONES_ID[hundreds] + " ratus");

  if (rest > 0) {
    if (rest === 10) {
      parts.push("sepuluh");
    } else if (rest === 11) {
      parts.push("sebelas");
    } else if (rest < 10) {
      parts.push(_ONES_ID[rest]);
    } else if (rest < 20) {
      parts.push(_ONES_ID[rest - 10] + " belas");
    } else {
      const tens = Math.floor(rest / 10);
      const ones = rest % 10;
      parts.push(_ONES_ID[tens] + " puluh");
      if (ones > 0) parts.push(_ONES_ID[ones]);
    }
  }

  return parts.join(" ");
}

function numberToWordsID(n) {
  if (n === 0) return "nol";

  const groups = [
    [1000000000000, "triliun"],
    [1000000000, "miliar"],
    [1000000, "juta"],
    [1000, "ribu"],
  ];
  const parts = [];
  let remaining = Math.round(n);

  groups.forEach(function (group) {
    const value = group[0];
    const name = group[1];
    if (remaining >= value) {
      const count = Math.floor(remaining / value);
      remaining %= value;
      parts.push(value === 1000 && count === 1 ? "seribu" : _threeDigitsToWordsID(count) + " " + name);
    }
  });

  if (remaining > 0) parts.push(_threeDigitsToWordsID(remaining));

  return parts.join(" ");
}

// Versi Inggris - dipakai kalau bahasa aplikasi sedang di-set ke English
// (document.documentElement.lang), lihat speakPaymentAmount().
const _ONES_EN = [
  "", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
  "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen",
];
const _TENS_EN = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"];

function _threeDigitsToWordsEN(n) {
  const parts = [];
  const hundreds = Math.floor(n / 100);
  const rest = n % 100;

  if (hundreds > 0) parts.push(_ONES_EN[hundreds] + " hundred");

  if (rest > 0) {
    if (rest < 20) {
      parts.push(_ONES_EN[rest]);
    } else {
      const tens = Math.floor(rest / 10);
      const ones = rest % 10;
      parts.push(_TENS_EN[tens] + (ones > 0 ? "-" + _ONES_EN[ones] : ""));
    }
  }

  return parts.join(" ");
}

function numberToWordsEN(n) {
  if (n === 0) return "zero";

  const groups = [
    [1000000000000, "trillion"],
    [1000000000, "billion"],
    [1000000, "million"],
    [1000, "thousand"],
  ];
  const parts = [];
  let remaining = Math.round(n);

  groups.forEach(function (group) {
    const value = group[0];
    const name = group[1];
    if (remaining >= value) {
      const count = Math.floor(remaining / value);
      remaining %= value;
      parts.push(_threeDigitsToWordsEN(count) + " " + name);
    }
  });

  if (remaining > 0) parts.push(_threeDigitsToWordsEN(remaining));

  return parts.join(" ");
}

// Ucapkan "Uang masuk, lima puluh ribu rupiah" (atau versi Inggrisnya)
// lewat Text-to-Speech - lewat jembatan Android (window.AndroidTTS, lihat
// MainActivity.java) kalau dibuka dari APK Hotatos, atau lewat
// speechSynthesis bawaan browser sebagai cadangan (dipakai kalau halaman
// ini dibuka dari laptop/browser biasa, bukan tablet). Diam saja (tidak
// error) kalau dua-duanya tidak tersedia - toast & bunyi 'ting' tetap
// jalan normal tanpa suara ini.
function speakPaymentAmount(amount, templateID, templateEN) {
  const isEn = (document.documentElement.lang || "id").toLowerCase().startsWith("en");
  const langTag = isEn ? "en-US" : "id-ID";

  let text;
  if (amount != null) {
    const words = isEn ? numberToWordsEN(amount) : numberToWordsID(amount);
    const template = (isEn ? templateEN : templateID) || (isEn ? "Payment received, {nominal} rupiah" : "Uang masuk, {nominal} rupiah");
    text = template.replace("{nominal}", words);
  } else {
    text = isEn ? "New QRIS payment received" : "Ada pembayaran QRIS baru";
  }

  try {
    if (window.AndroidTTS && window.AndroidTTS.speak) {
      window.AndroidTTS.speak(text, langTag);
      return;
    }
    if (window.speechSynthesis) {
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = langTag;
      window.speechSynthesis.speak(utterance);
    }
  } catch (e) {
    // Mesin TTS tidak tersedia/gagal - abaikan, bukan fitur penting.
  }
}

// Poll berkala endpoint JSON berisi {payments: [{id, amount, created_at}]}
// (notifikasi "uang QRIS masuk" dari listener BCA Merchant di tablet -
// lihat receive_payment_notification() di staff.py), bunyikan chime +
// tampilkan toast buat tiap ID baru. Beda dari startOrderPoller() karena
// perlu bawa data nominal per item buat teks toast-nya, bukan cuma
// deteksi "ada yang baru".
function startPaymentNotificationPoller(options) {
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
      // ignore
    }
  }

  function formatRupiah(n) {
    return "Rp " + Number(n).toLocaleString("id-ID");
  }

  function poll() {
    fetch(options.statusUrl)
      .then((res) => {
        if (!res.ok || res.redirected) throw new Error("poll failed");
        return res.json();
      })
      .then((data) => {
        const payments = data.payments || [];

        if (knownIds === null) {
          knownIds = new Set(payments.map((p) => p.id));
          return;
        }

        const newOnes = payments.filter((p) => !knownIds.has(p.id));
        knownIds = new Set(payments.map((p) => p.id));

        if (newOnes.length === 0 || options.enabled === false || isMuted()) return;

        newOnes.forEach((p) => {
          playOrderChime(options.soundKey, options.volume, options.customSoundUrl);
          if (window.showToast) {
            window.showToast(
              p.amount != null
                ? (options.labelPrefix || "Uang masuk: ") + formatRupiah(p.amount)
                : (options.unreadableLabel || "Ada notifikasi pembayaran QRIS baru (nominal tidak terbaca)"),
              "success"
            );
          }
          if (options.voiceEnabled !== false) {
            speakPaymentAmount(p.amount, options.voiceTemplateID, options.voiceTemplateEN);
          }
        });
      })
      .catch(() => {});
  }

  setInterval(poll, options.intervalMs || 5000);

  return { isMuted: isMuted, setMuted: setMuted };
}

// Toast generik yang bisa dipanggil kapan saja lewat JS (bukan cuma dari
// flash message Jinja saat render awal halaman) - dipakai
// startPaymentNotificationPoller() di atas. Markup & animasinya PERSIS
// sama dengan toast flash bawaan (lihat base.html) supaya konsisten;
// wireToastDismiss() sengaja dipisah dari markup-nya sendiri supaya bisa
// dipakai ulang baik untuk toast yang di-render Jinja saat load maupun
// yang dibikin dinamis di sini.
const TOAST_ICONS = {
  success: "bi-check-circle-fill",
  danger: "bi-x-circle-fill",
  warning: "bi-exclamation-triangle-fill",
  info: "bi-info-circle-fill",
};

function wireToastDismiss(toast, durationMs) {
  const DURATION_MS = durationMs || 5000;
  const bar = toast.querySelector(".toast-progress");
  const closeBtn = toast.querySelector(".toast-close");
  let timer = null;

  function dismiss() {
    if (!toast.isConnected) return;
    const rect = toast.getBoundingClientRect();
    toast.style.maxHeight = rect.height + "px";
    void toast.offsetHeight;
    toast.classList.add("toast-out");
    requestAnimationFrame(function () {
      toast.style.maxHeight = "0px";
      toast.style.marginBottom = "0px";
      toast.style.paddingTop = "0px";
      toast.style.paddingBottom = "0px";
    });
    let removed = false;
    function remove() {
      if (removed) return;
      removed = true;
      toast.remove();
    }
    toast.addEventListener("transitionend", function onEnd(e) {
      if (e.propertyName === "max-height") {
        toast.removeEventListener("transitionend", onEnd);
        remove();
      }
    });
    setTimeout(remove, 500);
  }

  function startTimer() {
    if (bar) {
      bar.style.animationDuration = DURATION_MS + "ms";
      bar.style.animationPlayState = "running";
    }
    timer = setTimeout(dismiss, DURATION_MS);
  }

  function pauseTimer() {
    clearTimeout(timer);
    if (bar) bar.style.animationPlayState = "paused";
  }

  startTimer();
  toast.addEventListener("mouseenter", pauseTimer);
  toast.addEventListener("mouseleave", startTimer);
  if (closeBtn) {
    closeBtn.addEventListener("click", function () {
      clearTimeout(timer);
      dismiss();
    });
  }
}

function showToast(message, category) {
  let stack = document.getElementById("toastStack");
  if (!stack) {
    stack = document.createElement("div");
    stack.className = "toast-stack";
    stack.id = "toastStack";
    const container = document.querySelector(".container-fluid");
    if (!container) return;
    container.insertBefore(stack, container.firstChild);
  }

  const toast = document.createElement("div");
  toast.className = "toast-item toast-" + (category || "info");
  toast.setAttribute("role", "alert");
  toast.innerHTML =
    '<span class="toast-icon"><i class="bi ' + (TOAST_ICONS[category] || TOAST_ICONS.info) + '"></i></span>' +
    '<span class="toast-body"></span>' +
    '<button type="button" class="toast-close" aria-label="Close"><i class="bi bi-x"></i></button>' +
    '<span class="toast-progress"></span>';
  toast.querySelector(".toast-body").textContent = message;
  stack.appendChild(toast);
  wireToastDismiss(toast);
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
