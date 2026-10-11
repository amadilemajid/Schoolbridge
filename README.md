# SchoolBridge Backend

SchoolBridge is a multi-tenant school management and automation platform. It manages student registration, attendance, fee collection (Mobile Money / PesaPal), parent/guardian notifications (WhatsApp & SMS), and academic results reporting.

---

## ⚡ Quick Start: Development Environment

To start all development services at once on Windows, you can use the automated startup routine:

### Option A: Desktop Shortcut (Recommended)
1. Ensure **Docker Desktop** is open and running.
2. Double-click the **SchoolBridge Dev Environment** shortcut on your Desktop.
3. This opens 3 dedicated PowerShell console windows for:
   - **Django Server** (running on http://localhost:8002)
   - **Celery Worker** (handling queues: `messaging`, `payments`, `automation`)
   - **Celery Beat** (scheduling periodic tasks)

### Option B: Batch File / PowerShell
- Double-click `start_dev.bat` in the root folder.
- Or run in a PowerShell window:
  ```powershell
  .\start_dev.ps1
  ```

---

## 🛠️ Port 5432 Conflict Resolution (PostgreSQL)

The development environment runs against Docker-hosted PostgreSQL (`edubridge_postgres` on port 5432). If you have a native Windows PostgreSQL installation running, it will block port 5432, preventing the Docker container from binding.

### To Stop/Disable Native PostgreSQL:
1. Open PowerShell **as Administrator**.
2. Run the following command to stop the native service:
   ```powershell
   Stop-Service -Name postgresql-x64-18 -Force
   ```
3. To prevent it from restarting automatically on reboot, run:
   ```powershell
   Set-Service -Name postgresql-x64-18 -StartupType Manual
   ```
4. Now restart Docker Desktop and run the startup script again.

---

## 📦 What the Startup Script Automates
1. **Virtual Environment Validation**: Checks that `.\venv` exists.
2. **Docker Daemon Status**: Verifies that the Docker engine is running.
3. **Database & Cache Health Check**: Automatically starts stopped containers (`edubridge_postgres` and `edubridge_redis`) and polls until they are healthy.
4. **Django Code System Check**: Runs `python manage.py check` to catch any Python syntax or setup issues before booting.
5. **Multi-process Orchestration**: Automatically spawns and titles separate service consoles.

---

## 📡 Service URLs

Once running, the services are available at:
- **API Base URL**: [http://localhost:8002/api/v1/](http://localhost:8002/api/v1/)
- **Swagger Docs**: [http://localhost:8002/api/docs/](http://localhost:8002/api/docs/)
- **OpenAPI Schema**: [http://localhost:8002/api/schema/](http://localhost:8002/api/schema/)
- **Django Admin**: [http://localhost:8002/admin/](http://localhost:8002/admin/)
- **Health Check**: [http://localhost:8002/health/](http://localhost:8002/health/)

---

## 🧪 Testing

To run the full test suite (Django tests + automated integrations):
```powershell
.\run_tests.ps1
```
