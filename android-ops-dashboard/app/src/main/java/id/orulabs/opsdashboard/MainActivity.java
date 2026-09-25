package id.orulabs.opsdashboard;

import android.net.http.SslError;
import android.os.Bundle;
import android.view.View;
import android.webkit.CookieManager;
import android.webkit.SslErrorHandler;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.FrameLayout;

import androidx.activity.OnBackPressedCallback;
import androidx.appcompat.app.AppCompatActivity;
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout;

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
