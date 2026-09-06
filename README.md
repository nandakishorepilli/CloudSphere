# Cloud Sphere

Cloud Sphere is a local FastAPI prototype for managing college student records. It includes a browser dashboard, REST API, and a SQLite database stored on your Windows computer.

## Project structure

```text
CloudSphere/
├── app/
│   ├── main.py          # FastAPI routes and dashboard API
│   ├── database.py      # SQLite setup and sample data
│   ├── schemas.py       # API validation models
│   ├── templates/index.html
│   └── static/style.css, script.js
├── data/                # Created automatically; contains local database
├── requirements.txt
└── .gitignore
```

## Technologies

Python, FastAPI, Uvicorn, SQLite, HTML, CSS, and vanilla JavaScript.

## Prerequisites

Install Python 3.10 or newer and Git. Verify Python in PowerShell with `python --version`.

## Installation

From the `CloudSphere` folder in Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

If PowerShell blocks activation, run this once for the current PowerShell window, then activate again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

## Run the application

With the virtual environment activated, run:

```powershell
python -m uvicorn app.main:app --reload
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser.

## Authentication and roles

Cloud Sphere is a client-facing platform: `/` is a login-only page and there is no public sign-up flow. Accounts use email and a one-time password (OTP), not stored passwords. The first local administrator is `admin@cloudsphere.com` (override with `CLOUDSPHERE_ADMIN_EMAIL`). In development, the generated code is returned only by the OTP API and written to the server log to make local testing possible. Set `CLOUDSPHERE_ENV=production` before deployment and connect an email provider in `app/otp_service.py`; production does not return the OTP.

- Admins authenticate to `/admin`, where they create, activate, deactivate, and delete user accounts and inspect audit activity.
- Users authenticate to `/dashboard`, the existing student data workspace.
- OTPs expire after five minutes, are single-use, and allow five verification attempts. Sessions and all data APIs require authentication.

## API endpoints

- `GET /api/students` — list students; supports `?search=term`
- `GET /api/students/{id}` — get one student
- `POST /api/students` — create a student
- `PUT /api/students/{id}` — update a student
- `DELETE /api/students/{id}` — delete a student
- `GET /api/dashboard` — dashboard statistics
- `GET /docs` — interactive FastAPI API documentation

## Database

The SQLite file is `data/cloudsphere.db`. It is created automatically on first start, creates the `students` table, and adds sample records only when the table is empty. The database is ignored by Git so local data is not committed.

## Stop the server

Click the PowerShell window running the server and press `Ctrl+C`. To leave the virtual environment, run `deactivate`.

## Troubleshooting

- **`python` is not recognized:** install Python from python.org and reopen PowerShell.
- **Port 8000 is busy:** run `python -m uvicorn app.main:app --reload --port 8001`, then open `http://127.0.0.1:8001`.
- **Module error:** confirm `(.venv)` appears in PowerShell, then repeat `python -m pip install -r requirements.txt`.
- **Start fresh data:** stop the server and delete only `data/cloudsphere.db`; it will be recreated with sample data at next start.
