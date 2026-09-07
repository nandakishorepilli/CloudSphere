"""SQLite setup and additive schema migrations for Cloud Sphere."""
from __future__ import annotations
import os
import sqlite3
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIRECTORY = PROJECT_ROOT / "data"
DATABASE_PATH = DATA_DIRECTORY / "cloudsphere.db"
APPROVED_COURSES = ("IT", "AI&ML", "CSE", "AI", "DS", "ECE", "EEE", "CIVIL", "MECH")
SAMPLE_STUDENTS = [("Aarav Sharma", "aarav.sharma@cloudsphere.edu", "+91 98765 43210", "Computer Science", 3), ("Priya Patel", "priya.patel@cloudsphere.edu", "+91 98765 43211", "Business Administration", 2), ("Rohan Mehta", "rohan.mehta@cloudsphere.edu", "+91 98765 43212", "Mechanical Engineering", 4), ("Ananya Iyer", "ananya.iyer@cloudsphere.edu", "+91 98765 43213", "Computer Science", 1), ("Vikram Singh", "vikram.singh@cloudsphere.edu", "+91 98765 43214", "Economics", 3)]

def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection

def _has_column(connection: sqlite3.Connection, table: str, column: str) -> bool:
    return column in {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}

def normalize_course_name(value: str) -> str:
    return " ".join(value.split()).casefold()

def initialize_database() -> None:
    """Create missing structures and add columns without altering existing data."""
    DATA_DIRECTORY.mkdir(parents=True, exist_ok=True)
    with get_connection() as c:
        c.execute("CREATE TABLE IF NOT EXISTS students (id INTEGER PRIMARY KEY AUTOINCREMENT, full_name TEXT NOT NULL, email TEXT NOT NULL UNIQUE, phone TEXT NOT NULL, department TEXT NOT NULL, year INTEGER NOT NULL CHECK (year BETWEEN 1 AND 10), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
        c.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT NOT NULL UNIQUE COLLATE NOCASE, full_name TEXT NOT NULL, role TEXT NOT NULL CHECK (role IN ('admin', 'user')), is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, last_login_at TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS otp_codes (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, code_hash TEXT NOT NULL, expires_at TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, used_at TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (user_id) REFERENCES users(id))")
        c.execute("CREATE TABLE IF NOT EXISTS sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, token_hash TEXT NOT NULL UNIQUE, user_id INTEGER NOT NULL, expires_at TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (user_id) REFERENCES users(id))")
        c.execute("CREATE TABLE IF NOT EXISTS audit_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, user_email TEXT NOT NULL, action TEXT NOT NULL, details TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (user_id) REFERENCES users(id))")
        c.execute("CREATE TABLE IF NOT EXISTS courses (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, normalized_name TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
        # Retain the earlier aggregate table for compatibility; date-based records below are authoritative.
        c.execute("CREATE TABLE IF NOT EXISTS attendance (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, course_id INTEGER NOT NULL, total_classes INTEGER NOT NULL CHECK(total_classes >= 0), classes_attended INTEGER NOT NULL CHECK(classes_attended >= 0 AND classes_attended <= total_classes), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(user_id, course_id), FOREIGN KEY(user_id) REFERENCES users(id), FOREIGN KEY(course_id) REFERENCES courses(id))")
        if not _has_column(c, "students", "roll_number"):
            c.execute("ALTER TABLE students ADD COLUMN roll_number TEXT")
        if not _has_column(c, "students", "course_id"):
            c.execute("ALTER TABLE students ADD COLUMN course_id INTEGER REFERENCES courses(id)")
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_students_roll_number ON students(roll_number) WHERE roll_number IS NOT NULL")
        c.execute("CREATE INDEX IF NOT EXISTS idx_students_course_id ON students(course_id)")
        c.execute("CREATE TABLE IF NOT EXISTS attendance_records (id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER NOT NULL, course_id INTEGER NOT NULL, attendance_date TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('present','absent')), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(student_id, course_id, attendance_date), FOREIGN KEY(student_id) REFERENCES students(id), FOREIGN KEY(course_id) REFERENCES courses(id))")
        c.execute("CREATE INDEX IF NOT EXISTS idx_attendance_course_date ON attendance_records(course_id, attendance_date)")
        for name in APPROVED_COURSES:
            c.execute("INSERT OR IGNORE INTO courses (name, normalized_name) VALUES (?, ?)", (name, normalize_course_name(name)))
        admin_email = os.getenv("CLOUDSPHERE_ADMIN_EMAIL", "admin@cloudsphere.com").strip().lower()
        c.execute("INSERT OR IGNORE INTO users (email, full_name, role, is_active) VALUES (?, ?, 'admin', 1)", (admin_email, "Cloud Sphere Administrator"))
        if c.execute("SELECT COUNT(*) FROM students").fetchone()[0] == 0:
            c.executemany("INSERT INTO students (full_name,email,phone,department,year) VALUES (?,?,?,?,?)", SAMPLE_STUDENTS)

def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row else None
