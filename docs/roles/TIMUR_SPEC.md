# Спецификация роли: ТИМУР — tech lead, platform/security/DevOps

## Миссия
Сделать так, чтобы продукт можно было безопасно запускать локально, в CI и на VPS; от PR до развёртывания путь не требует ручных команд. Удалить риск незапуска на защите. Ты интегратор, а не единственный разработчик.

## Ownership
GitHub rules, PR template, CONTRIBUTING, ADR001/002; конфигурация; FastAPI skeleton, auth email/password/JWT/Argon2, user/profile/Telegram link, groups/invites, membership/security; основной Docker, Compose, CI, GHCR/CD, Caddy/VPS, secrets, /health,/version, logs.

## Спецификация функциональности
1. /auth/register, /auth/login, /users/me, JWT expiry, Argon2, duplicate email tests.
2. Telegram actor mapping: service token not publicly exposed; Telegram update -> bot -> verified API service identity; create Telegram-only user and one-time link code. Race-safe uniqueness.
3. Groups and invites: owner joins automatically; strong single-use hashed token TTL 24h, join transaction; owner-only invite creation; no user deletion from history.
4. Unified validation/error format, 400 for invalid input, safe 404/403.
5. Docker Compose cold boot applies Alembic before API; no migration on each worker; health DB 200/503.
6. CI on PR (uv frozen, ruff, mypy, PostgreSQL tests coverage >=60, Docker build); block merge on fail; publish tagged SHA + deploy ONLY after main merge; health/version verification.
7. Public HTTPS reverse-proxy, DB private, least privilege secrets, rollback image instructions, logs with request_id and no secrets.

## Acceptance
- Fresh clone -> docker compose up --build works after documented env setup.
- Protected main with mandatory CI + one human review, documented tests denying direct push.
- Cross-user group reads/writes blocked; bot token alone cannot act as arbitrary user on public endpoint.
- New image published with SHA; VPS /version equals release SHA and /health 200.
- Docker nonroot, pinned base image, named PostgreSQL volume, healthchecks, logs persistence/rotation.

## Coordination
With Олег: schema users/group/member IDs, lock group first, claim actor, error schema. With Лера: /start onboarding, invitations, auth/link UX, bot service routes, token handling. Changes to contract via issue+review before coding.

## Don't do
Don't implement splitting or Telegram menus in parallel with owners; don't assign everyone a shared production token; don't weaken CI to pass. Own infrastructure but distribute documentation/testing to all three.

