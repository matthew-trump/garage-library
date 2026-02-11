# Garage Library

A web application for cataloging and browsing a personal book collection organized into named stacks.

## What It Does

Garage Library tracks books across physical stacks (shelves, piles, boxes, etc.). Each stack has a name and optional location. Each book has a title, author, publisher, and a position within its stack.

The app provides:

- **Browse** -- sidebar lists all stacks alphabetically; click one to see its books in order
- **Search** -- find books by title, author, or publisher
- **Add/edit books** -- create books at the beginning or end of a stack, edit details, move books between stacks
- **Add/edit stacks** -- create stacks with a name and location, rename or relocate them
- **Reorder** -- drag and drop to rearrange books within a stack

## Architecture

- **Backend**: Python FastAPI application (`app.py`) serving a JSON REST API under `/api/` and a single-page frontend under `/`
- **Frontend**: Vanilla HTML/CSS/JS in `static/index.html` with client-side routing (`pushState`)
- **Database**: SQLite (`garage-library.db`) with two tables: `stack` and `book`
- **No build step** -- everything runs directly with Python

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/stacks` | List all stacks |
| GET | `/api/stack/{id}` | Get stack with its books |
| POST | `/api/stack` | Create a new stack |
| PATCH | `/api/stack/{id}` | Update stack name/location |
| PUT | `/api/stack/{id}` | Reorder books in a stack |
| GET | `/api/books` | List all books |
| GET | `/api/books/search` | Search books by title/author/publisher |
| GET | `/api/book/{id}` | Get a single book |
| POST | `/api/book` | Add a book to a stack |
| PUT | `/api/book/{id}` | Update book details or move to another stack |

## Installation

Requires Python 3.11+.

1. Install dependencies:

   ```
   pip install fastapi uvicorn
   ```

2. Ensure `garage-library.db` exists in the project root. (The SQLite database contains `stack` and `book` tables.)

## Running

Start the server on port 8025:

```
uvicorn app:app --host 127.0.0.1 --port 8025
```

Then open http://127.0.0.1:8025 in a browser.
