# Garage Library

A web app for cataloging a personal book collection organized into physical stacks.

## Project Structure

- `app.py` -- FastAPI application (backend API + frontend serving)
- `static/index.html` -- Single-page frontend (vanilla HTML/CSS/JS, no build step)
- `static/favicon.png`, `static/logo.png` -- Static assets
- `garage-library.db` -- SQLite database (gitignored)
- `garage-library.json` -- Original source data (imported into DB)

## Backend

- **Framework**: FastAPI with SQLite via `sqlite3` module
- **API routes** are mounted under `/api/` using `APIRouter(prefix="/api")`
- **Frontend routes**: `GET /` and `GET /{path:path}` catch-all return `static/index.html`
- Static files are served via `StaticFiles` mount at `/static` (must come before the catch-all route)

### Database Schema

- `stack`: id, name, location
- `book`: id, title, author, publisher, stack_id, position
- Unique constraint on (stack_id, position) -- use two-pass negative temp positions when reordering

## Frontend

- Single-page app with client-side routing using `history.pushState` and `popstate`
- All views are divs toggled by `showView(name)`
- Routes: `/`, `/stacks/{id}`, `/book/{id}`, `/stacks/new`, `/search`

## Running

```
pip install fastapi uvicorn
uvicorn app:app --host 127.0.0.1 --port 8025
```

## Development Notes

- Python 3.13.1 via pyenv (`pyenv shell 3.13.1`)
- The DB is gitignored (`*.db` in `.gitignore`)
- When updating book positions, always use the two-pass approach (set to negative temps first, then final values) to avoid unique constraint violations
