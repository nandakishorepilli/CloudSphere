"""FastAPI routes for the Cloud Sphere college management prototype."""
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
import secrets, sqlite3
from fastapi import Cookie, Depends, FastAPI, HTTPException, Query, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from .database import get_connection, initialize_database, row_to_dict
from .otp_service import DEVELOPMENT_MODE, MAX_OTP_ATTEMPTS, OTP_TTL_MINUTES, generate_otp, hash_secret, send_otp
from .schemas import AttendanceSave, ManagedUserCreate, ManagedUserUpdate, OtpRequest, OtpVerify, Student, StudentCreate, StudentListItem, StudentUpdate

APP_DIRECTORY = Path(__file__).resolve().parent
@asynccontextmanager
async def lifespan(_: FastAPI): initialize_database(); yield
app = FastAPI(title="Cloud Sphere", version="0.4.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=APP_DIRECTORY / "static"), name="static")
def now(): return datetime.now(timezone.utc)
def date_text(value): return value.strftime("%Y-%m-%d %H:%M:%S")
def audit(user, action, details=""):
    with get_connection() as c: c.execute("INSERT INTO audit_logs (user_id,user_email,action,details) VALUES (?,?,?,?)", (user["id"] if user else None, user["email"] if user else "system", action, details))
def current_user(session_token: str | None = Cookie(default=None)):
    if not session_token: raise HTTPException(401, "Authentication required")
    with get_connection() as c: row=c.execute("SELECT users.* FROM sessions JOIN users ON users.id=sessions.user_id WHERE sessions.token_hash=? AND datetime(sessions.expires_at)>datetime('now')", (hash_secret(session_token),)).fetchone()
    user=row_to_dict(row)
    if not user or not user["is_active"]: raise HTTPException(401, "Your session is no longer active")
    return user
def require_admin(user=Depends(current_user)):
    if user["role"] != "admin": raise HTTPException(403, "Administrator access required")
    return user
def student_or_404(student_id):
    with get_connection() as c: row=c.execute("SELECT s.*, c.name AS course_name FROM students s LEFT JOIN courses c ON c.id=s.course_id WHERE s.id=?", (student_id,)).fetchone()
    if not row: raise HTTPException(404,"Student not found")
    return dict(row)
def course_or_422(c, course_id):
    row=c.execute("SELECT id FROM courses WHERE id=?",(course_id,)).fetchone()
    if not row: raise HTTPException(422,"Select an approved course")

@app.get("/", include_in_schema=False)
def login_page(): return FileResponse(APP_DIRECTORY / "templates" / "login.html")
@app.get("/dashboard", include_in_schema=False)
def user_dashboard(user=Depends(current_user)):
    if user["role"] != "user": raise HTTPException(403,"Student dashboard is available to user accounts only")
    return FileResponse(APP_DIRECTORY / "templates" / "user_dashboard.html")
@app.get("/attendance", include_in_schema=False)
def attendance_page(user=Depends(current_user)):
    if user["role"] != "user": raise HTTPException(403,"Student attendance is available to user accounts only")
    return FileResponse(APP_DIRECTORY / "templates" / "attendance.html")
@app.get("/admin", include_in_schema=False)
def admin_dashboard(_=Depends(require_admin)): return FileResponse(APP_DIRECTORY / "templates" / "admin.html")
@app.get("/admin/students", include_in_schema=False)
def admin_students(_=Depends(require_admin)): return FileResponse(APP_DIRECTORY / "templates" / "index.html")
@app.get("/admin/attendance", include_in_schema=False)
def admin_attendance(_=Depends(require_admin)): return FileResponse(APP_DIRECTORY / "templates" / "admin_attendance.html")
@app.get("/admin/activity", include_in_schema=False)
def admin_activity_page(_=Depends(require_admin)): return FileResponse(APP_DIRECTORY / "templates" / "activity.html")

@app.post("/api/auth/request-otp")
def request_otp(payload: OtpRequest):
    email=str(payload.email).lower()
    with get_connection() as c:
        user=row_to_dict(c.execute("SELECT * FROM users WHERE email=? AND role=?",(email,payload.role)).fetchone())
        if not user or not user["is_active"]: raise HTTPException(403,"This email is not an active account for the selected login.")
        code=generate_otp(); c.execute("UPDATE otp_codes SET used_at=CURRENT_TIMESTAMP WHERE user_id=? AND used_at IS NULL",(user["id"],)); c.execute("INSERT INTO otp_codes(user_id,code_hash,expires_at) VALUES(?,?,?)",(user["id"],hash_secret(code),date_text(now()+timedelta(minutes=OTP_TTL_MINUTES))))
    send_otp(email,code); result={"message":"A one-time code was sent. It expires in 5 minutes."}
    if DEVELOPMENT_MODE: result["development_otp"]=code
    return result
@app.post("/api/auth/verify-otp")
def verify_otp(payload: OtpVerify,response: Response):
    email=str(payload.email).lower()
    with get_connection() as c:
        user=row_to_dict(c.execute("SELECT * FROM users WHERE email=? AND role=?",(email,payload.role)).fetchone()); otp=row_to_dict(c.execute("SELECT * FROM otp_codes WHERE user_id=? AND used_at IS NULL ORDER BY id DESC LIMIT 1",(user["id"],)).fetchone()) if user else None
        valid=otp and otp["attempts"]<MAX_OTP_ATTEMPTS and otp["expires_at"]>date_text(now()) and secrets.compare_digest(otp["code_hash"],hash_secret(payload.code))
        if not user or not user["is_active"] or not valid:
            if otp: c.execute("UPDATE otp_codes SET attempts=attempts+1 WHERE id=?",(otp["id"],))
            raise HTTPException(400,"Invalid, expired, or exhausted OTP.")
        c.execute("UPDATE otp_codes SET used_at=CURRENT_TIMESTAMP WHERE id=?",(otp["id"],)); c.execute("UPDATE users SET last_login_at=CURRENT_TIMESTAMP WHERE id=?",(user["id"],)); token=secrets.token_urlsafe(32); c.execute("INSERT INTO sessions(token_hash,user_id,expires_at) VALUES(?,?,?)",(hash_secret(token),user["id"],date_text(now()+timedelta(days=1))))
    audit(user,"User logged in",f"Role: {user['role']}"); response.set_cookie("session_token",token,httponly=True,samesite="lax",secure=False,max_age=86400); return {"redirect":"/admin" if user["role"]=="admin" else "/dashboard","role":user["role"]}
@app.post("/api/auth/logout",status_code=204)
def logout(response:Response,user=Depends(current_user),session_token: str|None=Cookie(default=None)):
    with get_connection() as c:c.execute("DELETE FROM sessions WHERE token_hash=?",(hash_secret(session_token or ""),))
    audit(user,"User logged out");response.delete_cookie("session_token");return Response(status_code=204)

@app.get("/api/courses")
def courses(_=Depends(current_user)):
    with get_connection() as c: return [dict(x) for x in c.execute("SELECT id,name FROM courses ORDER BY id").fetchall()]
@app.get("/api/students",response_model=list[StudentListItem])
def list_students(name:str=Query("",max_length=100),roll_number:str=Query("",max_length=50),course_id:int|None=None,admin=Depends(require_admin)):
    statement="""SELECT s.*, c.name AS course_name,
        CASE WHEN u.id IS NULL THEN 'No linked account'
             WHEN u.is_active = 1 THEN 'Active' ELSE 'Inactive' END AS account_status
        FROM students s
        LEFT JOIN courses c ON c.id=s.course_id
        LEFT JOIN users u ON lower(u.email)=lower(s.email) AND u.role='user'
        WHERE 1=1""";params=[]
    if name.strip(): statement+=" AND s.full_name LIKE ?";params.append(f"%{name.strip()}%")
    if roll_number.strip(): statement+=" AND s.roll_number LIKE ?";params.append(f"%{roll_number.strip()}%")
    if course_id: statement+=" AND s.course_id=?";params.append(course_id)
    with get_connection() as c: rows=c.execute(statement+" ORDER BY s.full_name COLLATE NOCASE",params).fetchall()
    audit(admin,"Admin viewed student records",f"Name: {name or 'all'}; roll: {roll_number or 'all'}; course: {course_id or 'all'}");return [dict(x) for x in rows]
@app.get("/api/students/{student_id}")
def get_student(student_id:int,admin=Depends(require_admin)):
    student=student_or_404(student_id)
    with get_connection() as c: account=c.execute("SELECT is_active FROM users WHERE lower(email)=lower(?) AND role='user'",(student["email"],)).fetchone()
    student["account_status"]="No linked account" if not account else ("Active" if account["is_active"] else "Inactive")
    student["attendance"]=attendance_summary(student_id);return student
@app.post("/api/students",response_model=Student,status_code=201)
def create_student(payload:StudentCreate,admin=Depends(require_admin)):
    try:
        with get_connection() as c:
            course_or_422(c,payload.course_id);cur=c.execute("INSERT INTO students(full_name,email,phone,department,year,roll_number,course_id) VALUES(?,?,?,?,?,?,?)",(payload.full_name.strip(),str(payload.email),payload.phone.strip(),payload.department.strip(),payload.year,payload.roll_number.strip().upper(),payload.course_id));row=c.execute("SELECT * FROM students WHERE id=?",(cur.lastrowid,)).fetchone()
        audit(admin,"Admin added student",f"Student ID: {cur.lastrowid}; roll: {payload.roll_number}");return dict(row)
    except sqlite3.IntegrityError: raise HTTPException(409,"A student with this email or roll number already exists")
@app.put("/api/students/{student_id}",response_model=Student)
def update_student(student_id:int,payload:StudentUpdate,admin=Depends(require_admin)):
    student_or_404(student_id)
    try:
        with get_connection() as c:
            course_or_422(c,payload.course_id);c.execute("UPDATE students SET full_name=?,email=?,phone=?,department=?,year=?,roll_number=?,course_id=? WHERE id=?",(payload.full_name.strip(),str(payload.email),payload.phone.strip(),payload.department.strip(),payload.year,payload.roll_number.strip().upper(),payload.course_id,student_id));row=c.execute("SELECT * FROM students WHERE id=?",(student_id,)).fetchone()
        audit(admin,"Admin edited student",f"Student ID: {student_id}; roll: {payload.roll_number}");return dict(row)
    except sqlite3.IntegrityError: raise HTTPException(409,"A student with this email or roll number already exists")
@app.delete("/api/students/{student_id}",status_code=204)
def delete_student(student_id:int,admin=Depends(require_admin)):
    student=student_or_404(student_id)
    with get_connection() as c: c.execute("DELETE FROM attendance_records WHERE student_id=?",(student_id,));c.execute("DELETE FROM students WHERE id=?",(student_id,))
    audit(admin,"Admin deleted student",f"Student ID: {student_id}; roll: {student.get('roll_number') or 'none'}");return Response(status_code=204)

def attendance_summary(student_id):
    with get_connection() as c: row=c.execute("SELECT COUNT(*) total, SUM(status='present') present, SUM(status='absent') absent FROM attendance_records WHERE student_id=?",(student_id,)).fetchone();history=c.execute("SELECT a.attendance_date,c.name course,a.status FROM attendance_records a JOIN courses c ON c.id=a.course_id WHERE a.student_id=? ORDER BY a.attendance_date DESC,a.id DESC",(student_id,)).fetchall()
    total=row["total"];return {"total":total,"present":row["present"] or 0,"absent":row["absent"] or 0,"percentage":round((row["present"] or 0)*100/total,1) if total else 0,"history":[dict(x) for x in history]}
@app.get("/api/attendance/me")
def my_attendance(user=Depends(current_user)):
    if user["role"]!="user":raise HTTPException(403,"Student attendance is available to user accounts only")
    with get_connection() as c: student=c.execute("SELECT id,full_name,roll_number FROM students WHERE lower(email)=?",(user["email"].lower(),)).fetchone()
    if not student:return {"student":None,"summary":{"total":0,"present":0,"absent":0,"percentage":0,"history":[]},"by_course":[]}
    summary=attendance_summary(student["id"])
    with get_connection() as c: rows=c.execute("SELECT c.name course,COUNT(*) total,SUM(a.status='present') present,SUM(a.status='absent') absent FROM attendance_records a JOIN courses c ON c.id=a.course_id WHERE a.student_id=? GROUP BY c.id,c.name ORDER BY c.name",(student["id"],)).fetchall()
    return {"student":dict(student),"summary":summary,"by_course":[{**dict(x),"percentage":round((x["present"] or 0)*100/x["total"],1)} for x in rows]}
@app.get("/api/admin/attendance/students")
def attendance_students(course_id:int,search:str=Query("",max_length=100),attendance_date:str=Query(...),_=Depends(require_admin)):
    with get_connection() as c:
        course_or_422(c,course_id);rows=c.execute("SELECT s.id,s.full_name,s.roll_number,COALESCE(a.status,'absent') status FROM students s LEFT JOIN attendance_records a ON a.student_id=s.id AND a.course_id=? AND a.attendance_date=? WHERE s.course_id=? AND (s.full_name LIKE ? OR s.roll_number LIKE ?) ORDER BY s.full_name",(course_id,attendance_date,course_id,f"%{search.strip()}%",f"%{search.strip()}%")).fetchall()
    return [dict(x) for x in rows]
@app.post("/api/admin/attendance")
def save_attendance(payload:AttendanceSave,admin=Depends(require_admin)):
    with get_connection() as c:
        course_or_422(c,payload.course_id)
        for mark in payload.marks:
            student=c.execute("SELECT id FROM students WHERE id=? AND course_id=?",(mark.student_id,payload.course_id)).fetchone()
            if not student: raise HTTPException(422,"Every marked student must belong to the selected course")
            c.execute("INSERT INTO attendance_records(student_id,course_id,attendance_date,status,updated_at) VALUES(?,?,?,?,CURRENT_TIMESTAMP) ON CONFLICT(student_id,course_id,attendance_date) DO UPDATE SET status=excluded.status,updated_at=CURRENT_TIMESTAMP",(mark.student_id,payload.course_id,payload.attendance_date.isoformat(),mark.status))
    audit(admin,"Admin saved attendance",f"Course ID: {payload.course_id}; date: {payload.attendance_date}; students: {len(payload.marks)}");return {"message":"Attendance saved"}
@app.get("/api/admin/summary")
def admin_summary(_=Depends(require_admin)):
    with get_connection() as c: total=c.execute("SELECT COUNT(*) FROM students").fetchone()[0];courses=c.execute("SELECT COUNT(*) FROM courses").fetchone()[0];attendance=c.execute("SELECT COUNT(*) FROM attendance_records").fetchone()[0]
    return {"total_students":total,"total_courses":courses,"attendance_records":attendance}
@app.get("/api/admin/activity")
def activity(_=Depends(require_admin)):
    with get_connection() as c:return [dict(x) for x in c.execute("SELECT * FROM audit_logs ORDER BY datetime(created_at) DESC,id DESC LIMIT 100").fetchall()]
@app.get("/api/admin/users")
def admin_users(_=Depends(require_admin)):
    with get_connection() as c:return [dict(x) for x in c.execute("SELECT id,email,full_name,role,is_active,created_at,last_login_at FROM users WHERE role='user' ORDER BY id DESC").fetchall()]
@app.post("/api/admin/users",status_code=201)
def admin_create_user(payload:ManagedUserCreate,admin=Depends(require_admin)):
    try:
        with get_connection() as c: cur=c.execute("INSERT INTO users(email,full_name,role) VALUES(?,?,'user')",(str(payload.email).lower(),payload.full_name.strip()));row=c.execute("SELECT id,email,full_name,role,is_active,created_at,last_login_at FROM users WHERE id=?",(cur.lastrowid,)).fetchone()
        audit(admin,"Admin created user",f"User ID: {cur.lastrowid}; email: {payload.email}");return dict(row)
    except sqlite3.IntegrityError:raise HTTPException(409,"An account with this email already exists")
@app.patch("/api/admin/users/{user_id}")
def admin_update_user(user_id:int,payload:ManagedUserUpdate,admin=Depends(require_admin)):
    with get_connection() as c:
        if not c.execute("SELECT id FROM users WHERE id=? AND role='user'",(user_id,)).fetchone():raise HTTPException(404,"User not found")
        c.execute("UPDATE users SET is_active=? WHERE id=?",(int(payload.is_active),user_id));row=c.execute("SELECT id,email,full_name,role,is_active,created_at,last_login_at FROM users WHERE id=?",(user_id,)).fetchone()
    audit(admin,"Admin changed user status",f"User ID: {user_id}; active: {payload.is_active}");return dict(row)
@app.delete("/api/admin/users/{user_id}",status_code=204)
def admin_delete_user(user_id:int,admin=Depends(require_admin)):
    with get_connection() as c:
        row=c.execute("SELECT email FROM users WHERE id=? AND role='user'",(user_id,)).fetchone()
        if not row: raise HTTPException(404,"User not found")
        c.execute("DELETE FROM sessions WHERE user_id=?",(user_id,));c.execute("DELETE FROM otp_codes WHERE user_id=?",(user_id,));c.execute("UPDATE audit_logs SET user_id=NULL WHERE user_id=?",(user_id,));c.execute("DELETE FROM users WHERE id=?",(user_id,))
    audit(admin,"Admin deleted user",f"User ID: {user_id}; email: {row['email']}");return Response(status_code=204)
