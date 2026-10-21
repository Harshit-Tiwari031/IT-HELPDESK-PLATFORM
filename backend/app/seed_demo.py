"""Explicitly insert sample tickets into an already migrated development database."""

from sqlalchemy import func, select

from app.config import get_settings
from app.database import SessionLocal
from app.models import Ticket, TicketCategory, TicketPriority, TicketStatus


SAMPLE_TICKETS = [
    {"id": "HD-2481", "title": "VPN disconnects during calls", "description": "The VPN drops every few minutes during video calls. I have restarted the client and router, but the issue continues.", "category": TicketCategory.network, "priority": TicketPriority.high, "status": TicketStatus.in_progress, "owner": "Priya Sharma"},
    {"id": "HD-2480", "title": "Cannot access shared drive", "description": "The Finance shared drive returns an access denied message even though I am signed in to the company network.", "category": TicketCategory.access, "priority": TicketPriority.high, "status": TicketStatus.open, "owner": "Aarav Mehta"},
    {"id": "HD-2479", "title": "Laptop running slowly", "description": "My laptop takes several minutes to start and applications freeze while opening large files.", "category": TicketCategory.hardware, "priority": TicketPriority.medium, "status": TicketStatus.in_progress, "owner": "Nisha Patel"},
    {"id": "HD-2478", "title": "Reset MFA for new phone", "description": "I replaced my phone and need to register the authenticator app on the new device.", "category": TicketCategory.account, "priority": TicketPriority.medium, "status": TicketStatus.resolved, "owner": "Dev Kumar"},
    {"id": "HD-2477", "title": "Wi-Fi unavailable in meeting room", "description": "The guest Wi-Fi network is not appearing in Conference Room 4B.", "category": TicketCategory.network, "priority": TicketPriority.low, "status": TicketStatus.resolved, "owner": "Ishita Rao"},
    {"id": "HD-2476", "title": "Email sync delayed on desktop", "description": "New messages appear on my phone but take a long time to show in the desktop mail client.", "category": TicketCategory.software, "priority": TicketPriority.low, "status": TicketStatus.open, "owner": "Rohan Singh"},
]


def main() -> None:
    if get_settings().app_env.lower() == "production":
        raise SystemExit("Refusing to seed demo tickets when APP_ENV=production.")
    with SessionLocal() as db:
        count = db.scalar(select(func.count()).select_from(Ticket))
        if count:
            raise SystemExit(f"The tickets table already contains {count} record(s); no demo data was inserted.")
        db.add_all(Ticket(**ticket) for ticket in SAMPLE_TICKETS)
        db.commit()
    print(f"Inserted {len(SAMPLE_TICKETS)} demo tickets.")


if __name__ == "__main__":
    main()
