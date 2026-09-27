package id.orulabs.umkm;

import android.Manifest;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import androidx.appcompat.app.AppCompatActivity;
import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;

import com.chaquo.python.PyObject;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;

/**
 * Purwarupa tahap 1 - jalankan Flask langsung di dalam proses HP lewat
 * Chaquopy (Python asli, bukan cuma binding), lalu WebView buka
 * 127.0.0.1 seperti biasa. Tidak butuh PC/mini PC/jaringan sama sekali.
 */
public class MainActivity extends AppCompatActivity {

    private static final int PORT = 5000;
    private WebView webView;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        requestBluetoothPermissionIfNeeded();

        webView = findViewById(R.id.webView);
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        webView.setWebViewClient(new WebViewClient() {
            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                super.onReceivedError(view, request, error);
                // Flask di thread lain butuh waktu buat mulai listen (apalagi
                // kalau ini pertama kali app dibuka - Chaquopy masih bongkar
                // paket Python-nya dulu) - bukan error permanen, coba lagi
                // saja sampai berhasil, bukan cuma delay tetap yang bisa
                // meleset.
                if (request.isForMainFrame()) {
                    new Handler(Looper.getMainLooper()).postDelayed(
                            () -> webView.loadUrl("http://127.0.0.1:" + PORT + "/"),
                            500
                    );
                }
            }
        });

        if (!Python.isStarted()) {
            Python.start(new AndroidPlatform(this));
        }

        String filesDir = getFilesDir().getAbsolutePath();

        // Flask app.run() itu blocking (jalan selamanya) - wajib di
        // thread terpisah, bukan di thread utama UI.
        new Thread(() -> {
            Python py = Python.getInstance();
            PyObject module = py.getModule("umkm_app");
            module.callAttr("run", PORT, filesDir);
        }, "flask-server").start();

        webView.loadUrl("http://127.0.0.1:" + PORT + "/");
    }

    /** BLUETOOTH_CONNECT (Android 12+/API 31+) wajib diminta di runtime,
     * bukan cuma dideklarasikan di manifest - tanpa ini, cetak struk
     * lewat printer Bluetooth (lihat android_bluetooth_printer.py) akan
     * gagal dengan SecurityException begitu owner memilih printer dari
     * Pengaturan. Versi Android lebih lama (permission-nya level
     * "normal") otomatis diberikan cukup lewat manifest saja. */
    private void requestBluetoothPermissionIfNeeded() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S) {
            return;
        }
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.BLUETOOTH_CONNECT)
                != PackageManager.PERMISSION_GRANTED) {
            ActivityCompat.requestPermissions(
                    this, new String[]{Manifest.permission.BLUETOOTH_CONNECT}, 1
            );
        }
    }
}
