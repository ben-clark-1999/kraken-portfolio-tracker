# Login Component — Design Spec

**Date:** 2026-04-26
**Status:** Approved (pending implementation plan)
**Scope:** Adds a single-user authentication gate to the Kraken Portfolio Tracker so the app can be deployed publicly without exposing its data.

---

## 1. Goal

Block unauthenticated access to all app data — dashboard, REST endpoints, agent WebSocket — behind a single password gate, with a polished, on-brand login screen.

**Out of scope for this spec:**
- Multi-user / signup / per-user data
- OAuth providers, magic-link, passkeys
- Password recovery (single user, password is set via CLI)
- Any user-management surface

## 2. Architecture

A single-user JWT-cookie gate. Stateless on the server side — no session table, no Redis, no Supabase Auth. The full auth state is the cookie.

- **Backend:** A bcrypt-hashed password and a JWT signing secret live in `.env`. `POST /api/auth/login` verifies the password and issues a signed JWT in an HTTP-only cookie. A `require_auth` FastAPI dependency reads + verifies the cookie on every protected route. The agent WebSocket performs the same check before accepting the upgrade.
- **Frontend:** A top-level `<App>` component holds an `auth: 'checking' | 'authenticated' | 'unauthenticated'` state. On mount, calls `GET /api/auth/me` to resolve the initial state, then renders `<Login>` or `<Dashboard>` accordingly. After successful login or logout, the state flips and the render swaps.
- **Token:** HS256-signed JWT, payload `{ sub: "user", iat, exp }`. 30-day expiry. No refresh tokens — re-login monthly is acceptable for a personal gate.
- **Cookie:** name `auth_token`, `HttpOnly`, `SameSite=Lax`, `Max-Age=2592000`, `Secure` in production only (false in local dev because there's no HTTPS).

## 3. Components and file layout

### New backend files

| File | Purpose |
|---|---|
| `backend/auth/__init__.py` | Package marker |
| `backend/auth/password.py` | `verify_password(plain: str, hashed: str) -> bool` — wraps `bcrypt.checkpw` |
| `backend/auth/jwt.py` | `encode_token() -> str`, `decode_token(token: str) -> dict` — wraps `pyjwt`. Raises `jwt.PyJWTError` on invalid/expired |
| `backend/auth/dependencies.py` | `require_auth(request: Request) -> None` — FastAPI dependency. Reads `auth_token` cookie, decodes, raises 401 on failure. |
| `backend/auth/rate_limit.py` | In-memory per-IP failure counter for login. 5 failures within 60s → 60s cooldown. |
| `backend/routers/auth.py` | `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me` |
| `backend/scripts/__init__.py` | Package marker |
| `backend/scripts/set_password.py` | One-off CLI: prompts via `getpass`, bcrypt-hashes the input, prints `APP_PASSWORD_HASH=...` to stdout for the user to paste into `.env`. |

### Modified backend files

- `backend/config.py` — add two required `Settings` fields: `app_password_hash: str`, `jwt_secret: str`. Both have **no default** — startup fails fast if missing.
- `backend/main.py` — include the new auth router; add `dependencies=[Depends(require_auth)]` to the existing `portfolio`, `history`, `sync`, and `agent` router includes; add a cookie auth check at the top of the WebSocket handler in `agent_chat_endpoint` (or in the route function in `routers/agent.py`) before `ws.accept()`.
- `backend/requirements.txt` — add `bcrypt==<latest>`, `pyjwt==<latest>`.

### New frontend files

| File | Purpose |
|---|---|
| `frontend/src/api/auth.ts` | `login(password: string): Promise<void>`, `logout(): Promise<void>`, `me(): Promise<{ ok: boolean }>` — fetch wrappers. All use `credentials: 'include'`. |
| `frontend/src/pages/Login.tsx` | The two-pane atmospheric login screen |
| `frontend/src/components/AtmospherePane.tsx` | The animated right-pane visual (gradients + SVG chart + grid) |
| `frontend/src/components/SignOutButton.tsx` | Top-right sign-out affordance |
| `frontend/src/App.tsx` | New top-level component: holds `auth` state, calls `me()` on mount, renders `<Login>` or `<Dashboard>` |

### Modified frontend files

- `frontend/src/main.tsx` — replace `<Dashboard />` with `<App />`
- `frontend/src/pages/Dashboard.tsx` — surgical insertion of `<SignOutButton />` next to the existing "Refresh" affordance in the SummaryBar metadata row, OR (if surgical insertion is awkward) render it adjacent to the SummaryBar in Dashboard's outer layout. Implementation can pick whichever fits cleanest.
- `frontend/src/hooks/useAgentChat.ts` — modify the `ws.onclose` handler to skip the 2s reconnect when `event.code === 4401`. The existing reconnect-forever behavior should remain for all other close codes.
- A small global fetch helper in `frontend/src/api/portfolio.ts` (or extracted to a shared `frontend/src/api/client.ts`) so any 401 response triggers `auth: 'unauthenticated'` in the App-level state. Implementation can choose: extract a shared `apiFetch` helper, or use a simple event-bus pattern (`window.dispatchEvent`) that App listens to.

### Approximate size

- ~250 lines of new backend code
- ~200 lines of new frontend code
- 11 new files, 6 modified files

## 4. Data flow

### 4.1 Initial page load

1. Browser loads app → `<App>` mounts in `auth: 'checking'`, renders nothing visible (or a brief shimmer)
2. `App` calls `me()` → `GET /api/auth/me`
3. 200 → `auth: 'authenticated'` → render `<Dashboard>`
4. 401 → `auth: 'unauthenticated'` → render `<Login>`

### 4.2 Login

1. User enters password, presses Continue
2. `Login.tsx` posts `{ password }` to `POST /api/auth/login`
3. Backend rate-limit check: if IP is in cooldown, return 429 with `Retry-After`
4. Backend verifies via `verify_password(payload, settings.app_password_hash)`. False → record failure, return 401. True → encode JWT, set cookie, return 200
5. Frontend: 200 → flip `auth` to `'authenticated'`. 401 → show "Incorrect password" inline. 429 → show "Too many attempts. Try again in N seconds."

### 4.3 Logout

1. User clicks "Sign out" in Dashboard
2. Frontend calls `logout()` → `POST /api/auth/logout`
3. Backend: `response.delete_cookie("auth_token")`, returns 200
4. Frontend flips `auth` to `'unauthenticated'`

### 4.4 Protected REST request

1. Any `/api/*` request from frontend includes `credentials: 'include'`
2. Backend's `require_auth` dependency reads the cookie, decodes the JWT, succeeds or raises 401
3. Frontend: a global 401 handler (whether via shared `apiFetch` or event bus) flips `auth` to `'unauthenticated'`

### 4.5 WebSocket auth

1. Browser opens `ws://.../api/agent/chat` — cookie is included on the HTTP upgrade request
2. Inside the WebSocket route handler, **before** `ws.accept()`: read `ws.cookies.get("auth_token")`, decode it. On failure → `await ws.close(code=4401)`. Don't accept.
3. `useAgentChat` treats close code 4401 as terminal — no reconnect. The global 401 handler also fires (the next REST request 401s) and the user is sent to Login.

### 4.6 Token expiry

After 30 days, JWT `exp` is past, decoding raises, `require_auth` returns 401, global handler flips state. No refresh tokens by design.

## 5. Visual design

### 5.1 Layout

- Two-pane CSS grid `grid-cols-2` filling the viewport (`min-h-screen`)
- **`< 768px`:** collapses to single-column form only — atmosphere pane is hidden
- Vertical 1px `border-surface-border` separates the two panes

### 5.2 Form pane (left)

- Background: subtle gradient `linear-gradient(135deg, #0f0e14 0%, #131220 100%)`
- Layout: centered content (`flex items-center justify-center`)
- Inner stack: `max-w-[320px]`, 24px gap between header and form
- "Sign in" heading: `text-lg font-semibold text-txt-primary tracking-tight`
- Password input: `bg-surface-raised border border-surface-border rounded-md px-3 py-2.5 text-sm text-txt-primary placeholder:text-txt-muted focus:border-kraken focus:outline-none transition-colors`
- "Continue" button: `bg-kraken hover:bg-kraken-light active:scale-[0.98] text-txt-primary px-3 py-2.5 rounded-md text-sm font-medium transition`

### 5.3 Atmosphere pane (right)

Six layers, all absolute-positioned within a `position: relative; overflow: hidden` container:

1. **Base gradient** — `linear-gradient(135deg, #1a1823 0%, #0f0e14 100%)`
2. **Central glow** — `radial-gradient(circle at 60% 50%, rgba(123, 97, 255, 0.35) 0%, rgba(123, 97, 255, 0.15) 40%, transparent 80%)`. **Animated 8s pulse:** opacity oscillates 0.8 → 1 → 0.8 ease-in-out infinite. Respects `prefers-reduced-motion` (existing media query in `globals.css`).
3. **Bottom-left accent glow** — `radial-gradient(ellipse at 30% 90%, rgba(98, 72, 229, 0.4) 0%, transparent 60%)`
4. **Top-right accent glow** — `radial-gradient(ellipse at 100% 0%, rgba(155, 133, 255, 0.25) 0%, transparent 50%)`
5. **Chart silhouette** — full-pane SVG with `viewBox="0 0 100 100" preserveAspectRatio="none"`. Path `M0,75 C15,72 28,58 42,52 S68,38 82,22 L100,12 L100,100 L0,100 Z` filled with a kraken-purple-to-transparent vertical gradient (opacity 0.45 → 0). Same path as a stroke (kraken purple, 0.9 stroke width, opacity 0.85, `stroke-linecap="round"`).
6. **Grid texture** — repeating 20px × 20px lines, `rgba(240, 238, 245, 0.025)` — barely perceptible, adds depth.

### 5.4 States

| State | Treatment |
|---|---|
| Default | As described |
| Submitting | Button text → "Signing in…", button `opacity-70 cursor-not-allowed`, input `disabled` |
| Wrong password (401) | Inline error below input: `text-xs text-loss mt-1` saying "Incorrect password". Input gains `border-loss` for ~1.5s, then transitions back. No shake. |
| Rate-limited (429) | Inline error: "Too many attempts. Try again in {N} seconds." (N from `Retry-After` header) |
| Network error | Inline error: "Couldn't reach server. Try again." |
| First mount | Whole page fades in over 200ms — define a one-off CSS keyframe in `globals.css` for this. |

### 5.5 Sign-out button

Lives in the Dashboard header next to "Refresh", styled consistently:

```
text-xs text-txt-muted hover:text-txt-secondary transition-colors
```

Plain text "Sign out" — no icon. Calls `logout()` then triggers App-level `auth: 'unauthenticated'`.

### 5.6 New CSS additions

In `globals.css`:

```css
@layer utilities {
  .animate-fade-in { animation: fade-in 200ms ease-out; }
  .animate-glow-pulse { animation: glow-pulse 8s ease-in-out infinite; }
}

@keyframes fade-in { from { opacity: 0; } to { opacity: 1; } }
@keyframes glow-pulse { 0%, 100% { opacity: 0.8; } 50% { opacity: 1; } }
```

The existing `prefers-reduced-motion` media query already short-circuits these animations.

## 6. Error handling and edge cases

| Case | Behavior |
|---|---|
| `APP_PASSWORD_HASH` or `JWT_SECRET` missing at startup | `Settings` raises `ValidationError` (Pydantic) — uvicorn fails fast with a clear missing-env message. **Both required.** No silent fallback. |
| `JWT_SECRET` rotated | All existing tokens become invalid → next request 401s → user re-logs in. Acceptable. |
| Login brute-force | Per-IP in-memory counter: 5 failures in 60s → IP is in cooldown for 60s. Cooldown returns 429 with `Retry-After: 60`. State resets on server restart (acceptable for personal use). |
| Two tabs open, logout in one | Other tab continues until its next API call 401s → flips. Acceptable. |
| Auth expires mid-session with agent panel open | Active WebSocket eventually disconnects (server close on next graph state read, or via heartbeat failure). `useAgentChat` doesn't reconnect because the next protected REST call 401s and sends user to Login. |
| Cookie cleared via dev tools | Next request 401 → Login. Same path as expiry. |
| Password submit + page refresh race | Form remounts in default state. Auth check on mount resolves truth from server — no stale form state. |

## 7. Testing

### Backend unit tests (in `backend/tests/`)

- `test_password.py` — `verify_password()` returns true for correct, false for wrong, false for malformed hash
- `test_jwt.py` — encode → decode roundtrip works; expired token raises; tampered signature raises; valid token contains expected `sub` and `exp` claims
- `test_auth_router.py` — `POST /login` 200 with valid pw + sets cookie / 401 with wrong / 422 with empty body. `POST /logout` clears cookie. `GET /me` 200 with valid cookie / 401 without
- `test_require_auth.py` — protected dummy endpoint 401s without cookie, 200 with valid, 401 with expired
- `test_rate_limit.py` — counter increments on failures, returns cooldown after 5 within 60s, expires correctly

### Manual smoke test

1. Boot server without env vars → fails fast with clear message
2. Set `APP_PASSWORD_HASH` and `JWT_SECRET` → reboot → `GET /api/health` 200
3. Open `http://localhost:5173` → Login screen renders, atmosphere pane visible at full size
4. Submit wrong password → inline error appears, border briefly red
5. Submit correct password → Dashboard loads, agent panel works as before
6. Reload page → Dashboard still loads (cookie persisted)
7. Click Sign out → back to Login
8. Submit 6 wrong passwords rapidly → 6th gets rate-limit message
9. Verify `< 768px` viewport drops to single-pane

### No frontend unit tests

Consistent with Phase 1-3 — frontend correctness is verified manually in the browser.

## 8. Open questions for plan stage

- **Exact package versions** for `bcrypt` and `pyjwt` — look up latest stable on PyPI at implementation time
- **Implementation choice for global 401 handling** — shared `apiFetch` wrapper vs `window.dispatchEvent` event bus. Decide during plan.
- **`SignOutButton` placement** — inside `SummaryBar.tsx` (modify the user's existing component) vs alongside `<SummaryBar>` in `Dashboard.tsx` (purely additive). Decide during plan based on whether the user has committed their `SummaryBar.tsx` WIP by then.
