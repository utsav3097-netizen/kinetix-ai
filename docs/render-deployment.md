# Deploy KINETIX on Render

This is the non-AWS deployment path. `render.yaml` creates a same-origin Docker web service, one background AI worker, and private managed PostgreSQL in Singapore. Render provides HTTPS on the web service's generated `onrender.com` hostname.

## Provisioning

1. Create a Render account and connect this GitHub repository.
2. Choose **New → Blueprint Instance** and select branch `feature/aws-android-scale`.
3. Review the plan before confirming. The Blueprint uses paid web, worker, and PostgreSQL plans. Autoscaling requires a Render Pro workspace or higher; Render's free Postgres expires after 30 days and its free web service spins down.
4. Wait for `/api/v1/health/live` to pass, then verify `/api/v1/health` reports database readiness. Copy the exact HTTPS origin from the dashboard; do not guess the generated hostname.
5. In the web service Shell, create the administrator with `python -m app.cli create-user ADMIN_EMAIL --role admin`. Enter the password only at the hidden prompt. Never set an unverified `ADMIN_EMAIL` environment value.
6. Optional `GEMINI_API_KEY` and `OPENAI_API_KEY` values can be set in the Render environment on both web and worker services. Without keys, provider-backed AI features remain unavailable; core records remain usable.

Render runs `alembic upgrade head && python -m app.seed` before each web deploy. The web service sets `RUN_AI_WORKER=false`; one worker runs `python -m app.worker_main`. Render generates `JWT_SECRET` through a shared environment group. PostgreSQL accepts internal connections only.

## Client-IP and database safety

The Docker command enables Uvicorn proxy-header handling with Render's forwarded client address. Keep the service behind Render's ingress; do not expose a second direct port. Verify the forwarded IP and auth-rate-limit bucket behavior after deployment.

The Render Postgres `1c-2g` plan allows 100 connections. The web and worker pools are 2 plus 1 overflow per process: 10 web replicas, one worker, and one migration task use at most 36 steady-state connections. An old/new deployment overlap is at most 69 connections under this topology. The 500-VU test remains mandatory; the plan size alone does not prove capacity.
