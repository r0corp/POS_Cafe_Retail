package id.orulabs.umkm;

import android.app.Activity;
import androidx.appcompat.app.AlertDialog;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageInfo;
import android.net.Uri;
import android.os.Build;
import android.provider.Settings;
import android.webkit.ValueCallback;
import android.widget.ProgressBar;
import android.widget.Toast;

import androidx.core.content.FileProvider;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.security.MessageDigest;

/**
 * Update APK di luar Play Store: baca version.json dari repo rilis publik,
 * kalau ada versi lebih baru -> tawarkan, unduh, cocokkan SHA-256, lalu
 * buka layar instal Android. Data toko tidak ikut hilang karena yang diganti
 * hanya aplikasinya (tanda tangan APK baru WAJIB sama dengan yang terpasang,
 * kalau beda Android sendiri menolak).
 *
 * Bentuk version.json:
 * {
 *   "versionCode": 3, "versionName": "1.0.1",
 *   "apkUrl": "https://.../oru-go-1.0.1.apk", "sha256": "(hex)",
 *   "notes": "Perbaikan ...", "mandatory": false,
 *   "minSupportedVersionCode": 2
 * }
 */
public class UpdateManager {

    public interface StatusListener {
        void onStatus(String message);
    }

    /** Menjalankan JavaScript di WebView (pop-up update digambar oleh halaman, bukan dialog Android). */
    public interface JsRunner {
        void eval(String script, ValueCallback<String> callback);
    }

    private static final String PREFS = "update_prefs";
    private static final String KEY_LAST_CHECK = "last_check";
    private static final String KEY_SKIP_UNTIL = "skip_until";
    private static final String KEY_SKIP_VERSION = "skip_version";
    private static final long AUTO_CHECK_INTERVAL_MS = 6L * 60 * 60 * 1000;
    private static final long SKIP_DURATION_MS = 24L * 60 * 60 * 1000;

    private static class Info {
        int versionCode;
        String versionName;
        String apkUrl;
        String sha256;
        String notes;
        boolean mandatory;
    }

    private final Activity activity;
    private final StatusListener listener;
    private final JsRunner jsRunner;
    private Info pendingInfo;
    private final SharedPreferences prefs;
    private volatile boolean busy = false;
    private File pendingInstall = null;

