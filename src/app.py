"""FastAPI application factory for VetFlow AI."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from src.config import load_config
from src.utils.logger import setup_logging
from src.db.database import Database
from src.db.tenant_repo import TenantRepo
from src.db.appointment_repo import AppointmentRepo
from src.db.conversation_repo import ConversationRepo
from src.db.pet_repo import PetRepo
from src.db.reminder_repo import ReminderRepo
from src.services.ai_brain import AIBrain
from src.services.appointment_service import AppointmentService
from src.services.sms_service import SMSService
from src.services.phone_service import PhoneService
from src.services.email_service import EmailService
from src.services.reminder_service import ReminderService

from src.api.routes_chat import router as chat_router
from src.api.routes_webhook import router as webhook_router
from src.api.routes_appointment import router as appointment_router
from src.api.routes_intake import router as intake_router
from src.api.routes_dashboard import router as dashboard_router
from src.api.routes_widget import router as widget_router

logger = logging.getLogger("vetflow.app")


def create_app() -> FastAPI:
    config = load_config()
    setup_logging(
        level=config.get("logging", {}).get("level", "INFO"),
        log_file=config.get("logging", {}).get("file"),
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup
        db_path = config["_env"]["database_path"]
        db = Database(db_path)
        await db.connect()
        await db.run_migrations()

        # Repos
        app.state.config = config
        app.state.db = db
        app.state.tenant_repo = TenantRepo(db)
        app.state.appt_repo = AppointmentRepo(db)
        app.state.conv_repo = ConversationRepo(db)
        app.state.pet_repo = PetRepo(db)
        app.state.reminder_repo = ReminderRepo(db)

        # Services
        env = config["_env"]
        app.state.ai_brain = AIBrain(
            api_key=env["openai_api_key"],
            model=config.get("ai", {}).get("model", "gpt-4"),
            temperature=config.get("ai", {}).get("temperature", 0.3),
        )
        app.state.appt_service = AppointmentService(app.state.appt_repo, app.state.reminder_repo)
        app.state.sms_service = SMSService(env["twilio_account_sid"], env["twilio_auth_token"])
        app.state.phone_service = PhoneService(env["bland_api_key"], env["base_url"])
        app.state.email_service = EmailService(
            api_key=env["sendgrid_api_key"],
            from_email=config.get("email", {}).get("from_email", "hello@vetflow.ai"),
        )
        app.state.reminder_service = ReminderService(
            app.state.reminder_repo, app.state.appt_repo,
            app.state.sms_service, app.state.email_service,
        )

        logger.info("VetFlow AI started")
        yield

        # Shutdown
        await db.close()
        logger.info("VetFlow AI stopped")

    app = FastAPI(title="VetFlow AI", version="1.0.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(chat_router)
    app.include_router(webhook_router)
    app.include_router(appointment_router)
    app.include_router(intake_router)
    app.include_router(dashboard_router)
    app.include_router(widget_router)

    @app.get("/", response_class=HTMLResponse)
    async def marketing_home():
        """Serve the marketing landing page."""
        from pathlib import Path
        html_path = Path("src/templates/marketing/index.html")
        return HTMLResponse(html_path.read_text())

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "service": "VetFlow AI"}

    @app.get("/demo/{slug}", response_class=HTMLResponse)
    async def demo_page(slug: str):
        """Serve a clinic-specific proof/demo page."""
        import aiosqlite
        db_path = config["_env"]["database_path"]
        try:
            async with aiosqlite.connect(db_path) as adb:
                row = await (await adb.execute(
                    "SELECT html FROM demo_pages WHERE slug=?", (slug,)
                )).fetchone()
                if row:
                    await adb.execute(
                        "UPDATE demo_pages SET views = views + 1 WHERE slug=?", (slug,)
                    )
                    await adb.commit()
                    return HTMLResponse(row[0])
        except Exception as e:
            logger.warning("Demo page DB error: %s", e)
        return HTMLResponse(
            "<html><body style='font-family:sans-serif;max-width:500px;margin:60px auto;padding:20px'>"
            "<h2>Page not found</h2>"
            "<p>This demo link may have expired.</p>"
            "<a href='https://calendly.com/vetflow-ai/15-min-discovery-call' "
            "style='background:#6366f1;color:#fff;padding:12px 20px;border-radius:6px;"
            "text-decoration:none;display:inline-block;margin-top:16px'>"
            "Book a call with Karan →</a></body></html>",
            status_code=404,
        )

    @app.post("/api/admin/demo")
    async def create_demo_page(request):
        """Store a clinic-specific proof page (uploaded by proof_agent.py)."""
        from fastapi.responses import JSONResponse
        import aiosqlite
        try:
            data = await request.json()
            slug = data.get("slug", "")
            name = data.get("clinic_name", "")
            html = data.get("html", "")
            if not slug or not html:
                return JSONResponse({"error": "slug and html required"}, status_code=400)
            db_path = config["_env"]["database_path"]
            async with aiosqlite.connect(db_path) as adb:
                await adb.execute(
                    """CREATE TABLE IF NOT EXISTS demo_pages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        slug TEXT UNIQUE NOT NULL,
                        clinic_name TEXT,
                        html TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        views INTEGER DEFAULT 0
                    )"""
                )
                await adb.execute(
                    """INSERT INTO demo_pages (slug, clinic_name, html) VALUES (?,?,?)
                       ON CONFLICT(slug) DO UPDATE SET
                         html=excluded.html, clinic_name=excluded.clinic_name""",
                    (slug, name, html),
                )
                await adb.commit()
            return JSONResponse({"status": "ok", "url": f"/demo/{slug}"})
        except Exception as e:
            logger.error("Demo page create error: %s", e)
            return JSONResponse({"error": str(e)}, status_code=500)

    @app.post("/api/admin/contact")
    async def contact_form(request):
        """Handle marketing contact form submissions."""
        from fastapi.responses import JSONResponse
        try:
            data = await request.json()
            logger.info(f"Contact form submission: {data.get('email')} — {data.get('clinic_name')}")
            return JSONResponse({"status": "ok", "message": "Thank you! We will be in touch shortly."})
        except Exception as e:
            logger.error(f"Contact form error: {e}")
            return JSONResponse({"status": "error", "message": str(e)}, status_code=400)

    @app.post("/api/admin/seed-demo")
    async def seed_demo():
        """Seed a demo clinic for testing."""
        import uuid
        from src.models.tenant import Clinic, Staff

        tenant_repo = app.state.tenant_repo

        existing = await tenant_repo.get_clinic_by_api_key("vf_demo_3d12ff84d2294403")
        if existing:
            return {"status": "already_exists", "clinic_id": existing.id, "api_key": existing.api_key}

        clinic = Clinic(
            id=str(uuid.uuid4()),
            name="Happy Paws Veterinary Clinic",
            phone="+15873258952",
            email="vetflow.ai@gmail.com",
            address="123 Pet Lane, Calgary, AB T2P 1J9",
            city="Calgary",
            state="AB",
            timezone="America/Edmonton",
            twilio_phone="+15873258952",
            services=["wellness_exam", "vaccination", "dental", "surgery", "sick_visit"],
            business_hours={
                "mon": {"open": "08:00", "close": "18:00"},
                "tue": {"open": "08:00", "close": "18:00"},
                "wed": {"open": "08:00", "close": "18:00"},
                "thu": {"open": "08:00", "close": "18:00"},
                "fri": {"open": "08:00", "close": "18:00"},
                "sat": {"open": "09:00", "close": "14:00"},
            },
            emergency_keywords=["bleeding", "seizure", "poisoning", "hit by car", "not breathing"],
            api_key="vf_demo_3d12ff84d2294403",
            plan="standard",
            monthly_price=499.00,
        )
        await tenant_repo.create_clinic(clinic)

        vet = Staff(
            id=str(uuid.uuid4()),
            clinic_id=clinic.id,
            name="Dr. Sarah Chen",
            role="vet",
            phone="+15873258952",
            email="vetflow.ai@gmail.com",
            is_on_call=True,
        )
        await tenant_repo.create_staff(vet)

        return {
            "status": "created",
            "clinic_id": clinic.id,
            "api_key": clinic.api_key,
            "dashboard": f"/dashboard/?api_key={clinic.api_key}",
        }

    return app


app = create_app()
