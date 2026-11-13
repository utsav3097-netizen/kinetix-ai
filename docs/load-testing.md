# Render staging capacity test

Use a dedicated, fully onboarded staging athlete with no real production records. Run from the repository root:

```sh
k6 run -e BASE_URL=https://YOUR-RENDER-HTTPS-ORIGIN -e LOAD_TEST_EMAIL=athlete@example.test -e LOAD_TEST_PASSWORD='your-secret' backend/load/k6_staging.js
```

The test logs in once, shares the short-lived bearer token, ramps to 500 VUs over two minutes, holds ten minutes, then ramps down. Each VU performs read-only requests to `/`, `/api/v1/profile`, and `/api/v1/dashboard/targets`; AI-provider calls and repeated logins are excluded.

Accept only when `http_req_failed` is below 1%, authenticated API p95 is below 2 seconds, and Render's web and PostgreSQL metrics show headroom. Do not run this load against a production database. Record the Render plans, instance counts, database connections, and observed latencies with the result; the target is not guaranteed independently of the measured bottleneck.
