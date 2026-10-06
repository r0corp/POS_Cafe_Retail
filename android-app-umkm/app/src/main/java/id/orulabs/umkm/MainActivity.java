package id.orulabs.umkm;

import android.Manifest;
import android.app.DownloadManager;
import android.animation.ValueAnimator;
import android.content.pm.PackageManager;
import android.graphics.Bitmap;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.os.Handler;
import android.os.Looper;
import android.view.View;
import android.view.animation.AccelerateDecelerateInterpolator;
import android.webkit.CookieManager;
import android.webkit.JsResult;
import android.webkit.URLUtil;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;

import androidx.activity.OnBackPressedCallback;
import androidx.activity.result.ActivityResultLauncher;
import androidx.activity.result.contract.ActivityResultContracts;
import androidx.appcompat.app.AlertDialog;
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

    // Proses Android (dan thread-thread di dalamnya, termasuk server
    // Flask ini) bisa saja BERTAHAN HIDUP walau Activity-nya ditutup
    // (tombol Back/Home lalu dibuka lagi) - static, bukan field biasa,
    // supaya tetap "ingat" lintas onCreate() dan tidak coba nyalakan
    // server Flask kedua kali di port yang sama (nge-crash seluruh app
    // dengan "Address already in use" kalau dibiarkan).
    private static volatile boolean serverStarted = false;

    private WebView webView;
    private View splashOverlay;
    private ValueAnimator splashAnimator;
    private boolean pageLoadFailed = false;
    private ValueCallback<Uri[]> filePathCallback;
    private ActivityResultLauncher<String> fileChooserLauncher;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        requestBluetoothPermissionIfNeeded();

        fileChooserLauncher = registerForActivityResult(
                new ActivityResultContracts.GetContent(),
                uri -> {
                    if (filePathCallback == null) return;
                    filePathCallback.onReceiveValue(uri == null ? null : new Uri[]{uri});
                    filePathCallback = null;
                }
        );

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
        startSplashAnimation();
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
                // Flask di thread lain butuh waktu buat mulai listen (apalagi
                // kalau ini pertama kali app dibuka - Chaquopy masih bongkar
                // paket Python-nya dulu) - bukan error permanen, coba lagi
                // saja sampai berhasil, bukan cuma delay tetap yang bisa
                // meleset. splashOverlay (lihat activity_main.xml) tetap
                // nutupin WebView selama ini, jadi pengguna tidak pernah
                // lihat halaman error bawaan WebView berkedip sama sekali.
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
                // Baru sembunyikan splash kalau load-nya BENERAN sukses -
                // onPageFinished tetap kepanggil walau isinya halaman error
                // WebView, jadi wajib dicek pageLoadFailed dulu, bukan
                // langsung sembunyikan di sini.
                if (!pageLoadFailed) {
                    splashOverlay.setVisibility(View.GONE);
                    stopSplashAnimation();
                }
            }
        });

        // WebView polos diam-diam MENGABAIKAN alert()/confirm() JS tanpa
        // WebChromeClient - confirm() otomatis dianggap "Batal" tanpa
        // dialog apa pun. Beberapa halaman (mis. hapus kategori/foto di
        // Kelola Menu) pakai confirm() buat konfirmasi sebelum submit.
        // onShowFileChooser juga wajib ada di sini - tanpanya, input
        // upload foto menu/logo/profil sama sekali tidak bisa dipakai.
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

            @Override
            public boolean onShowFileChooser(WebView webView, ValueCallback<Uri[]> callback,
                                              FileChooserParams params) {
                filePathCallback = callback;
                String[] acceptTypes = params.getAcceptTypes();
                String rawType = (acceptTypes != null && acceptTypes.length > 0) ? acceptTypes[0] : "";
                String mimeType = (!rawType.isEmpty() && rawType.contains("/")) ? rawType : "image/*";

                try {
                    fileChooserLauncher.launch(mimeType);
                } catch (Exception e) {
                    filePathCallback = null;
                    Toast.makeText(MainActivity.this, "Tidak bisa membuka pemilih file.", Toast.LENGTH_SHORT).show();
                }
                return true;
            }
        });

        // File backup (.zip) yang dibuat lewat Pengaturan Toko - WebView
        // polos TIDAK bisa mengunduh file sama sekali (link dengan
        // Content-Disposition: attachment cuma diam saja tanpa listener
        // ini). Diarahkan ke folder Download HP lewat DownloadManager
        // supaya bisa dipindah ke Google Drive/HP baru dkk.
        webView.setDownloadListener((url, userAgent, contentDisposition, mimetype, contentLength) -> {
            String filename = URLUtil.guessFileName(url, contentDisposition, mimetype);
            DownloadManager.Request request = new DownloadManager.Request(Uri.parse(url));

            // DownloadManager jalan sebagai proses terpisah, tidak ikut
            // pakai cookie sesi login WebView secara otomatis - wajib
            // dioper manual, kalau tidak nanti yang ke-download malah
            // halaman login (backup_download butuh login Owner).
            String cookie = CookieManager.getInstance().getCookie(url);
            if (cookie != null) {
                request.addRequestHeader("Cookie", cookie);
            }

            request.setMimeType(mimetype);
            request.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
            request.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, filename);
            request.setTitle(filename);

            DownloadManager dm = (DownloadManager) getSystemService(DOWNLOAD_SERVICE);
            dm.enqueue(request);
            Toast.makeText(this, "Mengunduh " + filename + "...", Toast.LENGTH_SHORT).show();
        });

        if (!Python.isStarted()) {
            Python.start(new AndroidPlatform(this));
        }

        if (!serverStarted) {
            serverStarted = true;
            String filesDir = getFilesDir().getAbsolutePath();

            // Flask app.run() itu blocking (jalan selamanya) - wajib di
            // thread terpisah, bukan di thread utama UI.
            new Thread(() -> {
                try {
                    Python py = Python.getInstance();
                    PyObject module = py.getModule("umkm_app");
                    module.callAttr("run", PORT, filesDir);
                } catch (Throwable t) {
                    // Kalau server gagal jalan karena alasan APA PUN,
                    // biarkan WebView tetap coba reload seperti biasa
                    // (lihat onReceivedError) daripada nge-crash SELURUH
                    // proses app - exception di background thread yang
                    // dibiarkan lolos itu yang mematikan seluruh app,
                    // bukan cuma thread ini.
                    android.util.Log.e("MainActivity", "Flask server gagal jalan", t);
                }
            }, "flask-server").start();
        }

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

    /** Bar "LOADING..." yang geser terus - sama dengan loginLoaderSlide di
     *  style.css: dari -100% sampai 350% lebar bar (bar 40% dari track),
     *  1,1 detik, ease-in-out, ulang dari awal. */
    private void startSplashAnimation() {
        final View fill = findViewById(R.id.splashFill);
        if (fill == null) return;
        final float density = getResources().getDisplayMetrics().density;
        final float barWidth = 88f * density;
        splashAnimator = ValueAnimator.ofFloat(-barWidth, barWidth * 3.5f);
        splashAnimator.setDuration(1100);
        splashAnimator.setInterpolator(new AccelerateDecelerateInterpolator());
        splashAnimator.setRepeatCount(ValueAnimator.INFINITE);
        splashAnimator.setRepeatMode(ValueAnimator.RESTART);
        splashAnimator.addUpdateListener(a -> fill.setTranslationX((float) a.getAnimatedValue()));
        splashAnimator.start();
    }

    private void stopSplashAnimation() {
        if (splashAnimator != null) {
            splashAnimator.cancel();
            splashAnimator = null;
        }
    }

    @Override
    protected void onDestroy() {
        stopSplashAnimation();
        super.onDestroy();
    }
}
