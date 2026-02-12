import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import bcrypt
import jwt
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.routing import APIRouter
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-do-not-use-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 24

DB_PATH = Path(__file__).parent / "garage-library.db"

app = FastAPI(title="Garage Library API")


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute(
        """CREATE TABLE IF NOT EXISTS user (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL
        )"""
    )
    conn.commit()

    # Migration: add level column
    try:
        conn.execute("ALTER TABLE user ADD COLUMN level INTEGER NOT NULL DEFAULT 1")
        conn.commit()
    except Exception:
        pass  # column already exists

    # Ensure matthewtrump is admin
    conn.execute("UPDATE user SET level = 2 WHERE username = 'matthewtrump'")
    conn.commit()

    # Migration: add user_id column to book
    try:
        conn.execute("ALTER TABLE book ADD COLUMN user_id INTEGER REFERENCES user(id)")
        conn.commit()
    except Exception:
        pass  # column already exists

    # Set all existing books to user_id 2
    conn.execute("UPDATE book SET user_id = 2 WHERE user_id IS NULL")
    conn.commit()

    # Migration: add user_id column to stack
    try:
        conn.execute("ALTER TABLE stack ADD COLUMN user_id INTEGER REFERENCES user(id)")
        conn.commit()
    except Exception:
        pass  # column already exists

    # Set all existing stacks to user_id 2
    conn.execute("UPDATE stack SET user_id = 2 WHERE user_id IS NULL")
    conn.commit()
    conn.close()


init_db()


# --- JWT Helpers ---

USERNAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*$")


