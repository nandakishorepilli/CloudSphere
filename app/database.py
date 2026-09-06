"""SQLite setup and data access helpers for Cloud Sphere."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIRECTORY = PROJECT_ROOT / "data"
DATABASE_PATH = DATA_DIRECTORY / "cloudsphere.db"

SAMPLE_STUDENTS = [
    ("Aarav Sharma", "aarav.sharma@cloudsphere.edu", "+91 98765 43210", "Computer Science", 3),
    ("Priya Patel", "priya.patel@cloudsphere.edu", "+91 98765 43211", "Business Administration", 2),
    ("Rohan Mehta", "rohan.mehta@cloudsphere.edu", "+91 98765 43212", "Mechanical Engineering", 4),
    ("Ananya Iyer", "ananya.iyer@cloudsphere.edu", "+91 98765 43213", "Computer Science", 1),
    ("Vikram Singh", "vikram.singh@cloudsphere.edu", "+91 98765 43214", "Economics", 3),
]


def get_connection() -> sqlite3.Connection:
    """Return a SQLite connection whose rows behave like dictionaries."""
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database() -> None:
    """Create the local database, schema, and starter data on first launch."""
    DATA_DIRECTORY.mkdir(parents=True, exist_ok=True)
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                phone TEXT NOT NULL,
                department TEXT NOT NULL,
                year INTEGER NOT NULL CHECK (year BETWEEN 1 AND 10),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        existing = connection.execute("SELECT COUNT(*) FROM students").fetchone()[0]
        if existing == 0:
            connection.executemany(
                """
                INSERT INTO students (full_name, email, phone, department, year)
                VALUES (?, ?, ?, ?, ?)
                """,
                SAMPLE_STUDENTS,
            )


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row else None
