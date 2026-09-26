package id.cafepos.retail;

import android.content.Context;
import android.net.Uri;
import android.net.http.SslError;
import android.os.Bundle;
import android.print.PrintAttributes;
import android.print.PrintDocumentAdapter;
import android.print.PrintManager;
import android.view.View;
import android.webkit.JavascriptInterface;
import android.webkit.SslErrorHandler;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.Toast;

import androidx.activity.OnBackPressedCallback;
import androidx.activity.result.ActivityResultLauncher;
import androidx.activity.result.contract.ActivityResultContracts;
import androidx.appcompat.app.AppCompatActivity;
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout;

/**
 * Wrapper WebView sederhana yang selalu membuka alamat server toko
 * (kasir/dapur/pelayan pakai app ini seperti aplikasi Android biasa,
 * jadi tidak akan "hilang" seperti shortcut PWA yang bisa kehapus
 * tanpa sengaja).
 */
public class MainActivity extends AppCompatActivity {

    private WebView webView;
    private WebView offlineWebView;
    private SwipeRefreshLayout swipeRefresh;
    private FrameLayout offlineLayout;
    private ValueCallback<Uri[]> filePathCallback;
    private ActivityResultLauncher<String> fileChooserLauncher;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        String serverUrl = getString(R.string.server_url);

        webView = findViewById(R.id.webView);
        offlineWebView = findViewById(R.id.offlineWebView);
        swipeRefresh = findViewById(R.id.swipeRefresh);
        offlineLayout = findViewById(R.id.offlineLayout);
        Button retryButton = findViewById(R.id.retryButton);

        // Animasi "Logo Melayang + Sinyal" dimuat sekali dari file lokal
        // (bukan dari server) supaya tetap tampil walau benar-benar offline.
        // JS dinyalakan supaya showOffline() bisa kirim kode error (404,
        // 500, dst) ke halaman ini lewat evaluateJavascript() tanpa perlu
        // reload ulang tiap kali errornya beda.
        offlineWebView.getSettings().setAllowFileAccess(true);
        offlineWebView.getSettings().setJavaScriptEnabled(true);
        offlineWebView.loadUrl("file:///android_asset/offline.html");

        fileChooserLauncher = registerForActivityResult(
                new ActivityResultContracts.GetContent(),
                uri -> {
                    if (filePathCallback == null) return;
                    filePathCallback.onReceiveValue(uri == null ? null : new Uri[]{uri});
                    filePathCallback = null;
                }
        );

        setupWebView(serverUrl);

        swipeRefresh.setOnRefreshListener(() -> webView.reload());

        retryButton.setOnClickListener(v -> {
            offlineLayout.setVisibility(View.GONE);
            webView.setVisibility(View.VISIBLE);
            webView.loadUrl(serverUrl);
        });

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

