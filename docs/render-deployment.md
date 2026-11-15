# Temporary Render free demo

This Blueprint deploys KINETIX without AWS or a payment card. It uses one Free Render web service and one Free PostgreSQL database. This is a disposable demo, not production hosting:

- Render spins down a Free web service after 15 minutes without traffic; the next request can wait about a minute for startup.
- Free PostgreSQL is limited to 1 GB, has no backups, and expires 30 days after creation. After its 14-day upgrade grace period, Render deletes the database and its data.
- Free services cannot autoscale, run background-worker services, or use Render Shell/one-off jobs. The app runs its AI worker in the single web process.
- Do not enter real athlete records. The first registered account is a normal athlete; do not set `ADMIN_EMAIL` to grant admin without email verification.

## Deploy

1. Create a Render account and connect this GitHub repository.
2. Choose **New → Blueprint Instance**, select branch `feature/aws-android-scale`, and review `render.yaml`. It provisions only the Free web service and Free Postgres database, plus a generated JWT secret.
3. Wait for `/api/v1/health/live` to pass, then verify `/api/v1/health` reports database readiness. Copy the exact HTTPS origin from the Render dashboard.
4. The web startup script runs idempotent migrations and reference seeding before Uvicorn on every cold start. The single app process runs the queue worker. The private database connection remains in the Render environment; no database password goes in Git.
5. Optional provider keys can be set in Render's protected environment settings. Without them, core athlete records work and provider-backed AI features remain unavailable.

Uvicorn proxy-header handling is enabled for Render ingress so auth rate limits can use Render's forwarded client address. Do not add direct app ingress. Verify the forwarded client-IP behavior after deployment.

For a stable app without cold starts or database expiry, upgrade the web/database plans and use a paid worker service. The current free Blueprint does not meet the separate-worker, autoscaling, backup, or 500-VU production target.
