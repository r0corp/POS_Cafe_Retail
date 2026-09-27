// Mengganti tampilan daftar pilihan <select> bawaan browser (kotak, tidak
// bisa distyle) dengan panel dropdown kustom yang mengikuti desain aplikasi.
// <select> aslinya tetap ada (disembunyikan tapi tetap fokusable) supaya
// name/value/required tetap jalan normal saat form dikirim.
(function () {
  function enhance(select) {
    var wrap = document.createElement("div");
    wrap.className = "elegant-select";
    select.parentNode.insertBefore(wrap, select);
    wrap.appendChild(select);
    select.classList.add("elegant-select-native");

    var trigger = document.createElement("button");
    trigger.type = "button";
    trigger.className = "elegant-select-trigger";
    wrap.appendChild(trigger);

    var menu = document.createElement("div");
    menu.className = "elegant-select-menu";
    wrap.appendChild(menu);

    function renderOptions() {
      menu.innerHTML = "";
      Array.prototype.forEach.call(select.options, function (opt) {
        var item = document.createElement("button");
        item.type = "button";
        item.className = "elegant-select-option" + (opt.value === select.value ? " is-active" : "");
        item.textContent = opt.textContent;
        item.addEventListener("click", function () {
          select.value = opt.value;
          select.dispatchEvent(new Event("change", { bubbles: true }));
          syncTrigger();
          closeMenu();
        });
        menu.appendChild(item);
      });
    }

    function syncTrigger() {
      var selected = select.options[select.selectedIndex];
      trigger.textContent = selected ? selected.textContent : "";
      renderOptions();
    }

    // Ruang di bawah trigger cukup? Kalau tidak (misal trigger-nya di
    // dekat bagian bawah layar/modal), buka ke atas - tiap dropdown
    // dicek sendiri-sendiri sesuai posisinya di layout masing-masing,
    // bukan dipukul rata satu arah untuk semua halaman.
    var MENU_ESTIMATED_HEIGHT = 246;

    function positionMenu() {
      var rect = trigger.getBoundingClientRect();
      var spaceBelow = window.innerHeight - rect.bottom;
      var spaceAbove = rect.top;
      var openUp = spaceBelow < MENU_ESTIMATED_HEIGHT && spaceAbove > spaceBelow;
      menu.classList.toggle("opens-up", openUp);
    }

    function openMenu() {
      document.querySelectorAll(".elegant-select-menu.is-open").forEach(function (m) {
        m.classList.remove("is-open");
      });
      positionMenu();
      menu.classList.add("is-open");
      trigger.classList.add("is-open");
    }

    function closeMenu() {
      menu.classList.remove("is-open");
      trigger.classList.remove("is-open");
    }

    trigger.addEventListener("click", function (e) {
      e.stopPropagation();
      if (select.disabled) return;
      if (menu.classList.contains("is-open")) {
        closeMenu();
      } else {
        openMenu();
      }
    });

    select.addEventListener("change", syncTrigger);

    trigger.disabled = select.disabled;
    syncTrigger();
  }

  document.addEventListener("click", function () {
    document.querySelectorAll(".elegant-select-menu.is-open").forEach(function (m) {
      m.classList.remove("is-open");
    });
  });

  // Dipanggil ulang setelah konten baru disisipkan lewat AJAX (misal
  // refresh daftar pesanan Kasir tanpa reload halaman) supaya <select>
  // yang baru masuk DOM ikut dapat tampilan kustom ini. Guard ":not(...)"
  // mencegah select yang sama di-enhance dobel kalau root-nya kepanggil
  // lebih dari sekali.
  function enhanceAll(root) {
    (root || document).querySelectorAll("select[data-elegant-select]:not(.elegant-select-native)").forEach(enhance);
  }

  enhanceAll(document);
  window.enhanceElegantSelect = enhanceAll;
})();
