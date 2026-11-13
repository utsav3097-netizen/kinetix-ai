package com.kinetixai.mobile;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;
import static org.junit.Assert.fail;

import org.junit.Test;

public final class KinetixOriginTest {
    @Test
    public void allowsOnlyTheConfiguredHttpsOrigin() {
        KinetixOrigin origin = new KinetixOrigin("https://kinetix-web.onrender.com");

        assertTrue(origin.allows("https://kinetix-web.onrender.com/login"));
        assertTrue(origin.allows("https://KINETIX-WEB.ONRENDER.COM/api/v1/auth/refresh"));
        assertFalse(origin.allows("http://kinetix-web.onrender.com/login"));
        assertFalse(origin.allows("https://attacker.onrender.com/login"));
        assertFalse(origin.allows("https://kinetix-web.onrender.com.evil.test/login"));
        assertFalse(origin.allows("https://user@kinetix-web.onrender.com/login"));
        assertFalse(origin.allows("https://kinetix-web.onrender.com:444/login"));
    }

    @Test
    public void configuredOriginMustBeAnOnrenderHttpsOrigin() {
        for (String invalid : new String[]{
                "http://kinetix-web.onrender.com",
                "https://example.com",
                "https://user@kinetix-web.onrender.com",
                "https://kinetix-web.onrender.com/app",
                "https://kinetix-web.onrender.com?next=other"
        }) {
            try {
                new KinetixOrigin(invalid);
                fail("Expected invalid origin to be rejected: " + invalid);
            } catch (IllegalArgumentException expected) {
                // Invalid APK origins are rejected before any WebView navigation.
            }
        }
    }
}
