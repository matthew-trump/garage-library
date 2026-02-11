import sqlite3
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
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
    location: str | None


class StackDetail(BaseModel):
    id: int
    name: str
    location: str | None
    books: list[Book]


# --- API Routes ---

api = APIRouter(prefix="/api")


@api.get("/books", response_model=list[Book])
def list_books():
    conn = get_db()
    rows = conn.execute("SELECT id, title, author, publisher, stack_id, position FROM book").fetchall()
    conn.close()
    return [dict(r) for r in rows]


class BookSearchResult(BaseModel):
    id: int
    title: str
    author: str | None
    publisher: str | None
    stack_id: int
    stack_name: str


@api.get("/books/search", response_model=list[BookSearchResult])
def search_books(
    q: str = Query(..., min_length=1),
    title: bool = Query(True),
    author: bool = Query(True),
    publisher: bool = Query(False),
):
    if not (title or author or publisher):
        raise HTTPException(status_code=400, detail="At least one search field must be selected")

    conn = get_db()
    conditions = []
    params = []
    if title:
        conditions.append("b.title LIKE ?")
        params.append(f"%{q}%")
    if author:
        conditions.append("b.author LIKE ?")
        params.append(f"%{q}%")
    if publisher:
        conditions.append("b.publisher LIKE ?")
        params.append(f"%{q}%")

    where = " OR ".join(conditions)
    rows = conn.execute(
        f"SELECT b.id, b.title, b.author, b.publisher, b.stack_id, s.name as stack_name "
        f"FROM book b JOIN stack s ON b.stack_id = s.id "
        f"WHERE {where} ORDER BY b.title",
        params,
    ).fetchall()
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
    rows = conn.execute("SELECT id, name, location FROM stack").fetchall()
    conn.close()
    return [dict(r) for r in rows]


@api.get("/stack/{stack_id}", response_model=StackDetail)
def get_stack(stack_id: int):
    conn = get_db()
    stack = conn.execute("SELECT id, name, location FROM stack WHERE id = ?", (stack_id,)).fetchone()
    if stack is None:
        conn.close()
        raise HTTPException(status_code=404, detail="Stack not found")
    books = conn.execute(
        "SELECT id, title, author, publisher, stack_id, position FROM book WHERE stack_id = ? ORDER BY position",
        (stack_id,),
    ).fetchall()
    conn.close()
    return {"id": stack["id"], "name": stack["name"], "location": stack["location"], "books": [dict(b) for b in books]}


class StackCreate(BaseModel):
    name: str
    location: str | None = None


@api.post("/stack", response_model=Stack, status_code=201)
def create_stack(body: StackCreate):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Stack name cannot be empty")

    location = body.location.strip() if body.location else None

    conn = get_db()
    existing = conn.execute("SELECT id FROM stack WHERE name = ?", (name,)).fetchone()
    if existing:
        conn.close()
        raise HTTPException(status_code=400, detail="A stack with that name already exists")

    try:
        cur = conn.execute("INSERT INTO stack (name, location) VALUES (?, ?)", (name, location))
        conn.commit()
        stack_id = cur.lastrowid
    except Exception as e:
        conn.rollback()
        conn.close()
        raise HTTPException(status_code=500, detail=str(e))

    conn.close()
    return {"id": stack_id, "name": name, "location": location}


class BookCreate(BaseModel):
    title: str
    author: str | None = None
    publisher: str | None = None
    stack_id: int
    position: str = "end"  # "beginning" or "end"


@api.post("/book", response_model=Book, status_code=201)
def create_book(body: BookCreate):
    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title cannot be empty")

    if body.position not in ("beginning", "end"):
        raise HTTPException(status_code=400, detail="position must be 'beginning' or 'end'")

    conn = get_db()
    stack = conn.execute("SELECT id FROM stack WHERE id = ?", (body.stack_id,)).fetchone()
    if stack is None:
        conn.close()
        raise HTTPException(status_code=400, detail="Stack not found")

    try:
        existing = conn.execute(
            "SELECT id, position FROM book WHERE stack_id = ? ORDER BY position",
            (body.stack_id,),
        ).fetchall()

        if body.position == "beginning":
            # Shift existing books up to make room at position 0
            for b in existing:
                conn.execute(
                    "UPDATE book SET position = ? WHERE id = ?",
                    (-(b["position"] + 2), b["id"]),
                )
            for b in existing:
                conn.execute(
                    "UPDATE book SET position = ? WHERE id = ?",
                    (b["position"] + 1, b["id"]),
                )
            new_pos = 0
        else:
            new_pos = len(existing)

        cur = conn.execute(
            "INSERT INTO book (title, author, publisher, stack_id, position) VALUES (?, ?, ?, ?, ?)",
            (title, body.author, body.publisher, body.stack_id, new_pos),
        )
        conn.commit()
        book_id = cur.lastrowid
    except Exception as e:
        conn.rollback()
        conn.close()
        raise HTTPException(status_code=500, detail=str(e))

    row = conn.execute(
        "SELECT id, title, author, publisher, stack_id, position FROM book WHERE id = ?",
        (book_id,),
    ).fetchone()
    conn.close()
    return dict(row)