    public UpdateManager(Activity activity, StatusListener listener, JsRunner jsRunner) {
        this.activity = activity;
        this.listener = listener;
        this.jsRunner = jsRunner;
        this.prefs = activity.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    public int versionCode() {
        try {
            PackageInfo info = activity.getPackageManager().getPackageInfo(activity.getPackageName(), 0);
            return (int) (Build.VERSION.SDK_INT >= 28 ? info.getLongVersionCode() : info.versionCode);
        } catch (Exception e) {
            return 0;
        }
    }

    public String versionName() {
        try {
            return activity.getPackageManager().getPackageInfo(activity.getPackageName(), 0).versionName;
        } catch (Exception e) {
            return "?";
        }
    }

    /** Dipanggil otomatis saat app dibuka - diam-diam kalau tidak ada update / gagal. */
    public void checkAuto() {
        long now = System.currentTimeMillis();
        if (now - prefs.getLong(KEY_LAST_CHECK, 0) < AUTO_CHECK_INTERVAL_MS) return;
        check(false);
    }

    /** Dari tombol "Cek Pembaruan" - selalu kasih hasil ke pengguna. */
    public void checkManual() {
        check(true);
    }

    private void check(final boolean manual) {
        if (busy) return;
        busy = true;
        if (manual) status("Memeriksa pembaruan...");
        new Thread(() -> {
            try {
                Info info = fetchManifest();
                prefs.edit().putLong(KEY_LAST_CHECK, System.currentTimeMillis()).apply();
                int current = versionCode();
                if (info.versionCode <= current) {
                    if (manual) status("Aplikasi sudah versi terbaru (" + versionName() + ").");
                    return;
                }
                if (!manual && !info.mandatory && isSkipped(info)) return;
                status("Versi " + info.versionName + " tersedia.");
                activity.runOnUiThread(() -> presentUpdate(info));
            } catch (Exception e) {
                if (manual) status("Gagal memeriksa pembaruan. Pastikan HP terhubung ke internet.");
            } finally {
                busy = false;
            }
        }, "update-check").start();
    }

    private boolean isSkipped(Info info) {
        return prefs.getInt(KEY_SKIP_VERSION, 0) == info.versionCode
                && System.currentTimeMillis() < prefs.getLong(KEY_SKIP_UNTIL, 0);
    }

    private Info fetchManifest() throws Exception {
        HttpURLConnection conn = (HttpURLConnection) new URL(BuildConfig.UPDATE_MANIFEST_URL).openConnection();
        conn.setConnectTimeout(8000);
        conn.setReadTimeout(8000);
        conn.setUseCaches(false);
        try (InputStream in = conn.getInputStream()) {
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            byte[] buf = new byte[4096];
            int n;
            while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
            JSONObject json = new JSONObject(out.toString("UTF-8"));
            Info info = new Info();
            info.versionCode = json.getInt("versionCode");
            info.versionName = json.optString("versionName", String.valueOf(info.versionCode));
            info.apkUrl = json.getString("apkUrl");
            info.sha256 = json.getString("sha256").trim().toLowerCase();
            info.notes = json.optString("notes", "");
            info.mandatory = json.optBoolean("mandatory", false)
                    || versionCode() < json.optInt("minSupportedVersionCode", 0);
            return info;
        } finally {
            conn.disconnect();
        }
    }

    private void js(String script) {
        if (jsRunner != null) jsRunner.eval(script, null);
    }

    /** Tampilkan pop-up update di halaman (ikut tema/bahasa aplikasi). Kalau halaman
     *  yang sedang terbuka tidak punya komponennya (mis. halaman aktivasi), pakai dialog Android. */
    private void presentUpdate(final Info info) {
        pendingInfo = info;
        if (jsRunner == null) {
            showUpdateDialog(info);
            return;
        }
        final String payload;
        try {
            payload = new JSONObject().put("current", versionName()).put("next", info.versionName)
                    .put("notes", info.notes).put("mandatory", info.mandatory).toString();
        } catch (Exception e) {
            showUpdateDialog(info);
            return;
        }
        jsRunner.eval("(typeof window.__oruShowUpdate==='function') ? (window.__oruShowUpdate(" + payload
                + "), true) : false", result -> {
            if (!"true".equals(result)) showUpdateDialog(info);
        });
    }

    /** Tombol "Perbarui" di pop-up halaman. */
    public void startPendingUpdate() {
        final Info info = pendingInfo;
        if (info != null) activity.runOnUiThread(() -> download(info, true));
    }

    /** Tombol "Nanti" di pop-up halaman. */
    public void skipPendingUpdate() {
        if (pendingInfo != null) rememberSkip(pendingInfo);
    }

    private void rememberSkip(Info info) {
        prefs.edit()
                .putInt(KEY_SKIP_VERSION, info.versionCode)
                .putLong(KEY_SKIP_UNTIL, System.currentTimeMillis() + SKIP_DURATION_MS)
                .apply();
    }

    private void showUpdateDialog(final Info info) {
        if (activity.isFinishing()) return;
        String message = "Versi terpasang: " + versionName() + "\nVersi baru: " + info.versionName
                + (info.notes.isEmpty() ? "" : "\n\n" + info.notes)
                + "\n\nData toko Anda tetap aman.";
        AlertDialog.Builder builder = new AlertDialog.Builder(activity, R.style.OruGoAlertDialog)
                .setTitle("Pembaruan tersedia")
                .setMessage(message)
                .setCancelable(!info.mandatory)
                .setPositiveButton("Perbarui", (d, w) -> download(info, false));
        if (!info.mandatory) {
            builder.setNegativeButton("Nanti", (d, w) -> rememberSkip(info));
        }
        builder.show();
    }

    private void download(final Info info, final boolean web) {
        final ProgressBar bar = new ProgressBar(activity, null, android.R.attr.progressBarStyleHorizontal);
        bar.setMax(100);
        final AlertDialog progress = new AlertDialog.Builder(activity, R.style.OruGoAlertDialog)
                .setTitle("Mengunduh pembaruan...")
                .setView(bar)
                .setCancelable(false)
                .create();
        if (!web) progress.show();

        new Thread(() -> {
            File dir = new File(activity.getCacheDir(), "update");
            File target = new File(dir, "oru-go-update.apk");
            try {
                if (!dir.exists() && !dir.mkdirs()) throw new Exception("folder unduhan tidak bisa dibuat");
                if (target.exists()) target.delete();

                HttpURLConnection conn = (HttpURLConnection) new URL(info.apkUrl).openConnection();
                conn.setConnectTimeout(15000);
                conn.setReadTimeout(30000);
                long total = conn.getContentLengthLong();
                MessageDigest digest = MessageDigest.getInstance("SHA-256");
                try (InputStream in = conn.getInputStream(); OutputStream out = new FileOutputStream(target)) {
                    byte[] buf = new byte[65536];
                    long done = 0;
                    int lastPct = -1;
                    int n;
                    while ((n = in.read(buf)) > 0) {
                        out.write(buf, 0, n);
                        digest.update(buf, 0, n);
                        done += n;
                        if (total > 0) {
                            final int pct = (int) (done * 100 / total);
                            if (pct != lastPct) {
                                lastPct = pct;
                                activity.runOnUiThread(() -> {
                                    bar.setProgress(pct);
                                    if (web) js("window.__oruUpdateProgress&&window.__oruUpdateProgress(" + pct + ")");
                                });
                            }
                        }
                    }
                } finally {
                    conn.disconnect();
                }

                StringBuilder hex = new StringBuilder();
                for (byte b : digest.digest()) hex.append(String.format("%02x", b));
                if (!hex.toString().equals(info.sha256)) {
                    target.delete();
                    throw new Exception("checksum tidak cocok");
                }

                activity.runOnUiThread(() -> {
                    progress.dismiss();
                    if (web) js("window.__oruUpdateClose&&window.__oruUpdateClose()");
                    install(target);
                });
            } catch (Exception e) {
                target.delete();
                final String reason = e.getMessage() == null ? "unduhan gagal" : e.getMessage();
                activity.runOnUiThread(() -> {
                    progress.dismiss();
                    if (web) {
                        js("window.__oruUpdateFailed&&window.__oruUpdateFailed(" + JSONObject.quote(reason) + ")");
                    } else {
                        Toast.makeText(activity, "Pembaruan gagal: " + reason, Toast.LENGTH_LONG).show();
                    }
                });
                status("Pembaruan gagal: " + reason);
            }
        }, "update-download").start();
    }

    private void install(File apk) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
                && !activity.getPackageManager().canRequestPackageInstalls()) {
            // Android minta izin "pasang dari sumber ini" sekali saja per app.
            pendingInstall = apk;
            Toast.makeText(activity, "Izinkan aplikasi ini memasang pembaruan, lalu kembali.", Toast.LENGTH_LONG).show();
            Intent settings = new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                    Uri.parse("package:" + activity.getPackageName()));
            activity.startActivity(settings);
            return;
        }
        Uri uri = FileProvider.getUriForFile(activity, activity.getPackageName() + ".fileprovider", apk);
        Intent intent = new Intent(Intent.ACTION_VIEW)
                .setDataAndType(uri, "application/vnd.android.package-archive")
                .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK);
        activity.startActivity(intent);
    }

    /** Dipanggil dari onResume: lanjutkan pemasangan setelah pengguna mengizinkan. */
    public void resumePendingInstall() {
        if (pendingInstall == null) return;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
                && !activity.getPackageManager().canRequestPackageInstalls()) return;
        File apk = pendingInstall;
        pendingInstall = null;
        if (apk.exists()) install(apk);
    }

    private void status(String message) {
        if (listener != null) listener.onStatus(message);
    }
}
