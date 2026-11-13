# Render operations and release checks

## Before onboarding athletes

- Confirm web and worker services are healthy; check `/api/v1/health/live` and `/api/v1/health` from the generated HTTPS origin.
- Run the 500-VU scenario from [`load-testing.md`](load-testing.md) against a dedicated staging account. Review service CPU/memory, target latency, PostgreSQL connections, and disk usage in Render's dashboard during the full hold period.
- The pool budget is at most 36 connections at steady state and 69 during simultaneous old/new web and worker deployment overlap plus one migration process. Alert and investigate before connections approach 80 of the PostgreSQL plan's 100 limit.
- Confirm the Render PostgreSQL backup/PITR policy for the selected paid plan and test a restore before storing real records.

## Routine operations

- Render commits on `feature/aws-android-scale` auto-deploy the Blueprint services. Check the web pre-deploy migration/seed result before confirming the service is healthy.
- Change the Render service `JWT_SECRET` only with a planned session invalidation; changing it logs users out.
- Add optional provider keys in Render's protected environment settings on both web and worker services. Never put them in `render.yaml`, Git, or a Docker build context.
- For an APK update, run **Build KINETIX Android APK** with the current HTTPS service URL, download the artifact, and install it. Debug APK signing keys are ephemeral across runs, so uninstall the previous debug APK before installing a new one.
- If Render changes the service hostname, build a new APK with the new HTTPS origin. The native wrapper intentionally rejects arbitrary hosts and does not support HTTP.
