# Catatan untuk sesi Claude yang kerja di repo ini

Repo ini kadang dikerjakan dari 2 sesi Claude sekaligus (mis. satu di
laptop dev, satu lagi jalan langsung di mini PC untuk investigasi
lapangan). Supaya tidak saling tabrakan atau menduplikasi kerjaan:

- **`git pull` dulu sebelum mulai kerja**, tiap kali. Commit dari sesi
  lain bisa masuk kapan saja tanpa pemberitahuan langsung ke sesi ini.
- **Fokus ke yang diminta/dilaporkan user**, bukan refactor atau
  "sekalian beresin" area lain yang tidak disebut - mengurangi risiko
  dua sesi mengubah file yang sama dengan asumsi yang beda.
- **Baca dulu, jangan asumsi** - kalau sebuah bug/fitur kelihatannya
  sudah pernah dikerjakan (nama fungsi/variabel terasa asing atau lebih
  matang dari yang diingat), cek `git log` dulu sebelum menganggapnya
  belum ada - kemungkinan besar sesi lain sudah menanganinya.
- **Commit kecil & sering**, bukan 1 commit raksasa - supaya kalau ada
  konflik, gampang dilacak commit mana yang menyebabkan apa.
- **`ops/` (agent + dashboard kontrol deploy)** dan `migration/`
  (script setup mini PC) sengaja dipisah dari kode aplikasi POS utama
  (`app/`) - perubahan di salah satu biasanya tidak perlu menyentuh
  yang lain.

Detail arsitektur ops/deploy ada di [`ops/agent.py`](ops/agent.py) dan
[`ops/dashboard.html`](ops/dashboard.html) (komentar di kedua file itu
menjelaskan alasan tiap keputusan desain, bukan cuma "apa"-nya).
