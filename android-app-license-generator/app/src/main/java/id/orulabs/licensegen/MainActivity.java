package id.orulabs.licensegen;

import android.graphics.Bitmap;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.View;
import android.webkit.JavascriptInterface;
import android.webkit.JsResult;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import androidx.activity.OnBackPressedCallback;
import androidx.appcompat.app.AlertDialog;
import androidx.appcompat.app.AppCompatActivity;
import androidx.biometric.BiometricManager;
import androidx.biometric.BiometricPrompt;
import androidx.core.content.ContextCompat;

import com.chaquo.python.PyObject;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;

/**
 * App INTERNAL buat penjual sendiri - generate Kode Aktivasi APK UMKM
 * dari HP, tanpa perlu bawa laptop. Sama arsitekturnya dengan APK UMKM
 * (Python/Flask jalan lokal lewat Chaquopy, WebView buka 127.0.0.1),
 * tapi jauh lebih sederhana (tidak ada printer/backup/dst).
 */
public class MainActivity extends AppCompatActivity {

    private static final int PORT = 5001;

    private static volatile boolean serverStarted = false;

    private WebView webView;
    private View splashOverlay;
    private boolean pageLoadFailed = false;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        getOnBackPressedDispatcher().addCallback(this, new OnBackPressedCallback(true) {
            @Override
            public void handleOnBackPressed() {
                if (webView.canGoBack()) {
                    webView.goBack();
                } else {
                    setEnabled(false);
                    getOnBackPressedDispatcher().onBackPressed();
                }
            }
        });

        webView = findViewById(R.id.webView);
        splashOverlay = findViewById(R.id.splashOverlay);
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        webView.setWebViewClient(new WebViewClient() {
            @Override
            public void onPageStarted(WebView view, String url, Bitmap favicon) {
                super.onPageStarted(view, url, favicon);
                pageLoadFailed = false;
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                super.onReceivedError(view, request, error);
                // Flask di thread lain butuh waktu buat mulai listen -
                // bukan error permanen, coba lagi saja sampai berhasil.
                // splashOverlay tetap nutupin WebView selama ini.
                if (request.isForMainFrame()) {
                    pageLoadFailed = true;
                    new Handler(Looper.getMainLooper()).postDelayed(
                            () -> webView.loadUrl("http://127.0.0.1:" + PORT + "/"),
                            500
                    );
                }
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                super.onPageFinished(view, url);
                if (!pageLoadFailed) {
                    splashOverlay.setVisibility(View.GONE);
                }
            }
        });

        // WebChromeClient wajib ada supaya confirm()/alert() JS (dipakai
        // buat konfirmasi sebelum generate kode) tidak diam-diam
        // diabaikan oleh WebView polos.
        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onJsAlert(WebView view, String url, String message, JsResult result) {
                new AlertDialog.Builder(MainActivity.this)
                        .setMessage(message)
                        .setPositiveButton(android.R.string.ok, (dialog, which) -> result.confirm())
                        .setOnCancelListener(dialog -> result.cancel())
                        .setCancelable(false)
                        .show();
                return true;
            }

            @Override
            public boolean onJsConfirm(WebView view, String url, String message, JsResult result) {
                new AlertDialog.Builder(MainActivity.this)
                        .setMessage(message)
                        .setPositiveButton(android.R.string.ok, (dialog, which) -> result.confirm())
                        .setNegativeButton(android.R.string.cancel, (dialog, which) -> result.cancel())
                        .setOnCancelListener(dialog -> result.cancel())
                        .show();
                return true;
            }
        });

        webView.addJavascriptInterface(new AuthBridge(), "AndroidAuth");

        if (!Python.isStarted()) {
            Python.start(new AndroidPlatform(this));
        }

        if (!serverStarted) {
            serverStarted = true;
            String filesDir = getFilesDir().getAbsolutePath();

            new Thread(() -> {
                try {
                    Python py = Python.getInstance();
                    PyObject module = py.getModule("generator_app");
                    module.callAttr("run", PORT, filesDir);
                } catch (Throwable t) {
                    android.util.Log.e("MainActivity", "Flask server gagal jalan", t);
                }
            }, "flask-server").start();
        }

        webView.loadUrl("http://127.0.0.1:" + PORT + "/");
    }

    /** Dipanggil dari halaman login (lihat _LOGIN_PAGE di
     * generator_app.py) - sidik jari diverifikasi 100% NATIVE Android
     * (BiometricPrompt, dicocokkan ke sensor+data biometrik yang sudah
     * terdaftar di HP ini sendiri) SEBELUM WebView diarahkan ke endpoint
     * "sudah lolos" - Python sama sekali tidak pegang/lihat data
     * biometrik apa pun, cuma terima hasil akhirnya. Username+password
     * tetap ada sebagai cara masuk kalau sensor tidak tersedia/sidik
     * jari gagal dikenali. */
    private class AuthBridge {
        @JavascriptInterface
        public boolean isBiometricAvailable() {
            BiometricManager biometricManager = BiometricManager.from(MainActivity.this);
            return biometricManager.canAuthenticate(BiometricManager.Authenticators.BIOMETRIC_STRONG)
                    == BiometricManager.BIOMETRIC_SUCCESS;
        }

        @JavascriptInterface
        public void authenticate() {
            runOnUiThread(() -> {
                BiometricPrompt biometricPrompt = new BiometricPrompt(
                        MainActivity.this,
                        ContextCompat.getMainExecutor(MainActivity.this),
                        new BiometricPrompt.AuthenticationCallback() {
                            @Override
                            public void onAuthenticationSucceeded(BiometricPrompt.AuthenticationResult result) {
                                super.onAuthenticationSucceeded(result);
                                webView.loadUrl("http://127.0.0.1:" + PORT + "/biometric-unlock");
                            }
                        }
                );

                BiometricPrompt.PromptInfo promptInfo = new BiometricPrompt.PromptInfo.Builder()
                        .setTitle("Masuk Generator Lisensi")
                        .setSubtitle("Gunakan sidik jari yang terdaftar di HP ini")
                        .setNegativeButtonText("Batal")
                        .setAllowedAuthenticators(BiometricManager.Authenticators.BIOMETRIC_STRONG)
                        .build();

                biometricPrompt.authenticate(promptInfo);
            });
        }
    }
}