class BookUpdate(BaseModel):
    title: str
    author: str | None = None
    publisher: str | None = None
    stack_id: int | None = None


@api.put("/book/{book_id}", response_model=Book)
def update_book(book_id: int, body: BookUpdate):
    conn = get_db()
    row = conn.execute(
        "SELECT id, stack_id, position FROM book WHERE id = ?", (book_id,)
    ).fetchone()
    if row is None:
        conn.close()
        raise HTTPException(status_code=404, detail="Book not found")

    if not body.title.strip():
        conn.close()
        raise HTTPException(status_code=400, detail="Title cannot be empty")

    new_stack_id = body.stack_id if body.stack_id is not None else row["stack_id"]

    # Validate target stack exists
    if new_stack_id != row["stack_id"]:
        target_stack = conn.execute(
            "SELECT id FROM stack WHERE id = ?", (new_stack_id,)
        ).fetchone()
        if target_stack is None:
            conn.close()
            raise HTTPException(status_code=400, detail="Target stack not found")

    try:
        if new_stack_id != row["stack_id"]:
            old_stack_id = row["stack_id"]
            old_position = row["position"]

            # Move the book to a temporary position to avoid conflicts
            conn.execute(
                "UPDATE book SET position = -1, stack_id = ? WHERE id = ?",
                (new_stack_id, book_id),
            )

            # Shift books in old stack down to fill the gap
            old_books = conn.execute(
                "SELECT id, position FROM book WHERE stack_id = ? AND position > ? ORDER BY position",
                (old_stack_id, old_position),
            ).fetchall()
            for b in old_books:
                conn.execute(
                    "UPDATE book SET position = ? WHERE id = ?",
                    (-(b["position"] + 1), b["id"]),
                )
            for b in old_books:
                conn.execute(
                    "UPDATE book SET position = ? WHERE id = ?",
                    (b["position"] - 1, b["id"]),
                )

            # Shift books in new stack up to make room at position 0
            new_books = conn.execute(
                "SELECT id, position FROM book WHERE stack_id = ? AND id != ? ORDER BY position",
                (new_stack_id, book_id),
            ).fetchall()
            for b in new_books:
                conn.execute(
                    "UPDATE book SET position = ? WHERE id = ?",
                    (-(b["position"] + 2), b["id"]),
                )
            for b in new_books:
                conn.execute(
                    "UPDATE book SET position = ? WHERE id = ?",
                    (b["position"] + 1, b["id"]),
                )

            # Place the book at position 0 with updated fields
            conn.execute(
                "UPDATE book SET title = ?, author = ?, publisher = ?, position = 0 WHERE id = ?",
                (body.title.strip(), body.author, body.publisher, book_id),
            )
        else:
            conn.execute(
                "UPDATE book SET title = ?, author = ?, publisher = ? WHERE id = ?",
                (body.title.strip(), body.author, body.publisher, book_id),
            )
        conn.commit()
    except Exception as e:
        conn.rollback()
        conn.close()
        raise HTTPException(status_code=500, detail=str(e))

    updated = conn.execute(
        "SELECT id, title, author, publisher, stack_id, position FROM book WHERE id = ?",
        (book_id,),
    ).fetchone()
    conn.close()
    return dict(updated)


class StackUpdate(BaseModel):
    name: str
    location: str | None = None


@api.patch("/stack/{stack_id}", response_model=Stack)
def update_stack(stack_id: int, body: StackUpdate):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Stack name cannot be empty")

    location = body.location.strip() if body.location else None

    conn = get_db()
    stack = conn.execute("SELECT id, name FROM stack WHERE id = ?", (stack_id,)).fetchone()
    if stack is None:
        conn.close()
        raise HTTPException(status_code=404, detail="Stack not found")

    # Check name uniqueness if changed
    if name != stack["name"]:
        dup = conn.execute("SELECT id FROM stack WHERE name = ? AND id != ?", (name, stack_id)).fetchone()
        if dup:
            conn.close()
            raise HTTPException(status_code=400, detail="A stack with that name already exists")

    try:
        conn.execute("UPDATE stack SET name = ?, location = ? WHERE id = ?", (name, location, stack_id))
        conn.commit()
    except Exception as e:
        conn.rollback()
        conn.close()
        raise HTTPException(status_code=500, detail=str(e))

    conn.close()
    return {"id": stack_id, "name": name, "location": location}


class ReorderRequest(BaseModel):
    book_ids: list[int]


@api.put("/stack/{stack_id}", response_model=StackDetail)
def reorder_stack(stack_id: int, body: ReorderRequest):
    conn = get_db()
    stack = conn.execute("SELECT id, name, location FROM stack WHERE id = ?", (stack_id,)).fetchone()
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
    return {"id": stack["id"], "name": stack["name"], "location": stack["location"], "books": [dict(b) for b in books]}


app.include_router(api)


# --- Frontend Routes ---

@app.get("/", include_in_schema=False)
def root():
    return FileResponse("static/index.html")


app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/{path:path}", include_in_schema=False)
def frontend_catchall(path: str):
    return FileResponse("static/index.html")
