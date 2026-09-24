from pydantic import BaseModel
from datetime import datetime
from typing import Any, Dict, Literal, Optional

class Sale(BaseModel):
    name: str

    active: bool
    started_at: datetime
    ended_at: datetime
    summary: bool
    code: Optional[str] = None
    isProduct: bool

    priority: int
    discount: int
    condition: list[Dict[str, Any]]

class User(BaseModel):
    name: str
    region: str
    status: str

class Product(BaseModel):
    name: str
    price: float
    card_price: float
    category: str

class SaleQuery(BaseModel):
    user_id: int
    product_id: list[Dict[str, Any]]
    promocode: str
    partner_card: bool
    ball: int

class Client(BaseModel):
    mail: Optional[str] = None
    login: str
    password: str

class ClientLogin(BaseModel):
    login: str
    password: str

class Store(BaseModel):
    title: str
    subtitle: str
    image: str

class CrmUser(BaseModel):
    login: str
    password: str
    status: Literal["user", "admin"] = "user"

class CrmUserUpdate(BaseModel):
    login: Optional[str] = None
    password: Optional[str] = None
    status: Optional[Literal["user", "admin"]] = None
