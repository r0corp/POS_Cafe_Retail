package id.orulabs.umkm;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.net.wifi.WifiManager;
import android.os.Build;
import android.os.IBinder;
import android.os.PowerManager;

/**
 * Edisi Cafe: tablet/HP kasir adalah SERVER untuk tablet dapur dan kasir lain di WiFi toko. Tanpa layanan ini
 * Android membekukan proses aplikasi begitu layar mati atau aplikasi ke latar belakang, dan tablet lain terputus
 * (terbukti di emulator: server berhenti menjawab ~1 menit setelah layar mati).
 *
 * Layanan latar depan (notifikasi tetap) + PARTIAL_WAKE_LOCK + WifiLock menjaga server tetap melayani. Server
 * Flask-nya sendiri tetap dijalankan MainActivity; layanan ini hanya menjaga proses tetap hidup.
 */
public class ServerService extends Service {

    private static final String CHANNEL_ID = "server";
    private static final int NOTIFICATION_ID = 1;

    private PowerManager.WakeLock wakeLock;
    private WifiManager.WifiLock wifiLock;

    @Override
    public void onCreate() {
        super.onCreate();
        createChannel();
        Intent open = new Intent(this, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP);
        PendingIntent pending = PendingIntent.getActivity(this, 0, open, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        Notification.Builder builder = Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
                ? new Notification.Builder(this, CHANNEL_ID)
                : new Notification.Builder(this);
        Notification notification = builder
                .setContentTitle("Oru POS Cafe aktif")
                .setContentText("Melayani tablet lain di WiFi toko. Jangan tutup aplikasi ini.")
                .setSmallIcon(android.R.drawable.stat_notify_sync)
                .setContentIntent(pending)
                .setOngoing(true)
                .build();
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC);
        } else {
            startForeground(NOTIFICATION_ID, notification);
        }

        PowerManager power = (PowerManager) getSystemService(Context.POWER_SERVICE);
        if (power != null) {
            wakeLock = power.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "orucafe:server");
            wakeLock.setReferenceCounted(false);
            wakeLock.acquire();
        }
        WifiManager wifi = (WifiManager) getApplicationContext().getSystemService(Context.WIFI_SERVICE);
        if (wifi != null) {
            wifiLock = wifi.createWifiLock(Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q
                    ? WifiManager.WIFI_MODE_FULL_LOW_LATENCY : WifiManager.WIFI_MODE_FULL_HIGH_PERF, "orucafe:wifi");
            wifiLock.setReferenceCounted(false);
            wifiLock.acquire();
        }
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        return START_STICKY;
    }

    @Override
    public void onDestroy() {
        if (wakeLock != null && wakeLock.isHeld()) wakeLock.release();
        if (wifiLock != null && wifiLock.isHeld()) wifiLock.release();
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    private void createChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(CHANNEL_ID, "Server Cafe", NotificationManager.IMPORTANCE_LOW);
            channel.setDescription("Menjaga Oru POS Cafe tetap melayani tablet lain");
            NotificationManager manager = getSystemService(NotificationManager.class);
            if (manager != null) manager.createNotificationChannel(channel);
        }
    }
}
