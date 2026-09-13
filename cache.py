from datetime import datetime
from database import SessionLocal, SaleDB
from typing import Optional

_sales_cahce = {"data": []}

def refresh_sales_cahce() -> None:
    db = SessionLocal()
    try:
        rows = (
            db.query(SaleDB).filter(SaleDB.active.is_(True)).order_by(SaleDB.priority.asc()).all()
        )
        db.expunge_all()
        _sales_cahce["data"] = rows
    finally:
        db.close()

def get_active_cards(param_datetime: Optional[datetime] = None):
    now = param_datetime or datetime.now()
    product_cards, user_cards = [], []
    for s in _sales_cahce["data"]:
        if s.started_at <= now <= s.ended_at:
            (product_cards if s.isProduct else user_cards).append(s)
    return product_cards, user_cards

