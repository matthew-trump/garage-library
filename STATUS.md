# Garage Library — Status Update

_Last updated: 2026-08-08 (branch `main`, last commit `ebd50f2` "Add language field to books")_

## Where things stand

The app is a working single-user catalog with multi-user scaffolding half-built on top of it.
Backend is one 869-line `app.py` (FastAPI + `sqlite3`), frontend is one 2,136-line
`static/index.html` with no build step. Working tree is clean; there are no tests.

Live data in `garage-library.db`: **517 books across 39 stacks**, all owned by `user_id = 2`
(`matthewtrump`, level 2 / admin). Second account `testuser` (id 3, level 1) exists with no data.
No books are unstacked; 2 are flagged `special_collection`; 2 distinct languages in use.

## What works

**Auth** — bcrypt password hashing, JWT sessions (`HS256`, 24h default expiry), `level` column
for admin (2) vs normal (1). Registration is gated behind the `ALLOW_CREATE_ACCOUNT` env flag.
Frontend handles session expiry and has a password-visibility toggle.

**Catalog** — stacks with name/location, books with title, author, publisher, year, edition,
status, type, translation flag + translator, special-collection flag, and language. Reordering
within a stack uses the two-pass negative-temp-position trick to dodge the `(stack_id, position)`
unique constraint. Books can be moved between stacks on edit.

**Search** — multi-field (title/author/publisher/year toggles), scoped to the caller's own books;
admins can search another user's shelf via `user_id`.

**Extras** — OpenLibrary lookup on the book detail page; one-click DB backup to
`DATABASE_BACKUP_DIRECTORY` (3 backups on disk, most recent 2026-02-18).

**Frontend routes** — `/`, `/stacks/{id}`, `/stacks/new`, `/book/{id}`, `/search`, `/login`,
`/logged-out`, `/admin`, `/admin/users`.

## Gaps worth closing next

These are ordered roughly by how much they'd bite. Nothing here is currently exploitable beyond
the LAN, since the server binds `127.0.0.1` — but the multi-user model is the thing most
half-finished, and it's what the last several commits were building toward.

### 1. Ownership checks are missing on several endpoints

The read/list endpoints were written before `user_id` existed and never caught up:

| Endpoint | Issue |
|---|---|
| `GET /api/books` (app.py:309) | No auth at all; returns every user's books |
| `GET /api/book/{id}` (app.py:385) | No auth at all; any book by id |
| `PATCH /api/stack/{id}` (app.py:708) | No auth at all — anyone can rename any stack |
| `PUT /api/stack/{id}` reorder (app.py:745) | No auth at all — anyone can reorder any stack |
| `PUT /api/book/{id}` (app.py:586) | Requires auth, but never checks the book belongs to the caller |
| `POST /api/book` (app.py:493) | Validates the target stack exists, not that the caller owns it |

`GET /api/stacks`, `GET /api/stack/{id}`, and `/api/books/search` do scope correctly — they're the
pattern to copy.

### 2. Stack names are globally unique, not per-user

Both `create_stack` (app.py:458) and `update_stack` (app.py:726) check `WHERE name = ?` with no
`user_id` filter, so one user's "Poetry" blocks everyone else's. Wants a per-user uniqueness check
and ideally a real DB constraint on `(user_id, name)`.

### 3. No delete anywhere

There's no `DELETE` route for a book or a stack, and no UI for it. Mis-entered books can only be
edited, never removed.

### 4. No password-change flow

Changing a password currently means hand-writing a bcrypt hash into the DB (which is how
`matthewtrump`'s password was last rotated). A `POST /api/password` taking old + new, running
through `validate_password`, would close this. Note `validate_password` (app.py:180) requires
upper + lower + digit, so passwords set directly in SQL can violate rules the API enforces — login
only calls `checkpw` and won't notice.

### 5. Migration strategy won't scale much further

`init_db()` is now ~100 lines of `try: ALTER TABLE / except: pass`, plus two hardcoded data fixes
that run on every boot: `UPDATE user SET level = 2 WHERE username = 'matthewtrump'` (app.py:55) and
backfilling `user_id = 2` onto any null book/stack (app.py:67, 78). The backfills are no-ops now
that everything is assigned, and the admin promotion is a permanent hardcode of one username.
A `schema_version` table, or just retiring the completed backfills, would clean this up.

### 6. Asset weight

`static/favicon.png` and `static/logo.png` are **7.5 MB each** — bigger than the entire rest of the
project combined. A resized favicon and a web-sized logo would cut page load dramatically.

### 7. Config and docs drift

- `.env.example` lists only `DATABASE_BACKUP_DIRECTORY` and `ALLOW_CREATE_ACCOUNT`; the live `.env`
  also carries `JWT_SECRET` and `JWT_EXPIRY_SECONDS`. `JWT_SECRET` silently falls back to
  `"dev-secret-do-not-use-in-production"` if unset (app.py:20).
- `CLAUDE.md` documents the schema as `stack(id, name, location)` and
  `book(id, title, author, publisher, stack_id, position)` — it's missing `user`, `user_id`, and
  the eight book fields added since. It also gives the run command as bare `uvicorn`, while
  `start-server.sh` is the real entry point.

### 8. No tests

No test files exist. The reorder logic and the ownership rules above are the two places where a
handful of tests would pay for themselves immediately.

## Suggested order for the next session

1. Ownership checks on the six endpoints in §1 — smallest change, biggest correctness win.
2. Per-user stack-name uniqueness (§2).
3. Delete endpoints + UI (§3).
4. Password-change endpoint (§4).
5. Housekeeping: refresh `CLAUDE.md` and `.env.example`, shrink the PNGs, prune the dead
   backfill migrations.
