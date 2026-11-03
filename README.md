# KINETIX AI

Single-deployment React/Vite client and FastAPI API. Backend owns all calculations and authorization.

## Local development

Python 3.13 and Node.js 22+. Run commands from the project root unless noted.

```sh
python -m venv .venv
# Windows: .venv\Scripts\activate
# POSIX: source .venv/bin/activate
pip install -r backend/requirements.txt
cd backend
alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

In a second terminal:

```sh
cd frontend
npm ci
npm run dev
```

Visit http://localhost:5173. For a single-process local deployment, run `npm run build` in frontend, then start the backend and visit http://127.0.0.1:8000. API schema: `/api/docs`. Health: `/api/v1/health`.

Copy `.env.example` to `backend/.env` for local configuration. Set a random JWT_SECRET of at least 32 characters to keep sessions across restarts. SQLite is allowed only locally. API credentials remain on the server; never prefix them with VITE_.

## PostgreSQL deployment

Copy `.env.example` to root `.env`. Set JWT_SECRET, POSTGRES_PASSWORD, ADMIN_EMAIL and CORS_ORIGINS to explicit HTTPS origins (or `[]` for same-origin only). Place the service behind HTTPS; production refresh cookies are Secure.

Use a random URL-safe database password (for example, generate it with Python's `secrets.token_urlsafe(32)`). Build and provision the administrator before opening the application port:

```sh
docker compose build app
docker compose up -d db
docker compose run --rm app sh -c 'alembic upgrade head && python -m app.cli create-user YOUR_ADMIN_EMAIL --role admin'
docker compose up -d app
```

The app container runs migrations and serves the compiled client. PostgreSQL is mandatory outside local development. Do not expose the database port. Back up the database volume.

## Accounts and administrator bootstrap

From `backend`, run `python -m app.cli create-user YOUR_EMAIL --role admin` before exposing registration publicly. Password entry is hidden and stored only as an Argon2 hash. `ADMIN_EMAIL` grants administrator status to a newly registered matching canonical email; email ownership is not verified, so never publish an unprovisioned administrator address.

Use `python -m app.cli set-password YOUR_EMAIL` to rotate a password and revoke all sessions; `python -m app.cli set-role YOUR_EMAIL user` changes a role and revokes sessions. No OTP or email delivery is simulated.

The client keeps access tokens in memory. Refresh cookies are HttpOnly, rotated on use, and protected by same-origin checks. Refresh-token reuse revokes its session family. Authentication routes are rate limited using bounded database buckets.

Run backend regressions from `backend` with `python -m pytest tests -q`.

## Athlete profile and weight history

Complete all three onboarding steps before tracking or planning. Measurements are stored in kg/cm; the display preference can be kg or lb. Phases and 1–4-week analysis windows are validated on the server. Starting weight is an undated baseline. First save records the current weight on today's UTC date; dated check-ins are immutable and owner-scoped. Backfilling an older date does not change the latest current weight. Profile editing cannot rewrite measurement history.

## Reference catalog

After migrations, run `python -m app.seed` from `backend`. Seeding is idempotent and preserves administrator edits/deletions. The catalog includes 16 muscle groups, 14 exercises (including timed planks), and 7 generic foods. Food values are per 100 g, not per serving; verify branded products against their labels. Custom records are private to their owner. Effective bodyweight load uses the exercise's single biomechanical fraction: pull-ups/dips 0.95 and push-ups 0.65. Other default muscle weights, MET values, and bodyweight fractions are explicitly approximate and editable.

## Deterministic fitness policy

The server owns calculations in `backend/app/services/fitness_algorithms.py`; the client only previews effective load. Mifflin–St Jeor and the requested Epley (reps ≤10) / Brzycki (11–36) branches are used exactly. Invalid/nonfinite values and nonpositive carbohydrate allocations are rejected.

- Cutting: TDEE −500 kcal, protein 2.2 g/kg, fat 0.8 g/kg.
- Lean bulking: TDEE +350 kcal, protein 2 g/kg, fat 1 g/kg.
- Recomposition: maintenance base energy, protein 2.3 g/kg, policy fat 0.8 g/kg; carbohydrate grams cycle +10% on training days and −10% on rest days. Actual daily calories reflect that carbohydrate change.
- Baseline/calisthenics policy defaults: maintenance, protein 2 g/kg, fat 0.8 g/kg.
- Progression: all working sets at top reps and RPE ≤8 add 2.5 kg upper/isolation or 5 kg lower compound. High effort at completed target reps holds load and adds one rep to the weakest completed set. Two consecutive minimum-rep failures recommend a 10% deload. Missing effort never produces a guessed decision.
- Weighted muscle set credits use MV 6, MEV 8–10, MAV 12–20, and a recovery warning above 22. These are planning landmarks, not diagnoses.

Fatigue is a non-medical 0–100 policy score: available normalized effort, volume, sleep, and soreness signals have weights 0.35/0.30/0.20/0.15. Missing signals are excluded and disclosed; no signals means unavailable. No AI alters deterministic metrics.

## Workout records

`/workouts` supports sessions, exercise blocks, rep-based and timed sets, effort/rest inputs, kg/lb entry, history, PRs, muscle credits, and observed strength curves. Every correction/deletion appends a source revision; database triggers prevent rewriting or deleting the source journal. Current totals exclude removed records and warmups. Exercise and bodyweight snapshots keep historical set metrics stable when profiles or catalog entries change. Timed holds and sets at 37+ reps do not receive fabricated 1RM estimates. Multi-week muscle totals are divided by the window length before comparison with weekly volume landmarks.

## Nutrition records and adherence

`/nutrition` logs dated meals with measured grams, meal slots/times, private custom foods, and water entries. Food labels are per 100 g; label calories are preserved independently of simplified planning energy factors (for example, polyols differ from digestible carbohydrate). Editing grams on an existing item retains its original nutrient snapshot. Remove and re-add an item to intentionally use current catalog values. Corrections and deletions append immutable source history.

The first entry saves the day's bodyweight, phase, energy base, and macro targets. Later profile changes cannot rewrite those targets. Explicit training/rest changes recalculate carbohydrate cycling from the saved base.

- Protein adherence is 100 within the inclusive 1.8–2.4 g/kg range; below it scores actual/minimum, above it scores maximum/actual, multiplied by 100.
- Energy, carbohydrate, and fat scores are `max(0, 100 × (1 − abs(actual − target) / target))`; status uses an inclusive ±10% band. Macro adherence equally averages these four scores.
- Protein timing flags gaps longer than five hours between recorded protein-containing meals only. Fewer than two such meals means insufficient data; wake/sleep intervals are not inferred.
- Caloric drift is recorded energy minus the day's saved target. Window averages use meal-recorded days only and show recording coverage. Missing and water-only dates remain unknown, not zero-calorie intake. These signals are not medical assessments or proof of complete logging.

Validation failures return field locations/messages without echoing submitted values, including credentials or non-finite numbers.

## Asynchronous AI and editable meal drafts

Set saves/corrections and completed exercise blocks enqueue private, source-linked `AIInsight` jobs. The API process runs the durable worker; start it normally with Uvicorn after migrations. The UI polls pending jobs, shows validated results or explicit unavailability, and keeps deterministic comparisons available in either case. Interrupted calls become unavailable rather than being silently billed again; retry is an explicit user action.

Gemini uses the [Interactions API](https://ai.google.dev/gemini-api/docs/interactions-overview) with `store: false`; OpenAI fallback uses [Responses structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs), also without provider storage. Configure server-only `GEMINI_API_KEY`, `GEMINI_MODEL`, `OPENAI_API_KEY`, and `OPENAI_MODEL`. Defaults are `gemini-3.8-flash` and `gpt-5.6-terra`; access and quotas depend on your provider account. During local verification Flash returned high-demand errors, Pro had no free-tier token allowance, and `gemini-3.1-flash-lite` returned a validated extraction but also intermittent high-demand errors. The current local smoke server overrides the Gemini model to Flash-Lite; `.env.example` retains the requested Flash default.

Provider decoding enforces JSON structure; server Pydantic validation enforces all bounds and domain rules before storage. Gemini's constrained decoder rejects large bounded schemas, so those value bounds are applied server-side rather than sent to its decoder. Provider error bodies, keys, reasoning blocks, and private context are not returned by insight endpoints.

Natural-language meals produce an editable draft only. Foods must match the visible catalog. Explicit metric amounts can resolve automatically; counts such as “3 eggs” or “1 scoop” cannot invent a gram weight. Resolve or explicitly remove every uncertain item, review the draft, then save through the normal meal endpoint. Parsing alone never changes intake totals.