def create_token(user_id: int, username: str, level: int) -> str:
    payload = {
        "sub": str(user_id),
        "username": username,
        "level": level,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def require_auth(authorization: str):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    return payload


def require_admin(authorization: str):
    payload = require_auth(authorization)
    if payload.get("level", 1) < 2:
        raise HTTPException(status_code=403, detail="Admin access required")
    return payload


def validate_username(username: str) -> str:
    if not (3 <= len(username) <= 24):
        raise HTTPException(status_code=400, detail="Username must be 3-24 characters")
    if not USERNAME_RE.match(username):
        raise HTTPException(
            status_code=400,
            detail="Username must start with a letter and contain only letters, digits, and underscores",
        )
    return username.lower()


def validate_password(password: str):
    if not (8 <= len(password) <= 128):
        raise HTTPException(status_code=400, detail="Password must be 8-128 characters")
    if not re.search(r"[A-Z]", password):
        raise HTTPException(status_code=400, detail="Password must contain at least one uppercase letter")
    if not re.search(r"[a-z]", password):
        raise HTTPException(status_code=400, detail="Password must contain at least one lowercase letter")
    if not re.search(r"[0-9]", password):
        raise HTTPException(status_code=400, detail="Password must contain at least one digit")


# --- Models ---

class Book(BaseModel):
    id: int
    title: str
    author: str | None
    publisher: str | None
    year: str | None
    stack_id: int
    position: int
    user_id: int | None


class Stack(BaseModel):
    id: int
    name: str
    location: str | None
    user_id: int | None


class StackDetail(BaseModel):
    id: int
    name: str
    location: str | None
    user_id: int | None
    books: list[Book]


class UserCreate(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    id: int
    username: str
    level: int


class UserLogin(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    token: str


# --- API Routes ---

api = APIRouter(prefix="/api")


@api.post("/register", response_model=UserResponse, status_code=201)
def register(body: UserCreate):
    username = validate_username(body.username)
    validate_password(body.password)

    password_hash = bcrypt.hashpw(body.password.encode(), bcrypt.gensalt()).decode()

    conn = get_db()
    existing = conn.execute("SELECT id FROM user WHERE username = ?", (username,)).fetchone()
    if existing:
        conn.close()
        raise HTTPException(status_code=400, detail="Username already taken")

    try:
        cur = conn.execute(
            "INSERT INTO user (username, password_hash) VALUES (?, ?)",
            (username, password_hash),
        )
        conn.commit()
        user_id = cur.lastrowid
    except Exception as e:
        conn.rollback()
        conn.close()
        raise HTTPException(status_code=500, detail=str(e))

    conn.close()
    return {"id": user_id, "username": username, "level": 1}


@api.post("/login", response_model=TokenResponse)
def login(body: UserLogin):
    username = body.username.strip().lower()
    conn = get_db()
    row = conn.execute(
        "SELECT id, username, password_hash, level FROM user WHERE username = ?", (username,)
    ).fetchone()
    conn.close()

    if row is None or not bcrypt.checkpw(body.password.encode(), row["password_hash"].encode()):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = create_token(row["id"], row["username"], row["level"])
    return {"token": token}


@api.get("/users", response_model=list[UserResponse])
def list_users(authorization: str = Header(...)):
    require_admin(authorization)
    conn = get_db()
    rows = conn.execute("SELECT id, username, level FROM user").fetchall()
    conn.close()
    return [dict(r) for r in rows]



@api.get("/books", response_model=list[Book])
def list_books():
    conn = get_db()
    rows = conn.execute("SELECT id, title, author, publisher, year, stack_id, position, user_id FROM book").fetchall()
    conn.close()
    return [dict(r) for r in rows]


class BookSearchResult(BaseModel):
    id: int
    title: str
    author: str | None
    publisher: str | None
    year: str | None
    stack_id: int
    stack_name: str
    user_id: int | None


@api.get("/books/search", response_model=list[BookSearchResult])
def search_books(
    q: str = Query(..., min_length=1),
    title: bool = Query(True),
    author: bool = Query(True),
    publisher: bool = Query(False),
    year: bool = Query(False),
    user_id: int | None = Query(None),
    authorization: str = Header(...),
):
    caller = require_auth(authorization)
    caller_level = caller.get("level", 1)
    caller_id = int(caller["sub"])

    # Determine which user_id to filter by
    if caller_level >= 2:
        search_user_id = user_id if user_id is not None else caller_id
    else:
        # Level 1: always search own books, ignore any user_id param
        search_user_id = caller_id

    if not (title or author or publisher or year):
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
    if year:
        conditions.append("b.year LIKE ?")
        params.append(f"%{q}%")

    where = f"({' OR '.join(conditions)}) AND b.user_id = ?"
    params.append(search_user_id)
    rows = conn.execute(
        f"SELECT b.id, b.title, b.author, b.publisher, b.year, b.stack_id, s.name as stack_name, b.user_id "
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
        "SELECT id, title, author, publisher, year, stack_id, position, user_id FROM book WHERE id = ?",
        (book_id,),
    ).fetchone()
    conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="Book not found")
    return dict(row)


@api.get("/stacks", response_model=list[Stack])
def list_stacks(authorization: str = Header(...)):
    caller = require_auth(authorization)
    caller_id = int(caller["sub"])
    conn = get_db()
    rows = conn.execute("SELECT id, name, location, user_id FROM stack WHERE user_id = ?", (caller_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@api.get("/stack/{stack_id}", response_model=StackDetail)
def get_stack(stack_id: int, authorization: str = Header(...)):
    caller = require_auth(authorization)
    caller_id = int(caller["sub"])
    conn = get_db()
    stack = conn.execute("SELECT id, name, location, user_id FROM stack WHERE id = ? AND user_id = ?", (stack_id, caller_id)).fetchone()
    if stack is None:
        conn.close()
        raise HTTPException(status_code=404, detail="Stack not found")
    books = conn.execute(
        "SELECT id, title, author, publisher, year, stack_id, position, user_id FROM book WHERE stack_id = ? ORDER BY position",
        (stack_id,),
    ).fetchall()
    conn.close()
    return {"id": stack["id"], "name": stack["name"], "location": stack["location"], "user_id": stack["user_id"], "books": [dict(b) for b in books]}


class StackCreate(BaseModel):
    name: str
    location: str | None = None
    user_id: int | None = None


@api.post("/stack", response_model=Stack, status_code=201)
def create_stack(body: StackCreate, authorization: str = Header(...)):
    caller = require_auth(authorization)
    caller_level = caller.get("level", 1)
    caller_id = int(caller["sub"])

    if caller_level >= 2:
        stack_user_id = body.user_id if body.user_id is not None else caller_id
    else:
        if body.user_id is not None:
            raise HTTPException(status_code=400, detail="Normal users cannot specify user_id")
        stack_user_id = caller_id

    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Stack name cannot be empty")

    location = body.location.strip() if body.location else None

    conn = get_db()

    # Validate user_id exists
    target_user = conn.execute("SELECT id FROM user WHERE id = ?", (stack_user_id,)).fetchone()
    if target_user is None:
        conn.close()
        raise HTTPException(status_code=400, detail="User not found")

    existing = conn.execute("SELECT id FROM stack WHERE name = ?", (name,)).fetchone()
    if existing:
        conn.close()
        raise HTTPException(status_code=400, detail="A stack with that name already exists")

    try:
        cur = conn.execute("INSERT INTO stack (name, location, user_id) VALUES (?, ?, ?)", (name, location, stack_user_id))
        conn.commit()
        stack_id = cur.lastrowid
    except Exception as e:
        conn.rollback()
        conn.close()
        raise HTTPException(status_code=500, detail=str(e))

    conn.close()
    return {"id": stack_id, "name": name, "location": location, "user_id": stack_user_id}


class BookCreate(BaseModel):
    title: str
    author: str | None = None
    publisher: str | None = None
    year: str | None = None
    stack_id: int
    position: str = "end"  # "beginning" or "end"
    user_id: int | None = None


@api.post("/book", response_model=Book, status_code=201)
def create_book(body: BookCreate, authorization: str = Header(...)):
    caller = require_auth(authorization)
    caller_level = caller.get("level", 1)
    caller_id = int(caller["sub"])

    # Determine user_id for the new book
    if caller_level >= 2:
        # Admin: accept user_id if provided, default to caller
        book_user_id = body.user_id if body.user_id is not None else caller_id
    else:
        # Normal user: must not pass user_id
        if body.user_id is not None:
            raise HTTPException(status_code=400, detail="Normal users cannot specify user_id")
        book_user_id = caller_id

    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title cannot be empty")

    if body.position not in ("beginning", "end"):
        raise HTTPException(status_code=400, detail="position must be 'beginning' or 'end'")

    conn = get_db()

    # Validate user_id exists
    target_user = conn.execute("SELECT id FROM user WHERE id = ?", (book_user_id,)).fetchone()
    if target_user is None:
        conn.close()
        raise HTTPException(status_code=400, detail="User not found")

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
            "INSERT INTO book (title, author, publisher, year, stack_id, position, user_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (title, body.author, body.publisher, body.year, body.stack_id, new_pos, book_user_id),
        )
        conn.commit()
        book_id = cur.lastrowid
    except Exception as e:
        conn.rollback()
        conn.close()
        raise HTTPException(status_code=500, detail=str(e))

    row = conn.execute(
        "SELECT id, title, author, publisher, year, stack_id, position, user_id FROM book WHERE id = ?",
        (book_id,),
    ).fetchone()
    conn.close()
    return dict(row)


class BookUpdate(BaseModel):
    title: str
    author: str | None = None
    publisher: str | None = None
    year: str | None = None
    stack_id: int | None = None
    user_id: int | None = None


@api.put("/book/{book_id}", response_model=Book)
def update_book(book_id: int, body: BookUpdate, authorization: str = Header(...)):
    caller = require_auth(authorization)
    caller_level = caller.get("level", 1)

    if caller_level < 2 and body.user_id is not None:
        raise HTTPException(status_code=400, detail="Normal users cannot specify user_id")

    if caller_level >= 2 and body.user_id is not None:
        conn_check = get_db()
        target_user = conn_check.execute("SELECT id FROM user WHERE id = ?", (body.user_id,)).fetchone()
        conn_check.close()
        if target_user is None:
            raise HTTPException(status_code=400, detail="User not found")

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
            if body.user_id is not None:
                conn.execute(
                    "UPDATE book SET title = ?, author = ?, publisher = ?, year = ?, position = 0, user_id = ? WHERE id = ?",
                    (body.title.strip(), body.author, body.publisher, body.year, body.user_id, book_id),
                )
            else:
                conn.execute(
                    "UPDATE book SET title = ?, author = ?, publisher = ?, year = ?, position = 0 WHERE id = ?",
                    (body.title.strip(), body.author, body.publisher, body.year, book_id),
                )
        else:
            if body.user_id is not None:
                conn.execute(
                    "UPDATE book SET title = ?, author = ?, publisher = ?, year = ?, user_id = ? WHERE id = ?",
                    (body.title.strip(), body.author, body.publisher, body.year, body.user_id, book_id),
                )
            else:
                conn.execute(
                    "UPDATE book SET title = ?, author = ?, publisher = ?, year = ? WHERE id = ?",
                    (body.title.strip(), body.author, body.publisher, body.year, book_id),
                )
        conn.commit()
    except Exception as e:
        conn.rollback()
        conn.close()
        raise HTTPException(status_code=500, detail=str(e))

    updated = conn.execute(
        "SELECT id, title, author, publisher, year, stack_id, position, user_id FROM book WHERE id = ?",
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
    stack = conn.execute("SELECT id, name, user_id FROM stack WHERE id = ?", (stack_id,)).fetchone()
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
    return {"id": stack_id, "name": name, "location": location, "user_id": stack["user_id"]}


class ReorderRequest(BaseModel):
    book_ids: list[int]


@api.put("/stack/{stack_id}", response_model=StackDetail)
def reorder_stack(stack_id: int, body: ReorderRequest):
    conn = get_db()
    stack = conn.execute("SELECT id, name, location, user_id FROM stack WHERE id = ?", (stack_id,)).fetchone()
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
        "SELECT id, title, author, publisher, year, stack_id, position, user_id FROM book WHERE stack_id = ? ORDER BY position",
        (stack_id,),
    ).fetchall()
    conn.close()
    return {"id": stack["id"], "name": stack["name"], "location": stack["location"], "user_id": stack["user_id"], "books": [dict(b) for b in books]}


app.include_router(api)


# --- Frontend Routes ---

@app.get("/", include_in_schema=False)
def root():
    return FileResponse("static/index.html")


app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/{path:path}", include_in_schema=False)
def frontend_catchall(path: str):
    return FileResponse("static/index.html")
