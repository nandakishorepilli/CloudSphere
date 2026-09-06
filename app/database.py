"""SQLite setup and data access helpers for Cloud Sphere."""
from __future__ import annotations

import sqlite3
import os
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
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                full_name TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('admin', 'user')),
                is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_login_at TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS otp_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                code_hash TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                used_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token_hash TEXT NOT NULL UNIQUE,
                user_id INTEGER NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                user_email TEXT NOT NULL,
                action TEXT NOT NULL,
                details TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
            """
        )
        admin_email = os.getenv("CLOUDSPHERE_ADMIN_EMAIL", "admin@cloudsphere.com").strip().lower()
        connection.execute(
            """INSERT OR IGNORE INTO users (email, full_name, role, is_active)
               VALUES (?, ?, 'admin', 1)""",
            (admin_email, "Cloud Sphere Administrator"),
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
