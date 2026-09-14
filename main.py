from fastapi import HTTPException
from fastapi import FastAPI, Depends, Form, Request
from typing import Optional
from fastapi.middleware.cors import CORSMiddleware
from database import SessionLocal, SaleDB, UserDB, ProductDB
from sqlalchemy.orm import Session
from local_types import Sale, SaleQuery, User, Product
from datetime import datetime
from index import get_user_cards, get_user_product_cards, get_user_products, get_final_price
from time import perf_counter
from cache import get_active_cards, refresh_sales_cahce
from contextlib import asynccontextmanager

# uvicorn api:app --no-access-log --loop uvloop --http httptools

@asynccontextmanager
async def lifespan(app: FastAPI):
    refresh_sales_cahce()
    yield

app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://helpful-halva-84b879.netlify.app"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/")
async def root():
    return {"message": "Hello World"}

@app.middleware("http")
async def timing_middleware(request: Request, call_next):
    start = perf_counter()

    response = await call_next(request)

    elapsed = (perf_counter() - start) * 1000

    print(
        f"{request.method} {request.url.path}: "
        f"{elapsed:.3f} ms"
    )

    return response

@app.post("/create-sale")
async def create_sale(sale: Sale, db: Session = Depends(get_db)):
    new_sale = SaleDB(
        name = sale.name,
        active = sale.active,
        started_at = sale.started_at,
        ended_at = sale.ended_at,
        summary = sale.summary,
        isProduct = sale.isProduct,
        priority = sale.priority,
        discount = sale.discount / 100,
        condition = sale.condition,
    )
    db.add(new_sale)
    db.commit()
    refresh_sales_cahce()
    db.refresh(new_sale)

    return {
        "message": "Sale created",
        "sale": new_sale.id,
    }

@app.get("/get-sales")
async def get_sales(db: Session = Depends(get_db)):
    sales = db.query(SaleDB).all()
    return {
        "message": "Sales found",
        "sale": sales,
    }

@app.post("/deleted-sale")
async def deleted_sale(db: Session = Depends(get_db), sale_id: int = Form(...)):
    sale = db.query(SaleDB).get(sale_id)
    if sale is None:
        raise HTTPException(status_code=404, detail="Sale not found")
    db.delete(sale)
    db.commit()
    refresh_sales_cahce()
    return {
        "message": "Sale deleted",
    }

@app.post("/update-sale")
async def update_sale(sale: Sale, sale_id: int, db: Session = Depends(get_db)):
    local_sale = db.query(SaleDB).get(sale_id)
    if local_sale is None:
        raise HTTPException(status_code=404, detail="Sale not found")
    local_sale.name = sale.name
    local_sale.active = sale.active
    local_sale.started_at = sale.started_at
    local_sale.ended_at = sale.ended_at
    local_sale.summary = sale.summary
    local_sale.condition = sale.condition
    local_sale.discount = sale.discount / 100
    local_sale.priority = sale.priority
    local_sale.isProduct = sale.isProduct
    local_sale.code = sale.code
    db.add(local_sale)
    db.commit()
    refresh_sales_cahce()
    db.refresh(local_sale)
    return {
        "message": "Sale updated",
    }

@app.post("/create-user")
async def create_user(user: User, db: Session = Depends(get_db)):
    new_user = UserDB(
        name = user.name,
        region = user.region,
        status = user.status,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {
        "message": "User created",
    }

@app.get("/get-users")
async def get_users(db: Session = Depends(get_db)):
    users = db.query(UserDB).all()
    return {
        "users": users,
    }

@app.get("/get-products")
async def get_products(db: Session = Depends(get_db)):
    products = db.query(ProductDB).all()
    return {
        "products": products,
    }

@app.post("/delete-user")
async def delete_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(UserDB).get(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    db.delete(user)
    db.commit()
    return {
        "message": "User deleted",
    }

@app.post("/delete-product")
async def delete_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(ProductDB).get(product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    db.delete(product)
    db.commit()
    return {
        "message": "Product deleted",
    }

@app.post("/create-product")
async def create_product(product: Product, db: Session = Depends(get_db)):
    new_product = ProductDB(
        name = product.name,
        price = product.price,
        card_price = product.card_price,
        category = product.category,
    )
    db.add(new_product)
    db.commit()
    db.refresh(new_product)
    return {
        "message": "Product created",
    }

@app.post("/get-price")
async def get_price(data: SaleQuery, db: Session = Depends(get_db), param_datetime: Optional[datetime] = None):

    start = perf_counter()

    user = db.query(UserDB).filter(UserDB.id == data.user_id).first()

    t1 = perf_counter()

    # product_cards = get_user_product_cards(db, param_datetime)
    product_cards, user_cards = get_active_cards(param_datetime)

    t2 = perf_counter()

    products = get_user_products(db, data.product_id, product_cards, user, data.partner_card)

    t3 = perf_counter()

    # user_cards = get_user_cards(db, param_datetime)

    t4 = perf_counter()

    user_sales, final_price = get_final_price(user_cards, user, data.promocode, data.ball, sum([product["summ_price"] for product in products]))

    t5 = perf_counter()
    print("\n=== /get-price breakdown ===")
    print(f"  [1] get user (SQL):             {(t1 - start) * 1000:.3f} ms")
    print(f"  [2] get_user_product_cards:     {(t2 - t1) * 1000:.3f} ms")
    print(f"  [3] get_user_products:          {(t3 - t2) * 1000:.3f} ms")
    print(f"  [4] get_user_cards:             {(t4 - t3) * 1000:.3f} ms")
    print(f"  [5] get_final_price:            {(t5 - t4) * 1000:.3f} ms")
    print(f"  --- TOTAL:                      {(t5 - start) * 1000:.3f} ms")
    print("===========================\n")

    return {
        "products": products,
        "user_sales": user_sales,
        "price": final_price,
    }


    # actual_cards = get_discount(user, products, cards)
    # orig_price = sum(product["quantity"] * product["product"].price for product in products)
    # price = get_price(orig_price, actual_cards)

    # return {
    #     "price": orig_price,
    #     "price-after-sale": price,
    #     "products": products,
    # }



# {
#   "name": "VIP клиенту",
#   "active": true,
#   "started_at": "2026-08-28T09:08:10.132Z",
#   "ended_at": "2026-09-06T09:08:10.132Z",
#   "summary": true,
#   "priority": 1,
#   "isProduct": false,
#   "discount": 10,
#   "condition": [{
#     "field": "user.status", "operator": "==", "value": "vip"
#   }]
# }

# {
#   "user_id": 1,
#   "product_id": [
#     {
#       "product": 1,
#       "quantity": 1
#     }
#   ],
#   "promocode": "",
#   "partner_card": false
# }
