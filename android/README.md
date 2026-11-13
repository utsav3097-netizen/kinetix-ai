# Android project

This project builds a small Android WebView wrapper; the deployed Render site remains the single application origin. Cookie-based login therefore stays first-party inside the WebView.

GitHub Actions builds with Java 17, Gradle 8.9, Android SDK 35, and `minSdk 24`. The APK build requires `KINETIX_PUBLIC_URL`, an HTTPS origin on `*.onrender.com`, and a positive `KINETIX_VERSION_CODE`. The CI workflow passes the Render URL entered in `app_url` and uses the workflow run number for APK versioning.

For a local build after installing Java, Gradle, and Android SDK 35:

```sh
gradle --no-daemon --project-dir android testDebugUnitTest assembleDebug \
  -PKINETIX_PUBLIC_URL=https://YOUR-RENDER-HTTPS-ORIGIN \
  -PKINETIX_VERSION_CODE=1
```

`KinetixOrigin` contains the WebView origin allowlist and has JVM unit tests. Do not enable arbitrary navigation, file access, mixed content, or third-party cookies to work around an invalid deployment URL.
