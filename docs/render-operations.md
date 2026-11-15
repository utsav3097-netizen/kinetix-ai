# Free demo limitations

- The Free web service sleeps after 15 minutes of inactivity and can take about a minute to wake. Expect a cold start on the first phone launch after idle.
- The Free Postgres database is 1 GB, has no backups, expires after 30 days, and is deleted after a 14-day grace period unless upgraded. Export any data you need before expiration; do not store real athlete records.
- The Blueprint runs one web instance and the AI queue worker in that same process. It has no background worker service, pre-deploy hook, shell, or autoscaling on the Free tier.
- The pool cap is six connections for the single web process; migration runs before Uvicorn starts. Do not scale replicas without changing the worker topology and recalculating the connection budget.
- The free demo is not the 500-VU acceptance environment. Upgrade to paid web/Postgres/worker plans and a Pro workspace before a representative load test.

## Upgrade path

When moving to paid plans, provision a managed worker and run migrations through a pre-deploy command before the web rollout. Render Pro is required for the Blueprint's 2–10 web autoscaling. Confirm Postgres backup/PITR retention, test a restore, and verify the forwarded client IP and rate-limit behavior before onboarding real athletes.

For every APK build, use the currently deployed HTTPS hostname. A changed Render hostname requires building a new APK. The artifact is debug-signed; later CI builds may need uninstall/reinstall unless a stable private release keystore is configured.