        webView.loadUrl(serverUrl);
    }

    private void setupWebView(String serverUrl) {
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);
        settings.setLoadWithOverviewMode(true);
        settings.setUseWideViewPort(true);
        settings.setSupportZoom(false);
        settings.setCacheMode(WebSettings.LOAD_DEFAULT);

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                // Semua link tetap dibuka di dalam app ini, bukan browser luar,
                // selama masih di server yang sama.
                view.loadUrl(request.getUrl().toString());
                return true;
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                super.onPageFinished(view, url);
                swipeRefresh.setRefreshing(false);

                // WebView bawaan TIDAK mengimplementasikan window.print() -
                // manggilnya diam-diam tidak melakukan apa-apa (beda dengan
                // browser Chrome biasa yang munculkan dialog print). Timpa
                // di tiap halaman baru supaya tombol "Cetak Struk" (yang
                // pakai onclick="window.print()") lempar ke printCurrentPage()
                // lewat jembatan AndroidPrint di bawah.
                view.evaluateJavascript(
                        "if (window.AndroidPrint) { window.print = function () { window.AndroidPrint.requestPrint(); }; }",
                        null
                );
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                super.onReceivedError(view, request, error);
                if (request.isForMainFrame()) {
                    // Gagal koneksi (tidak ada internet, DNS gagal, timeout, dst) -
                    // tidak ada kode HTTP karena server sama sekali tidak terjangkau.
                    showOffline(null);
                }
            }

            @Override
            public void onReceivedHttpError(WebView view, WebResourceRequest request, WebResourceResponse errorResponse) {
                super.onReceivedHttpError(view, request, errorResponse);
                if (request.isForMainFrame()) {
                    // Server TERJANGKAU tapi balas status error (404, 500, dst) -
                    // kode statusnya ditampilkan gede di halaman animasi yang sama.
                    showOffline(errorResponse.getStatusCode());
                }
            }

            @Override
            public void onReceivedSslError(WebView view, SslErrorHandler handler, SslError error) {
                handler.cancel();
                showOffline(null);
            }
        });

        // Jembatan supaya window.print() (ditimpa di onPageFinished di atas)
        // bisa manggil PrintManager Android yang sesungguhnya - lihat
        // printCurrentPage() & PrintBridge di bawah.
        webView.addJavascriptInterface(new PrintBridge(), "AndroidPrint");

        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView webView, ValueCallback<Uri[]> callback,
                                              FileChooserParams params) {
                // Dipakai untuk semua fitur upload foto di aplikasi (foto menu,
                // avatar, logo, QRIS) supaya bisa pilih file dari galeri/kamera.
                //
                // PENTING: acceptTypes[0] TIDAK SELALU berupa MIME type yang
                // valid ("image/png") - beberapa <input accept="..."> di web
                // ini masih pakai daftar ekstensi (".png,.jpg,...") yang lolos
                // baik-baik saja di browser biasa, tapi kalau string mentah
                // semacam ".png" itu langsung dipakai sebagai Intent.setType()
                // di Android, sistem tidak akan nemu activity manapun yang
                // cocok -> ActivityNotFoundException -> APLIKASI FORCE CLOSE.
                // Makanya di-validasi dulu wujudnya "tipe/subtipe" (ada "/"),
                // dan seluruh launch()-nya dibungkus try/catch supaya walau
                // ada accept value aneh lainnya di masa depan, aplikasi cuma
                // gagal buka pemilih file (dengan pesan Toast), bukan crash.
                filePathCallback = callback;
                String[] acceptTypes = params.getAcceptTypes();
                String rawType = (acceptTypes != null && acceptTypes.length > 0) ? acceptTypes[0] : "";
                String mimeType = (!rawType.isEmpty() && rawType.contains("/")) ? rawType : "image/*";

                try {
                    fileChooserLauncher.launch(mimeType);
                } catch (Exception e) {
                    filePathCallback = null;
                    Toast.makeText(MainActivity.this,
                            getString(R.string.file_chooser_error), Toast.LENGTH_SHORT).show();
                }
                return true;
            }
        });
    }

    private void showOffline(Integer httpErrorCode) {
        swipeRefresh.setRefreshing(false);
        offlineLayout.setVisibility(View.VISIBLE);
        webView.setVisibility(View.GONE);
        offlineWebView.evaluateJavascript(
                "setErrorCode(" + (httpErrorCode != null ? httpErrorCode : "null") + ");",
                null
        );
    }

    /** Buka dialog Cetak Android bawaan untuk konten WebView saat ini
     * (dipanggil dari halaman struk lewat window.print(), lihat
     * onPageFinished & PrintBridge). Dialog ini menampilkan Print Service
     * apa pun yang sudah terpasang di tablet/HP kasir - kalau printer
     * thermal-nya belum ada driver Print Service (banyak printer thermal
     * murah cuma dijual dengan app cetak sendiri, bukan Print Service
     * resmi Android), pilihan "Simpan sebagai PDF" tetap selalu ada. */
    private void printCurrentPage() {
        PrintManager printManager = (PrintManager) getSystemService(Context.PRINT_SERVICE);
        if (printManager == null) {
            Toast.makeText(this, getString(R.string.print_unavailable_error), Toast.LENGTH_SHORT).show();
            return;
        }
        String jobName = getString(R.string.app_name) + " - Struk";
        PrintDocumentAdapter adapter = webView.createPrintDocumentAdapter(jobName);
        printManager.print(jobName, adapter, new PrintAttributes.Builder().build());
    }

    private class PrintBridge {
        @JavascriptInterface
        public void requestPrint() {
            runOnUiThread(MainActivity.this::printCurrentPage);
        }
    }
}
