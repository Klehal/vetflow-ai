"""FastAPI application factory for VetFlow AI."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "service": "VetFlow AI"}

    @app.post("/api/admin/seed-demo")
    async def seed_demo():
        """Seed a demo clinic for testing."""
        import uuid, json
        from src.models.tenant import Clinic, Staff

        tenant_repo = app.state.tenant_repo

        # Check if already seeded
        existing = await tenant_repo.get_clinic_by_api_key("vf_demo_3d12ff84d2294403")
        if existing:
            return {"status": "already_exists", "clinic_id": existing.id, "api_key": existing.api_key}

        clinic = Clinic(
            id=str(uuid.uuid4()),
            name="Happy Paws Veterinary Clinic",
            phone="+15873258952",
            email="vetflow.ai@gmail.com",
            address="123 Pet Lane, Austin, TX 78701",
            city="Austin",
            state="TX",
            timezone="America/Chicago",
            twilio_phone="+15873258952",
            services=["wellness_exam", "vaccination", "dental", "surgery", "sick_visit", "grooming", "boarding"],
            business_hours={
                "mon": {"open": "08:00", "close": "18:00"},
                "tue": {"open": "08:00", "close": "18:00"},
                "wed": {"open": "08:00", "close": "18:00"},
                "thu": {"open": "08:00", "close": "18:00"},
                "fri": {"open": "08:00", "close": "18:00"},
                "sat": {"open": "09:00", "close": "14:00"},
            },
            emergency_keywords=["bleeding", "seizure", "poisoning", "hit by car", "not breathing", "unconscious"],
            api_key="vf_demo_3d12ff84d2294403",
            plan="standard",
            monthly_price=599.00,
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
            "intake_form": f"/intake/{clinic.id}",
            "widget_config": f"/widget/{clinic.id}/config",
        }

    return app


app = create_app()
