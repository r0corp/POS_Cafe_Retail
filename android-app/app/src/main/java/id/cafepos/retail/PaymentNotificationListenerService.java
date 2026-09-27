package id.cafepos.retail;

import android.app.Notification;
import android.os.Bundle;
import android.service.notification.NotificationListenerService;
import android.service.notification.StatusBarNotification;
import android.util.Log;

import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

/**
 * "Dengar" notifikasi asli app BCA Merchant di tablet kasir ini, teruskan
 * teksnya ke server mini PC (endpoint /api/payment-notification) supaya
 * bisa dibunyikan sebagai notifikasi "uang QRIS masuk" di semua layar POS
 * - lihat komentar _parse_qris_amount() di app/blueprints/staff.py buat
 * alasan kenapa PARSING nominalnya sengaja dilakukan di server (Python),
 * bukan di sini: supaya kalau polanya ternyata meleset dari notifikasi
 * BCA Merchant yang sesungguhnya, cukup diperbaiki di server (deploy
 * ulang), TIDAK perlu bongkar/build ulang APK ini lagi.
 *
 * Servis ini SENGAJA tidak melakukan apa-apa (no-op, tidak nge-crash)
 * kalau payment_notify_token belum diisi di strings.xml - lihat
 * R.string.payment_notify_token.
 */
public class PaymentNotificationListenerService extends NotificationListenerService {

    private static final String TAG = "PaymentNotifListener";

    // Nama paket resmi app "Merchant BCA: QRIS & EDC" di Play Store.
    private static final String BCA_MERCHANT_PACKAGE = "com.bca.msb";

    @Override
    public void onNotificationPosted(StatusBarNotification sbn) {
        if (!BCA_MERCHANT_PACKAGE.equals(sbn.getPackageName())) return;

        String rawText = extractText(sbn);
        if (rawText == null || rawText.trim().isEmpty()) return;

        String serverUrl = getString(R.string.server_url);
        String token = getString(R.string.payment_notify_token);
        if (token == null || token.isEmpty() || "REPLACE_WITH_REAL_TOKEN".equals(token)) {
            Log.w(TAG, "payment_notify_token belum diisi - notifikasi BCA Merchant diabaikan: " + rawText);
            return;
        }

        forwardToServer(serverUrl, token, rawText);
    }

    /** Gabungkan judul + isi (termasuk bigText kalau ada, buat notifikasi
     * yang teksnya dipanjangkan/expand) supaya pola "Rp..." di server
     * punya peluang terbaik ketemu, apa pun bentuk notifikasi BCA
     * Merchant yang sebenarnya nanti (belum ada contoh resminya). */
    private String extractText(StatusBarNotification sbn) {
        Notification notification = sbn.getNotification();
        if (notification == null) return null;

        Bundle extras = notification.extras;
        if (extras == null) return null;

        StringBuilder sb = new StringBuilder();
        CharSequence title = extras.getCharSequence(Notification.EXTRA_TITLE);
        CharSequence text = extras.getCharSequence(Notification.EXTRA_TEXT);
        CharSequence bigText = extras.getCharSequence(Notification.EXTRA_BIG_TEXT);

        if (title != null) sb.append(title).append(" ");
        if (bigText != null) {
            sb.append(bigText);
        } else if (text != null) {
            sb.append(text);
        }

        return sb.toString();
    }

    private void forwardToServer(String serverUrl, String token, String rawText) {
        new Thread(() -> {
            try {
                URL url = new URL(serverUrl + "/api/payment-notification");
                HttpURLConnection conn = (HttpURLConnection) url.openConnection();
                conn.setRequestMethod("POST");
                conn.setRequestProperty("Content-Type", "application/json; charset=utf-8");
                conn.setRequestProperty("X-Payment-Token", token);
                conn.setConnectTimeout(5000);
                conn.setReadTimeout(5000);
                conn.setDoOutput(true);

                String escaped = rawText.replace("\\", "\\\\").replace("\"", "\\\"")
                        .replace("\n", "\\n").replace("\r", "");
                byte[] body = ("{\"raw_text\":\"" + escaped + "\"}").getBytes(StandardCharsets.UTF_8);

                try (OutputStream os = conn.getOutputStream()) {
                    os.write(body);
                }

                int code = conn.getResponseCode();
                if (code != 200) {
                    Log.w(TAG, "Server menolak notifikasi pembayaran, HTTP " + code);
                }
                conn.disconnect();
            } catch (Exception e) {
                // Jaringan lagi putus/server mati dll - jangan sampai bikin
                // listener service ini crash, notifikasi berikutnya masih
                // harus tetap dicoba diteruskan.
                Log.w(TAG, "Gagal kirim notifikasi pembayaran ke server", e);
            }
        }).start();
    }
}
