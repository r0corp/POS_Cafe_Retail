package id.orulabs.opsdashboard;

import android.content.Intent;
import android.net.Uri;
import android.net.http.SslError;
import android.os.Bundle;
import android.view.View;
import android.webkit.CookieManager;
import android.webkit.SslErrorHandler;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.JsResult;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.Toast;

import androidx.activity.OnBackPressedCallback;
import androidx.appcompat.app.AlertDialog;
import androidx.appcompat.app.AppCompatActivity;
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout;

/*
 * Catatan soal "gabung dengan Tailscale jadi 1 aplikasi": TIDAK bisa
 * secara teknis - Tailscale itu aplikasi VPN pihak ketiga (pakai
 * VpnService Android-nya sendiri, bukan library yang bisa ditempel ke
 * APK lain). Yang bisa dilakukan cuma mempermudah lompat ke sana lewat
 * tombol di layar offline (lihat openTailscale() di bawah) - solusi
 * yang lebih permanen sebenarnya fitur "Always-on VPN" bawaan Tailscale
 * sendiri di Pengaturan Android, supaya Tailscale otomatis nyala tanpa
 * perlu dibuka manual sama sekali.
 */

/**
 * Wrapper WebView sederhana buat Dashboard Kontrol Deploy (ops/dashboard.html)
 * - supaya bisa dibuka dari HP kayak aplikasi Android biasa, tanpa perlu
 * ketik alamat/port tiap kali lewat browser. Login-nya pakai sesi cookie
 * (lihat ops/dashboard_server.py) - CookieManager WAJIB diaktifkan supaya
 * sesi itu tersimpan antar-buka-app, sama seperti browser biasa.
 */
public class MainActivity extends AppCompatActivity {

    private WebView webView;
    private WebView offlineWebView;
    private SwipeRefreshLayout swipeRefresh;
    private FrameLayout offlineLayout;

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
        Button openTailscaleButton = findViewById(R.id.openTailscaleButton);

        offlineWebView.getSettings().setAllowFileAccess(true);
        offlineWebView.getSettings().setJavaScriptEnabled(true);
        offlineWebView.loadUrl("file:///android_asset/offline.html");

        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(webView, true);

        setupWebView();

        swipeRefresh.setOnRefreshListener(() -> webView.reload());

        retryButton.setOnClickListener(v -> {
            offlineLayout.setVisibility(View.GONE);
            webView.setVisibility(View.VISIBLE);
            webView.loadUrl(serverUrl);
        });

        openTailscaleButton.setOnClickListener(v -> openTailscale());

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

    private void setupWebView() {
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
                view.loadUrl(request.getUrl().toString());
                return true;
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                super.onPageFinished(view, url);
                swipeRefresh.setRefreshing(false);
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                super.onReceivedError(view, request, error);
                if (request.isForMainFrame()) {
                    // Gagal koneksi (Tailscale di HP mati, laptop kontrol
                    // mati/tidur, dst) - tidak ada kode HTTP sama sekali.
                    showOffline(null);
                }
            }

            @Override
            public void onReceivedHttpError(WebView view, WebResourceRequest request, WebResourceResponse errorResponse) {
                super.onReceivedHttpError(view, request, errorResponse);
                if (request.isForMainFrame()) {
                    showOffline(errorResponse.getStatusCode());
                }
            }

            @Override
            public void onReceivedSslError(WebView view, SslErrorHandler handler, SslError error) {
                handler.cancel();
                showOffline(null);
            }
        });

        // WebView diam-diam mengabaikan alert()/confirm() JS kalau tidak
        // dikasih WebChromeClient - confirm() langsung dianggap "Batal"
        // tanpa dialog apa pun. Dashboard pakai confirm() buat konfirmasi
        // Update/Rollback (supaya tidak ke-restart aplikasi POS tanpa
        // sengaja), jadi ini WAJIB ada.
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
    }

    private static final String TAILSCALE_PACKAGE = "com.tailscale.ipn";

    /** Buka app Tailscale langsung ke layar utamanya (kalau sudah
     * terpasang), atau ke listing Play Store-nya (kalau belum) - dipanggil
     * dari tombol "Buka Tailscale" di layar offline. Tidak bisa membuat
     * Tailscale otomatis nyambung tanpa disentuh sama sekali (itu perlu
     * diaktifkan sendiri lewat fitur "Always-on VPN" Tailscale di
     * Pengaturan Android), tapi setidaknya user tidak perlu cari-cari
     * ikonnya sendiri di antara semua app di HP. */
    private void openTailscale() {
        Intent launchIntent = getPackageManager().getLaunchIntentForPackage(TAILSCALE_PACKAGE);
        if (launchIntent != null) {
            startActivity(launchIntent);
            return;
        }

        Toast.makeText(this, getString(R.string.tailscale_not_installed), Toast.LENGTH_LONG).show();
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse("market://details?id=" + TAILSCALE_PACKAGE)));
        } catch (Exception e) {
            startActivity(new Intent(Intent.ACTION_VIEW,
                    Uri.parse("https://play.google.com/store/apps/details?id=" + TAILSCALE_PACKAGE)));
        }
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
}
