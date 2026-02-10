import sqlite3
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.routing import APIRouter
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

DB_PATH = Path(__file__).parent / "garage-library.db"

app = FastAPI(title="Garage Library API")


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# --- Models ---

class Book(BaseModel):
    id: int
    title: str
    author: str | None
    publisher: str | None
    stack_id: int
    position: int


class Stack(BaseModel):
    id: int
    name: str


class StackDetail(BaseModel):
    id: int
    name: str
    books: list[Book]


# --- API Routes ---

api = APIRouter(prefix="/api")


@api.get("/books", response_model=list[Book])
def list_books():
    conn = get_db()
    rows = conn.execute("SELECT id, title, author, publisher, stack_id, position FROM book").fetchall()
    conn.close()
    return [dict(r) for r in rows]


@api.get("/book/{book_id}", response_model=Book)
def get_book(book_id: int):
    conn = get_db()
    row = conn.execute(
        "SELECT id, title, author, publisher, stack_id, position FROM book WHERE id = ?",
        (book_id,),
    ).fetchone()
    conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="Book not found")
    return dict(row)


@api.get("/stacks", response_model=list[Stack])
def list_stacks():
    conn = get_db()
    rows = conn.execute("SELECT id, name FROM stack").fetchall()
    conn.close()
    return [dict(r) for r in rows]


@api.get("/stack/{stack_id}", response_model=StackDetail)
def get_stack(stack_id: int):
    conn = get_db()
    stack = conn.execute("SELECT id, name FROM stack WHERE id = ?", (stack_id,)).fetchone()
    if stack is None:
        conn.close()
        raise HTTPException(status_code=404, detail="Stack not found")
    books = conn.execute(
        "SELECT id, title, author, publisher, stack_id, position FROM book WHERE stack_id = ? ORDER BY position",
        (stack_id,),
    ).fetchall()
    conn.close()
    return {"id": stack["id"], "name": stack["name"], "books": [dict(b) for b in books]}


class ReorderRequest(BaseModel):
    book_ids: list[int]


@api.put("/stack/{stack_id}", response_model=StackDetail)
def reorder_stack(stack_id: int, body: ReorderRequest):
    conn = get_db()
    stack = conn.execute("SELECT id, name FROM stack WHERE id = ?", (stack_id,)).fetchone()
    if stack is None:
        conn.close()
        raise HTTPException(status_code=404, detail="Stack not found")

    # Verify all book IDs belong to this stack
    existing = conn.execute(
        "SELECT id FROM book WHERE stack_id = ? ORDER BY position", (stack_id,)
    ).fetchall()
    existing_ids = {r["id"] for r in existing}

    if set(body.book_ids) != existing_ids:
        conn.close()
        raise HTTPException(
            status_code=400,
            detail="book_ids must contain exactly the books in this stack",
        )

    try:
        # Use negative temporary positions to avoid unique constraint conflicts
        for i, book_id in enumerate(body.book_ids):
            conn.execute(
                "UPDATE book SET position = ? WHERE id = ?", (-(i + 1), book_id)
            )
        for i, book_id in enumerate(body.book_ids):
            conn.execute(
                "UPDATE book SET position = ? WHERE id = ?", (i, book_id)
            )
        conn.commit()
    except Exception as e:
        conn.rollback()
        conn.close()
        raise HTTPException(status_code=500, detail=str(e))

    books = conn.execute(
        "SELECT id, title, author, publisher, stack_id, position FROM book WHERE stack_id = ? ORDER BY position",
        (stack_id,),
    ).fetchall()
    conn.close()
    return {"id": stack["id"], "name": stack["name"], "books": [dict(b) for b in books]}


app.include_router(api)


# --- Frontend Routes ---

@app.get("/", include_in_schema=False)
def root():
    return FileResponse("static/index.html")


@app.get("/{path:path}", include_in_schema=False)
def frontend_catchall(path: str):
    return FileResponse("static/index.html")


app.mount("/static", StaticFiles(directory="static"), name="static")
