"""FastAPI application for the Cloud Sphere local prototype."""
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
import secrets
import sqlite3

from fastapi import Cookie, Depends, FastAPI, HTTPException, Query, Response, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .database import get_connection, initialize_database, row_to_dict
from .otp_service import DEVELOPMENT_MODE, MAX_OTP_ATTEMPTS, OTP_TTL_MINUTES, generate_otp, hash_secret, send_otp
from .schemas import ManagedUserCreate, ManagedUserUpdate, OtpRequest, OtpVerify, Student, StudentCreate, StudentUpdate

APP_DIRECTORY = Path(__file__).resolve().parent

@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield

app = FastAPI(title="Cloud Sphere", version="0.2.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=APP_DIRECTORY / "static"), name="static")

def now() -> datetime: return datetime.now(timezone.utc)
def date(value: datetime) -> str: return value.strftime("%Y-%m-%d %H:%M:%S")

def audit(user: dict | None, action: str, details: str = "") -> None:
    with get_connection() as con:
        con.execute("INSERT INTO audit_logs (user_id, user_email, action, details) VALUES (?, ?, ?, ?)", (user["id"] if user else None, user["email"] if user else "system", action, details))

def current_user(session_token: str | None = Cookie(default=None)) -> dict:
    if not session_token: raise HTTPException(401, "Authentication required")
    with get_connection() as con:
        row = con.execute("""SELECT users.* FROM sessions JOIN users ON users.id=sessions.user_id
            WHERE sessions.token_hash=? AND datetime(sessions.expires_at)>datetime('now')""", (hash_secret(session_token),)).fetchone()
    user = row_to_dict(row)
    if not user or not user["is_active"]: raise HTTPException(401, "Your session is no longer active")
    return user

def require_admin(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "admin": raise HTTPException(403, "Administrator access required")
    return user

def get_student_or_404(student_id: int) -> dict:
    with get_connection() as con: row = con.execute("SELECT * FROM students WHERE id=?", (student_id,)).fetchone()
    result = row_to_dict(row)
    if not result: raise HTTPException(404, "Student not found")
    return result

@app.get("/", include_in_schema=False)
def login_page(): return FileResponse(APP_DIRECTORY / "templates" / "login.html")
@app.get("/dashboard", include_in_schema=False)
def user_dashboard(_: dict = Depends(current_user)): return FileResponse(APP_DIRECTORY / "templates" / "index.html")
@app.get("/admin", include_in_schema=False)
def admin_dashboard(_: dict = Depends(require_admin)): return FileResponse(APP_DIRECTORY / "templates" / "admin.html")

@app.post("/api/auth/request-otp")
def request_otp(payload: OtpRequest) -> dict:
    email = str(payload.email).lower()
    with get_connection() as con:
        user = row_to_dict(con.execute("SELECT * FROM users WHERE email=? AND role=?", (email, payload.role)).fetchone())
        if not user or not user["is_active"]: raise HTTPException(403, "This email is not an active account for the selected login.")
        code = generate_otp()
        con.execute("UPDATE otp_codes SET used_at=CURRENT_TIMESTAMP WHERE user_id=? AND used_at IS NULL", (user["id"],))
        con.execute("INSERT INTO otp_codes (user_id, code_hash, expires_at) VALUES (?, ?, ?)", (user["id"], hash_secret(code), date(now() + timedelta(minutes=OTP_TTL_MINUTES))))
    try: send_otp(email, code)
    except RuntimeError: raise HTTPException(503, "OTP email delivery is not configured.")
    result = {"message": "A one-time code was sent. It expires in 5 minutes."}
    if DEVELOPMENT_MODE: result["development_otp"] = code
    return result

@app.post("/api/auth/verify-otp")
def verify_otp(payload: OtpVerify, response: Response) -> dict:
    email = str(payload.email).lower()
    with get_connection() as con:
        user = row_to_dict(con.execute("SELECT * FROM users WHERE email=? AND role=?", (email, payload.role)).fetchone())
        if not user or not user["is_active"]: raise HTTPException(403, "This account is unavailable.")
        otp = row_to_dict(con.execute("SELECT * FROM otp_codes WHERE user_id=? AND used_at IS NULL ORDER BY id DESC LIMIT 1", (user["id"],)).fetchone())
        valid = otp and otp["attempts"] < MAX_OTP_ATTEMPTS and otp["expires_at"] > date(now()) and secrets.compare_digest(otp["code_hash"], hash_secret(payload.code))
        if not valid:
            if otp: con.execute("UPDATE otp_codes SET attempts=attempts+1 WHERE id=?", (otp["id"],))
            raise HTTPException(400, "Invalid, expired, or exhausted OTP.")
        con.execute("UPDATE otp_codes SET used_at=CURRENT_TIMESTAMP WHERE id=?", (otp["id"],))
        con.execute("UPDATE users SET last_login_at=CURRENT_TIMESTAMP WHERE id=?", (user["id"],))
        token = secrets.token_urlsafe(32)
        con.execute("INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)", (hash_secret(token), user["id"], date(now()+timedelta(days=1))))
    audit(user, "User logged in", f"Role: {user['role']}")
    response.set_cookie("session_token", token, httponly=True, samesite="lax", secure=False, max_age=86400)
    return {"redirect": "/admin" if user["role"] == "admin" else "/dashboard", "role": user["role"]}

@app.post("/api/auth/logout", status_code=204)
def logout(response: Response, user: dict = Depends(current_user), session_token: str | None = Cookie(default=None)):
    with get_connection() as con: con.execute("DELETE FROM sessions WHERE token_hash=?", (hash_secret(session_token or ""),))
    audit(user, "User logged out")
    response.delete_cookie("session_token")
    return Response(status_code=204, headers={"Set-Cookie": "session_token=; Max-Age=0; Path=/; HttpOnly; SameSite=Lax"})

@app.get("/api/auth/me")
def whoami(user: dict = Depends(current_user)): return {key: user[key] for key in ("id", "email", "full_name", "role", "is_active", "last_login_at")}

@app.get("/api/students", response_model=list[Student])
def list_students(search: str = Query(default="", max_length=100), user: dict = Depends(current_user)):
    statement, params = "SELECT * FROM students", ()
    if search.strip():
        term=f"%{search.strip()}%"; statement += " WHERE full_name LIKE ? OR email LIKE ? OR department LIKE ?"; params=(term,term,term)
    with get_connection() as con: rows=con.execute(statement+" ORDER BY datetime(created_at) DESC, id DESC", params).fetchall()
    audit(user, "User viewed student records", f"Search: {search.strip() or 'all'}")
    return [dict(row) for row in rows]

@app.get("/api/students/{student_id}", response_model=Student)
def get_student(student_id: int, _: dict = Depends(current_user)): return get_student_or_404(student_id)

@app.post("/api/students", response_model=Student, status_code=201)
def create_student(payload: StudentCreate, user: dict = Depends(current_user)):
    try:
        with get_connection() as con:
            cursor=con.execute("INSERT INTO students (full_name,email,phone,department,year) VALUES (?,?,?,?,?)", (payload.full_name.strip(),str(payload.email),payload.phone.strip(),payload.department.strip(),payload.year)); row=con.execute("SELECT * FROM students WHERE id=?",(cursor.lastrowid,)).fetchone()
        audit(user,"User added a student record",f"Student ID: {cursor.lastrowid}; email: {payload.email}"); return dict(row)
    except sqlite3.IntegrityError: raise HTTPException(409,"A student with this email already exists")

@app.put("/api/students/{student_id}", response_model=Student)
def update_student(student_id: int, payload: StudentUpdate, user: dict = Depends(current_user)):
    get_student_or_404(student_id)
    try:
        with get_connection() as con:
            con.execute("UPDATE students SET full_name=?,email=?,phone=?,department=?,year=? WHERE id=?",(payload.full_name.strip(),str(payload.email),payload.phone.strip(),payload.department.strip(),payload.year,student_id)); row=con.execute("SELECT * FROM students WHERE id=?",(student_id,)).fetchone()
        audit(user,"User edited a student record",f"Student ID: {student_id}; email: {payload.email}"); return dict(row)
    except sqlite3.IntegrityError: raise HTTPException(409,"A student with this email already exists")

@app.delete("/api/students/{student_id}", status_code=204)
def delete_student(student_id: int, user: dict = Depends(current_user)):
    student=get_student_or_404(student_id)
    with get_connection() as con: con.execute("DELETE FROM students WHERE id=?",(student_id,))
    audit(user,"User deleted a student record",f"Student ID: {student_id}; email: {student['email']}"); return Response(status_code=204)

@app.get("/api/dashboard")
def dashboard_statistics(_: dict = Depends(current_user)):
    with get_connection() as con:
        total=con.execute("SELECT COUNT(*) FROM students").fetchone()[0]; departments=con.execute("SELECT COUNT(DISTINCT department) FROM students").fetchone()[0]; by_dept=con.execute("SELECT department,COUNT(*) count FROM students GROUP BY department ORDER BY count DESC,department").fetchall(); by_year=con.execute("SELECT year,COUNT(*) count FROM students GROUP BY year ORDER BY year").fetchall(); recent=con.execute("SELECT * FROM students ORDER BY datetime(created_at) DESC,id DESC LIMIT 5").fetchall()
    return {"database_status":"Connected","total_students":total,"total_departments":departments,"by_department":[dict(x) for x in by_dept],"by_year":[dict(x) for x in by_year],"recent_students":[dict(x) for x in recent]}

@app.get("/api/admin/summary")
def admin_summary(_: dict = Depends(require_admin)):
    with get_connection() as con:
        total=con.execute("SELECT COUNT(*) FROM users WHERE role='user'").fetchone()[0]; active=con.execute("SELECT COUNT(*) FROM users WHERE role='user' AND is_active=1").fetchone()[0]; logs=con.execute("SELECT * FROM audit_logs ORDER BY datetime(created_at) DESC,id DESC LIMIT 30").fetchall()
    return {"total_users":total,"active_users":active,"inactive_users":total-active,"recent_activity":[dict(x) for x in logs]}

@app.get("/api/admin/users")
def admin_list_users(_: dict = Depends(require_admin)):
    with get_connection() as con: rows=con.execute("SELECT id,email,full_name,role,is_active,created_at,last_login_at FROM users WHERE role='user' ORDER BY datetime(created_at) DESC,id DESC").fetchall()
    return [dict(x) for x in rows]

@app.post("/api/admin/users", status_code=201)
def admin_create_user(payload: ManagedUserCreate, admin: dict = Depends(require_admin)):
    try:
        with get_connection() as con:
            cursor=con.execute("INSERT INTO users (email,full_name,role) VALUES (?,?,'user')",(str(payload.email).lower(),payload.full_name.strip())); row=con.execute("SELECT id,email,full_name,role,is_active,created_at,last_login_at FROM users WHERE id=?",(cursor.lastrowid,)).fetchone()
        audit(admin,"Admin created user",f"User ID: {cursor.lastrowid}; email: {payload.email}"); return dict(row)
    except sqlite3.IntegrityError: raise HTTPException(409,"An account with this email already exists")

@app.patch("/api/admin/users/{user_id}")
def admin_update_user(user_id: int, payload: ManagedUserUpdate, admin: dict = Depends(require_admin)):
    with get_connection() as con:
        if not con.execute("SELECT id FROM users WHERE id=? AND role='user'",(user_id,)).fetchone(): raise HTTPException(404,"User not found")
        con.execute("UPDATE users SET is_active=? WHERE id=?",(int(payload.is_active),user_id)); row=con.execute("SELECT id,email,full_name,role,is_active,created_at,last_login_at FROM users WHERE id=?",(user_id,)).fetchone()
    audit(admin,"Admin changed user status",f"User ID: {user_id}; active: {payload.is_active}"); return dict(row)

@app.delete("/api/admin/users/{user_id}", status_code=204)
def admin_delete_user(user_id: int, admin: dict = Depends(require_admin)):
    with get_connection() as con:
        row=con.execute("SELECT * FROM users WHERE id=? AND role='user'",(user_id,)).fetchone()
        if not row: raise HTTPException(404,"User not found")
        con.execute("DELETE FROM sessions WHERE user_id=?",(user_id,)); con.execute("DELETE FROM otp_codes WHERE user_id=?",(user_id,)); con.execute("DELETE FROM users WHERE id=?",(user_id,))
    audit(admin,"Admin deleted user",f"User ID: {user_id}; email: {row['email']}"); return Response(status_code=204)
