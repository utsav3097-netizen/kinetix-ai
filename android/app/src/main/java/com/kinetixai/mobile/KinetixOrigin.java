package com.kinetixai.mobile;

import java.net.URI;
import java.net.URISyntaxException;
import java.util.Locale;

/** Restricts the app WebView and its links to the configured HTTPS Render origin. */
public final class KinetixOrigin {
    private final String host;
    private final int port;
    private final String baseUrl;

    public KinetixOrigin(String configuredUrl) {
        URI uri = parse(configuredUrl);
        if (!"https".equals(uri.getScheme()) || uri.getHost() == null || uri.getUserInfo() != null
                || uri.getQuery() != null || uri.getFragment() != null
                || !(uri.getPath().isEmpty() || "/".equals(uri.getPath()))
                || !(uri.getPort() == -1 || uri.getPort() == 443)) {
            throw new IllegalArgumentException("The KINETIX URL must be an HTTPS origin.");
        }
        this.host = uri.getHost().toLowerCase(Locale.ROOT);
        if (!host.endsWith(".onrender.com")) {
            throw new IllegalArgumentException("The KINETIX URL must use the deployed Render hostname.");
        }
        this.port = 443;
        this.baseUrl = "https://" + host;
    }

    public boolean allows(String candidateUrl) {
        URI candidate;
        try {
            candidate = parse(candidateUrl);
        } catch (IllegalArgumentException exception) {
            return false;
        }
        int candidatePort = candidate.getPort() == -1 ? 443 : candidate.getPort();
        return "https".equals(candidate.getScheme())
                && candidate.getUserInfo() == null
                && host.equalsIgnoreCase(candidate.getHost())
                && candidatePort == port;
    }

    public String baseUrl() {
        return baseUrl;
    }

    private static URI parse(String value) {
        try {
            return new URI(value);
        } catch (URISyntaxException | NullPointerException exception) {
            throw new IllegalArgumentException("Invalid KINETIX URL.", exception);
        }
    }
}
