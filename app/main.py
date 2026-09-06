"""FastAPI application for the Cloud Sphere local prototype."""
from contextlib import asynccontextmanager
import sqlite3
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .database import get_connection, initialize_database, row_to_dict
from .schemas import Student, StudentCreate, StudentUpdate

APP_DIRECTORY = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield


app = FastAPI(title="Cloud Sphere", version="0.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=APP_DIRECTORY / "static"), name="static")


def get_student_or_404(student_id: int) -> dict:
    with get_connection() as connection:
        student = connection.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
    result = row_to_dict(student)
    if result is None:
        raise HTTPException(status_code=404, detail="Student not found")
    return result


@app.get("/", include_in_schema=False)
def homepage() -> FileResponse:
    return FileResponse(APP_DIRECTORY / "templates" / "index.html")


@app.get("/api/students", response_model=list[Student])
def list_students(search: str = Query(default="", max_length=100)) -> list[dict]:
    statement = "SELECT * FROM students"
    parameters: tuple = ()
    if search.strip():
        term = f"%{search.strip()}%"
        statement += " WHERE full_name LIKE ? OR email LIKE ? OR department LIKE ?"
        parameters = (term, term, term)
    statement += " ORDER BY datetime(created_at) DESC, id DESC"
    with get_connection() as connection:
        rows = connection.execute(statement, parameters).fetchall()
    return [dict(row) for row in rows]


@app.get("/api/students/{student_id}", response_model=Student)
def get_student(student_id: int) -> dict:
    return get_student_or_404(student_id)


@app.post("/api/students", response_model=Student, status_code=201)
def create_student(payload: StudentCreate) -> dict:
    try:
        with get_connection() as connection:
            cursor = connection.execute(
                """INSERT INTO students (full_name, email, phone, department, year)
                   VALUES (?, ?, ?, ?, ?)""",
                (payload.full_name.strip(), str(payload.email), payload.phone.strip(), payload.department.strip(), payload.year),
            )
            row = connection.execute("SELECT * FROM students WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return dict(row)
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="A student with this email already exists")


@app.put("/api/students/{student_id}", response_model=Student)
def update_student(student_id: int, payload: StudentUpdate) -> dict:
    get_student_or_404(student_id)
    try:
        with get_connection() as connection:
            connection.execute(
                """UPDATE students SET full_name = ?, email = ?, phone = ?, department = ?, year = ?
                   WHERE id = ?""",
                (payload.full_name.strip(), str(payload.email), payload.phone.strip(), payload.department.strip(), payload.year, student_id),
            )
            row = connection.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
        return dict(row)
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="A student with this email already exists")


@app.delete("/api/students/{student_id}", status_code=204)
def delete_student(student_id: int) -> Response:
    get_student_or_404(student_id)
    with get_connection() as connection:
        connection.execute("DELETE FROM students WHERE id = ?", (student_id,))
    return Response(status_code=204)


@app.get("/api/dashboard")
def dashboard_statistics() -> dict:
    with get_connection() as connection:
        total_students = connection.execute("SELECT COUNT(*) FROM students").fetchone()[0]
        total_departments = connection.execute("SELECT COUNT(DISTINCT department) FROM students").fetchone()[0]
        by_department = connection.execute("SELECT department, COUNT(*) AS count FROM students GROUP BY department ORDER BY count DESC, department").fetchall()
        by_year = connection.execute("SELECT year, COUNT(*) AS count FROM students GROUP BY year ORDER BY year").fetchall()
        recent = connection.execute("SELECT * FROM students ORDER BY datetime(created_at) DESC, id DESC LIMIT 5").fetchall()
    return {
        "database_status": "Connected",
        "total_students": total_students,
        "total_departments": total_departments,
        "by_department": [dict(row) for row in by_department],
        "by_year": [dict(row) for row in by_year],
        "recent_students": [dict(row) for row in recent],
    }
