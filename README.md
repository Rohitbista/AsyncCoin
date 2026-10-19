# Async Coin

A full-stack crypto tracker. A FastAPI backend syncs market data for the top coins from CoinGecko into PostgreSQL on a schedule, and a lightweight single-page frontend lets verified users browse the market, view price history, and manage a personal watchlist with price alerts.

| Layer | Stack | Hosting (free tier) |
| --- | --- | --- |
| Backend | Python, FastAPI, SQLAlchemy (async), JWT auth | FastAPI Cloud |
| Database | PostgreSQL, Alembic migrations | Neon |
| Email | Brevo transactional email API | Brevo |
| Frontend | Vanilla JS single-page app (`app.js`) | GitHub Pages |
| Tooling | [uv](https://docs.astral.sh/uv/), GitHub Actions | |

Live API: `https://asynccoin.fastapicloud.dev` (interactive docs at `/docs`)

---

## Features

- **Market data** from CoinGecko, synced in the background and stored as append-only snapshots, so every user reads from the same database and price history builds up automatically.
- **Search, sort and pagination** across the top 1,000 coins by default.
- **Coin detail view** with 24h stats, all-time high, supply and a price sparkline.
- **Personal watchlist** with notes and `alert_above` / `alert_below` price targets, plus a summary (best and worst 24h performer, total market cap, 24h / 7d / 30d change per coin).
- **Account system**: registration, email verification, login, forgot and reset password.
- **Security details**:
  - Password hashing is done off the event loop, with a dummy hash verified for unknown emails to equalise login timing.
  - Registration, resend and forgot-password responses are identical whether or not the email exists (no account enumeration).
  - Email tokens are random, single-use and expiring. Only their SHA-256 hash is stored.
  - Verification uses `POST`, so email link scanners that prefetch URLs cannot consume the token.
  - Per-IP, per-route rate limiting on all auth endpoints.
  - Emails are stored lowercased, enforced by a database `CHECK` constraint.

---

## Architecture

```
┌──────────────────────┐   HTTPS + JWT   ┌──────────────────────────┐   asyncpg   ┌──────────────┐
│  GitHub Pages        │ ──────────────▶ │  FastAPI Cloud           │ ──────────▶ │  Neon        │
│  index.html + app.js │                 │  asynccoin.app.server    │             │  PostgreSQL  │
└──────────────────────┘                 │                          │             └──────────────┘
                                         │  ├─ routes (auth, crypto,│
                                         │  │   watchlist)          │   HTTPS     ┌──────────────┐
                                         │  ├─ services             │ ──────────▶ │  CoinGecko   │
                                         │  ├─ background sync ─────┼───────────▶ └──────────────┘
                                         │  └─ email (background)   │   HTTPS     ┌──────────────┐
                                         └──────────────────────────┘ ──────────▶ │  Brevo       │
                                                                                  └──────────────┘
```

On startup the app creates one shared `httpx.AsyncClient` and, if `sync_enabled` is true, launches a background task that pulls coin data from CoinGecko immediately and then every `sync_interval_seconds` (default 3 hours). Each sync inserts a new batch of rows into `crypto_snapshots` that all share the same `fetched_at`. "Latest" data is simply the rows with the newest `fetched_at`.

### Project layout

The imports show the package is named `asynccoin`. The relevant structure is:

```
asynccoin/
├── app/
│   ├── server.py                 # FastAPI app, lifespan, CORS, router wiring
│   ├── deps.py                   # get_current_user, in-memory RateLimiter
│   ├── routes/
│   │   ├── auth.py               # /api/auth/*
│   │   ├── crypto_tracker.py     # /api/crypto/*
│   │   └── personal_crypto.py    # /api/crypto/watchlist/*
│   └── schemas/                  # Pydantic request/response models
├── config/
│   └── settings.py               # Pydantic settings (ASYNCCOIN_ env vars)
├── database/
│   ├── base.py
│   ├── models.py                 # User, UserToken, WatchlistItem, CryptoSnapshot
│   ├── session.py                # async engine + get_db dependency
│   └── crypto_repo.py            # snapshot queries
└── services/
    ├── security.py               # password hashing, JWT, token helpers
    ├── email.py                  # Brevo email sending
    ├── crypto_sync.py            # CoinGecko background sync
    └── personal_crypto_service.py# watchlist business logic
```

The routes layer handles HTTP only (validation and error-to-status mapping). SQL lives in repositories and business rules live in services.

### Data model

| Table | Purpose |
| --- | --- |
| `users` | Account, active/verified flags, login timestamps. Email is unique and lowercase-checked. |
| `user_tokens` | Single-use tokens for `verify_email` and `reset_password`. Stores the SHA-256 hash only. |
| `user_watchlist` | One row per (user, coin) with optional note and alert thresholds. `coin_id` is deliberately not a foreign key, because snapshots are append-only. The service layer validates the coin exists. |
| `crypto_snapshots` | Append-only market data, one row per coin per sync, indexed on `(coin_id, fetched_at)` and `(fetched_at, market_cap_rank)`. |

> Adding a new token purpose requires updating the `purpose_valid` `CHECK` constraint with an Alembic migration.

---

## API overview

All routes except those marked public require `Authorization: Bearer <access_token>`. Full interactive docs are at `/docs` (use the **Authorize** button and paste the token from `/api/auth/login`).

### Public

| Method | Path | Description |
| --- | --- | --- |
| GET | `/` | Welcome message |
| GET | `/health` | Health check |

### Auth: `/api/auth`

| Method | Path | Rate limit (per IP) | Description |
| --- | --- | --- | --- |
| POST | `/register` | 5 / 10 min | Create an account and send a verification email (202) |
| POST | `/verify-email` | 20 / 10 min | Consume a verification token |
| POST | `/resend-verification` | 5 / 10 min | Resend the verification email (202) |
| POST | `/login` | 10 / 1 min | Returns `access_token` and `expires_in` |
| GET | `/me` | none | Current user (requires auth) |
| POST | `/forgot-password` | 5 / 10 min | Send a password reset email (202) |
| POST | `/reset-password` | 10 / 10 min | Set a new password with a reset token |

Behaviour worth knowing:

- Unverified or disabled accounts cannot log in (`403`).
- Resending a verification or reset email is throttled by `verification_resend_cooldown_seconds` (default 10 minutes). Issuing a new token invalidates earlier unused ones.
- Completing a password reset also marks the email as verified, since the user proved they own the inbox.

### Market: `/api/crypto` (auth required)

| Method | Path | Description |
| --- | --- | --- |
| GET | `/coins` | Paginated list. Params: `limit` (1-250), `offset`, `search`, `sort_by`, `order` |
| GET | `/top` | Top N by market cap (`limit` 1-100) |
| GET | `/movers` | Biggest 24h `gainers` or `losers` |
| GET | `/coins/{coin_id}` | Latest snapshot for a coin |
| GET | `/coins/{coin_id}/history` | History, newest first. Params: `since`, `until` (ISO timestamps), `limit` (1-1000) |

`sort_by` accepts `market_cap_rank`, `market_cap`, `current_price`, `total_volume`, `price_change_percentage_24h` and `name`.

### Watchlist: `/api/crypto/watchlist` (auth required)

| Method | Path | Description |
| --- | --- | --- |
| GET | `` | The user's coins with latest market data |
| POST | `` | Add coins: `{"coin_ids": ["bitcoin", "solana"]}`. Response reports `added`, `already_tracked` and `not_found`. Returns `409` if the watchlist limit is exceeded. |
| GET | `/summary` | Best/worst 24h performer, total market cap, 24h/7d/30d change |
| GET | `/alerts` | Coins currently past their `alert_above` / `alert_below` |
| PATCH | `/{coin_id}` | Update `note`, `alert_above`, `alert_below` (only fields sent are changed; send `null` to clear) |
| DELETE | `/{coin_id}` | Stop tracking a coin (204) |

---

## Configuration

Settings are read from environment variables prefixed with `ASYNCCOIN_`, or from a `.env` file in the project root.

### Required

| Variable | Description |
| --- | --- |
| `ASYNCCOIN_DATABASE_URL` | Must use the asyncpg driver: `postgresql+asyncpg://user:pass@host:5432/dbname` |
| `ASYNCCOIN_COINGECKO_URL` | CoinGecko API base URL |
| `ASYNCCOIN_JWT_SECRET` | Generate with `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `ASYNCCOIN_BREVO_API_KEY` | Brevo API key. Set to an empty string in dev to log links instead of emailing |
| `ASYNCCOIN_FRONTEND_BASE_URL` | Where the frontend is served, e.g. `https://<user>.github.io/<repo>` |

### Optional (defaults shown)

| Variable | Default | Description |
| --- | --- | --- |
| `ASYNCCOIN_BREVO_SENDER_EMAIL` | `""` | Must be a sender or domain verified in Brevo. **Required in practice for real email.** |
| `ASYNCCOIN_BREVO_SENDER_NAME` | `Async Coin` | Display name on emails |
| `ASYNCCOIN_JWT_ALGORITHM` | `HS256` | |
| `ASYNCCOIN_ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Access token lifetime |
| `ASYNCCOIN_VERIFICATION_TOKEN_TTL_HOURS` | `24` | |
| `ASYNCCOIN_VERIFICATION_RESEND_COOLDOWN_SECONDS` | `600` | |
| `ASYNCCOIN_PASSWORD_RESET_TOKEN_TTL_MINUTES` | `60` | |
| `ASYNCCOIN_SYNC_ENABLED` | `true` | Turn the background CoinGecko sync on or off |
| `ASYNCCOIN_SYNC_INTERVAL_SECONDS` | `10800` | Every 3 hours |
| `ASYNCCOIN_SYNC_PER_PAGE` | `250` | CoinGecko maximum per page |
| `ASYNCCOIN_SYNC_MAX_PAGES` | `4` | 4 pages x 250 = top 1,000 coins |
| `ASYNCCOIN_SYNC_PAGE_DELAY_SECONDS` | `8.0` | Pause between pages to respect rate limits |
| `ASYNCCOIN_SYNC_RATE_LIMIT_RETRIES` | `3` | Retries per page on HTTP 429 |
| `ASYNCCOIN_SYNC_RATE_LIMIT_WAIT_SECONDS` | `60.0` | Wait before retrying a 429 |
| `ASYNCCOIN_REQUEST_TIMEOUT_SECONDS` | `10.0` | Outbound HTTP timeout |
| `ASYNCCOIN_CACHE_TTL_SECONDS` | `60` | |
| `ASYNCCOIN_VS_CURRENCY` | `usd` | |
| `ASYNCCOIN_COIN_IDS` | `bitcoin,ethereum,tether,binancecoin,solana` | |

---

## Local development

### Prerequisites

- Python (version pinned in `pyproject.toml`)
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- A PostgreSQL database (local, Docker, or a free Neon project)

### 1. Install dependencies

```bash
uv sync
```

### 2. Create a `.env` file

```env
ASYNCCOIN_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/asynccoin
ASYNCCOIN_COINGECKO_URL=https://api.coingecko.com/api/v3
ASYNCCOIN_JWT_SECRET=replace-me-with-a-long-random-string
ASYNCCOIN_FRONTEND_BASE_URL=http://localhost:5500
# Leave empty in dev: verification and reset links are printed in the server log
ASYNCCOIN_BREVO_API_KEY=
```

### 3. Run migrations

```bash
uv run alembic upgrade head
```

### 4. Start the API

```bash
uv run uvicorn asynccoin.app.server:app --reload --port 8000
```

Open <http://localhost:8000/docs>. The first CoinGecko sync starts in the background right away. With the default settings it takes roughly 30 seconds or more, because of the delay between pages.

### 5. Serve the frontend

Set `API_BASE` at the top of `app.js` to `http://localhost:8000`, then serve the frontend folder with any static server:

```bash
python -m http.server 5500
```

### Registering locally without Brevo

When `ASYNCCOIN_BREVO_API_KEY` is empty, the backend logs a warning containing the verification link, such as `http://localhost:5500/#/verify?token=...`. Open that link (or paste the token on the verify page) to activate the account. Password reset links work the same way.

### Creating a migration

After changing `models.py`:

```bash
uv run alembic revision --autogenerate -m "describe change"
uv run alembic upgrade head
```

Review autogenerated migrations before committing them.

---

## Frontend

The frontend is a dependency-free single-page app written in `app.js`, using hash-based routing so it works on GitHub Pages without server rewrites.

| Route | Access | Purpose |
| --- | --- | --- |
| `#/login`, `#/register` | public | Sign in or create an account |
| `#/verify?token=...` | public | Email verification landing page |
| `#/forgot`, `#/reset?token=...` | public | Password reset flow |
| `#/market` | auth | Searchable, sortable, paginated coin table with detail dialog |
| `#/watchlist` | auth | Manage tracked coins, notes and alerts, with summary stats |
| `#/alerts` | auth | Coins currently past their price targets |

- The JWT and its expiry are stored in `localStorage` (`ac_token`, `ac_exp`). The app logs out automatically when the token expires or the API returns `401`.
- All user-supplied and API-supplied strings are HTML-escaped before rendering.
- `app.js` expects the host page to provide elements with ids `app`, `dlg` (a `<dialog>`), `nav`, `acct` and `toast`.
- Email links point to `<FRONTEND_BASE_URL>/#/verify?token=...` and `<FRONTEND_BASE_URL>/#/reset?token=...`, so `ASYNCCOIN_FRONTEND_BASE_URL` must match where the frontend is actually served.

---

## Deployment

### Database: Neon

1. Create a Neon project and copy the connection string.
2. Convert it to the asyncpg form, `postgresql+asyncpg://...`. asyncpg takes `ssl=require` rather than `sslmode=require`, so adjust the query string if Neon gives you the latter.
3. Use this value as `ASYNCCOIN_DATABASE_URL` for both the backend and the migration workflow.

### Backend: FastAPI Cloud

1. Make sure the app entry point is `asynccoin.app.server:app`.
2. Set all required `ASYNCCOIN_*` variables in your FastAPI Cloud environment, with `ASYNCCOIN_FRONTEND_BASE_URL` pointing at your GitHub Pages URL.
3. Deploy with the FastAPI Cloud CLI (`fastapi deploy`).

Production checklist:

- [ ] **Restrict CORS.** `server.py` currently uses `allow_origins=["*"]`. Change it to your GitHub Pages origin, such as `https://<user>.github.io` (origins have no path).
- [ ] **Trusted proxy headers.** `main()` runs uvicorn with `forwarded_allow_ips="*"`, which is convenient but lets any client spoof `X-Forwarded-For` and therefore bypass IP rate limiting if the app is ever reachable without the platform proxy in front. Restrict it to the proxy's address where possible.
- [ ] **Rate limiter scope.** The limiter is in-memory and per process, so the effective limit is multiplied by the number of workers or instances. Move to Redis or `slowapi` if you scale out.
- [ ] **Background sync.** The CoinGecko sync runs inside the web process. If the platform scales the app to zero or restarts it often, syncs will pause or restart. Check that your plan keeps the process alive, or move the sync to a scheduled job.

### Frontend: GitHub Pages

1. Set `API_BASE` at the top of `app.js` to your deployed backend (it must be HTTPS, because GitHub Pages is served over HTTPS).
2. Push the frontend files to the branch or folder configured under **Settings, Pages**.
3. Set `ASYNCCOIN_FRONTEND_BASE_URL` on the backend to the resulting Pages URL, for example `https://<user>.github.io/<repo>`.

### CI: database migrations

`.github/workflows/migrations.yml` runs `uv run alembic upgrade head` against the production database on every push to `main` that touches migration files or any `.py` file, and can also be started manually from the **Actions** tab (`workflow_dispatch`).

Add these repository secrets (**Settings, Secrets and variables, Actions**):

`ASYNCCOIN_DATABASE_URL`, `ASYNCCOIN_COINGECKO_URL`, `ASYNCCOIN_JWT_SECRET`, `ASYNCCOIN_BREVO_API_KEY`, `ASYNCCOIN_FRONTEND_BASE_URL`, and optionally `ASYNCCOIN_JWT_ALGORITHM` and `ASYNCCOIN_ACCESS_TOKEN_EXPIRE_MINUTES`.

Things to double-check in the workflow:

- The variable in the workflow is named `ASYNCCOIN_ACCESS_TOKEN_EXPIRES_MINUTES`, but the setting is `access_token_expire_minutes`, so the correct variable is `ASYNCCOIN_ACCESS_TOKEN_EXPIRE_MINUTES`. The misspelled one is silently ignored.
- The `paths` filter lists `migration/**`. Make sure that matches your real Alembic folder name (for example `migrations/` or `alembic/`).
- Since `**.py` is in the filter, every Python change triggers a migration run. That is harmless when there is nothing new to apply, but you may prefer to narrow it.
- If a secret is left unset, GitHub passes an empty string, which can override a default (for example an empty `JWT_ALGORITHM`). Remove optional variables you don't set.

---

## Security notes

- Never commit `.env` or secrets. Rotate `ASYNCCOIN_JWT_SECRET` if it is ever exposed (this logs everyone out).
- Access tokens are short-lived (30 minutes by default) and there is no refresh token, so users log in again after expiry.
- Because the JWT lives in `localStorage`, keep the frontend free of third-party scripts and continue escaping all rendered values.
- Password reset and verification links contain a raw token in the URL fragment query. Treat them as credentials until used or expired.

---

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| Frontend shows "Can't reach the server" | Wrong `API_BASE`, backend not HTTPS, or CORS blocking the origin |
| Registration succeeds but no email arrives | `ASYNCCOIN_BREVO_SENDER_EMAIL` not set or not verified in Brevo. Check the server logs for `Brevo send failed`. |
| "Invalid or expired verification link" | Token already used, expired (24h), or superseded by a newer resend |
| Login returns 403 "verify your email" | Account not verified yet. Use the resend flow. |
| `429 Too many requests` | Rate limit hit. Check the `Retry-After` header. |
| Market page is empty | The first sync hasn't finished, or `ASYNCCOIN_SYNC_ENABLED=false`, or CoinGecko is rate-limiting. Check the logs. |
| Alembic cannot connect to Neon | Connection string not in `postgresql+asyncpg://` form, or `sslmode` used instead of `ssl` |

---