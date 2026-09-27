package id.orulabs.umkm;

import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import androidx.appcompat.app.AppCompatActivity;

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
}
