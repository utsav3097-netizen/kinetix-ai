package com.kinetixai.mobile;

import android.content.ActivityNotFoundException;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebView;
import android.webkit.WebViewClient;

public final class KinetixWebViewClient extends WebViewClient {
    private final Context context;
    private final KinetixOrigin origin;
    private boolean showingOfflineMessage;

    public KinetixWebViewClient(Context context, KinetixOrigin origin) {
        this.context = context;
        this.origin = origin;
    }

    @Override
    public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
        Uri destination = request.getUrl();
        if (origin.allows(destination.toString())) {
            return false;
        }
        String scheme = destination.getScheme();
        if ("https".equals(scheme) || "mailto".equals(scheme) || "tel".equals(scheme)) {
            try {
                context.startActivity(new Intent(Intent.ACTION_VIEW, destination));
            } catch (ActivityNotFoundException ignored) {
                // Keep unsupported external schemes inside the app rather than crashing.
            }
        }
        return true;
    }

    @Override
    public void onPageStarted(WebView view, String url, android.graphics.Bitmap favicon) {
        if (origin.allows(url)) {
            showingOfflineMessage = false;
        }
    }

    @Override
    public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
        if (request.isForMainFrame() && !showingOfflineMessage) {
            showingOfflineMessage = true;
            view.loadDataWithBaseURL(
                    origin.baseUrl(),
                    "<!doctype html><html lang='en'><meta name='viewport' content='width=device-width,initial-scale=1'>"
                            + "<meta name='theme-color' content='#090a0f'><title>KINETIX AI — Offline</title>"
                            + "<style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#090a0f;color:#f4f5f7;font:16px system-ui,sans-serif}"
                            + "main{max-width:30rem;padding:2rem}h1{color:#74e0b2}</style>"
                            + "<main><h1>You’re offline</h1><p>Reconnect to load your KINETIX account. Athlete records are not stored for offline use.</p>"
                            + "<a style='color:#74e0b2' href='" + origin.baseUrl() + "'>Try again</a></main></html>",
                    "text/html",
                    "UTF-8",
                    null
            );
        }
    }
}
