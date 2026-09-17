from fastapi import HTTPException
from fastapi import FastAPI, Depends, Form, Request
from typing import Optional
from fastapi.middleware.cors import CORSMiddleware
from pip._internal.models.link import Link

from database import SessionLocal, SaleDB, UserDB, ProductDB, ClientsDB, LinksDB, StoreDB, BaseLinks
from sqlalchemy.orm import Session
from local_types import Sale, SaleQuery, User, Product, Client, ClientLogin, Store
from auth import hash_password, verify_password, create_access_token, get_current_client_id
from datetime import datetime
from index import get_user_cards, get_user_product_cards, get_user_products, get_final_price
from time import perf_counter
from cache import get_active_cards, refresh_sales_cahce
from contextlib import asynccontextmanager
from urllib.parse import urlparse


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
#
# @app.post("/create-sale")
# async def create_sale(sale: Sale, db: Session = Depends(get_db)):
#     new_sale = SaleDB(
#         name = sale.name,
#         active = sale.active,
#         started_at = sale.started_at,
#         ended_at = sale.ended_at,
#         summary = sale.summary,
#         isProduct = sale.isProduct,
#         priority = sale.priority,
#         discount = sale.discount / 100,
#         condition = sale.condition,
#     )
#     db.add(new_sale)
#     db.commit()
#     refresh_sales_cahce()
#     db.refresh(new_sale)
#
#     return {
#         "message": "Sale created",
#         "sale": new_sale.id,
#     }
#
# @app.get("/get-sales")
# async def get_sales(db: Session = Depends(get_db)):
#     sales = db.query(SaleDB).all()
#     return {
#         "message": "Sales found",
#         "sale": sales,
#     }
#
# @app.post("/deleted-sale")
# async def deleted_sale(db: Session = Depends(get_db), sale_id: int = Form(...)):
#     sale = db.query(SaleDB).get(sale_id)
#     if sale is None:
#         raise HTTPException(status_code=404, detail="Sale not found")
#     db.delete(sale)
#     db.commit()
#     refresh_sales_cahce()
#     return {
#         "message": "Sale deleted",
#     }
#
# @app.post("/update-sale")
# async def update_sale(sale: Sale, sale_id: int, db: Session = Depends(get_db)):
#     local_sale = db.query(SaleDB).get(sale_id)
#     if local_sale is None:
#         raise HTTPException(status_code=404, detail="Sale not found")
#     local_sale.name = sale.name
#     local_sale.active = sale.active
#     local_sale.started_at = sale.started_at
#     local_sale.ended_at = sale.ended_at
#     local_sale.summary = sale.summary
#     local_sale.condition = sale.condition
#     local_sale.discount = sale.discount / 100
#     local_sale.priority = sale.priority
#     local_sale.isProduct = sale.isProduct
#     local_sale.code = sale.code
#     db.add(local_sale)
#     db.commit()
#     refresh_sales_cahce()
#     db.refresh(local_sale)
#     return {
#         "message": "Sale updated",
#     }
#
# @app.post("/create-user")
# async def create_user(user: User, db: Session = Depends(get_db)):
#     new_user = UserDB(
#         name = user.name,
#         region = user.region,
#         status = user.status,
#     )
#     db.add(new_user)
#     db.commit()
#     db.refresh(new_user)
#     return {
#         "message": "User created",
#     }
#
# @app.get("/get-users")
# async def get_users(db: Session = Depends(get_db)):
#     users = db.query(UserDB).all()
#     return {
#         "users": users,
#     }
#
# @app.get("/get-products")
# async def get_products(db: Session = Depends(get_db)):
#     products = db.query(ProductDB).all()
#     return {
#         "products": products,
#     }
#
# @app.post("/delete-user")
# async def delete_user(user_id: int, db: Session = Depends(get_db)):
#     user = db.query(UserDB).get(user_id)
#     if user is None:
#         raise HTTPException(status_code=404, detail="User not found")
#     db.delete(user)
#     db.commit()
#     return {
#         "message": "User deleted",
#     }
#
# @app.post("/delete-product")
# async def delete_product(product_id: int, db: Session = Depends(get_db)):
#     product = db.query(ProductDB).get(product_id)
#     if product is None:
#         raise HTTPException(status_code=404, detail="Product not found")
#     db.delete(product)
#     db.commit()
#     return {
#         "message": "Product deleted",
#     }
#
# @app.post("/create-product")
# async def create_product(product: Product, db: Session = Depends(get_db)):
#     new_product = ProductDB(
#         name = product.name,
#         price = product.price,
#         card_price = product.card_price,
#         category = product.category,
#     )
#     db.add(new_product)
#     db.commit()
#     db.refresh(new_product)
#     return {
#         "message": "Product created",
#     }
#
# @app.post("/get-price")
# async def get_price(data: SaleQuery, db: Session = Depends(get_db), param_datetime: Optional[datetime] = None):
#
#     start = perf_counter()
#
#     user = db.query(UserDB).filter(UserDB.id == data.user_id).first()
#
#     t1 = perf_counter()
#
#     # product_cards = get_user_product_cards(db, param_datetime)
#     product_cards, user_cards = get_active_cards(param_datetime)
#
#     t2 = perf_counter()
#
#     products = get_user_products(db, data.product_id, product_cards, user, data.partner_card)
#
#     t3 = perf_counter()
#
#     # user_cards = get_user_cards(db, param_datetime)
#
#     t4 = perf_counter()
#
#     user_sales, final_price = get_final_price(user_cards, user, data.promocode, data.ball, sum([product["summ_price"] for product in products]))
#
#     t5 = perf_counter()
#     print("\n=== /get-price breakdown ===")
#     print(f"  [1] get user (SQL):             {(t1 - start) * 1000:.3f} ms")
#     print(f"  [2] get_user_product_cards:     {(t2 - t1) * 1000:.3f} ms")
#     print(f"  [3] get_user_products:          {(t3 - t2) * 1000:.3f} ms")
#     print(f"  [4] get_user_cards:             {(t4 - t3) * 1000:.3f} ms")
#     print(f"  [5] get_final_price:            {(t5 - t4) * 1000:.3f} ms")
#     print(f"  --- TOTAL:                      {(t5 - start) * 1000:.3f} ms")
#     print("===========================\n")
#
#     return {
#         "products": products,
#         "user_sales": user_sales,
#         "price": final_price,
#     }


@app.get("/get-links")
async def get_links(store_id: int, db: Session = Depends(get_db)):
    store = db.get(StoreDB, store_id)
    if store is None:
        raise HTTPException(status_code=404, detail="Store not found")
    links = db.query(LinksDB).filter(LinksDB.store_id == store_id).all()
    return {
        "id": store.id,
        "title": store.title,
        "subtitle": store.subtitle,
        "image": store.image,
        "links": links,
    }

@app.post("/create-link")
async def create_link(link: str, label: Optional[str] = None, client_id: int = Depends(get_current_client_id), db: Session = Depends(get_db)):
    store = db.query(StoreDB).filter(StoreDB.client_id == client_id).first()
    if store is None:
        raise HTTPException(status_code=404, detail="Store not found")

    parsed_url = urlparse(link)
    base = db.query(BaseLinks).filter(BaseLinks.name == parsed_url.netloc).first()
    if base is not None:
        new_link = LinksDB(
            icon=base.src,
            link=link,
            label=base.label,
            store_id=store.id,
        )
    else:
        new_link = LinksDB(
            icon=None,
            link=link,
            label=label if label is not None else parsed_url.netloc,
            store_id=store.id,
        )

    db.add(new_link)
    db.commit()
    db.refresh(new_link)
    return {
        "message": "Link created",
    }

@app.post("/delete-link")
async def delete_link(link_id: int, client_id: int = Depends(get_current_client_id), db: Session = Depends(get_db)):
    link = db.get(LinksDB, link_id)
    if link is None:
        raise HTTPException(status_code=404, detail="Link not found")
    store = db.get(StoreDB, link.store_id)
    if store is None or store.client_id != client_id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this link")
    db.delete(link)
    db.commit()
    return {
        "message": "Link deleted",
    }

@app.post("/update-link")
async def update_link(link_id: int, link: str, label: Optional[str] = None, client_id: int = Depends(get_current_client_id), db: Session = Depends(get_db)):
    local_link = db.get(LinksDB, link_id)
    if local_link is None:
        raise HTTPException(status_code=404, detail="Link not found")
    store = db.get(StoreDB, local_link.store_id)
    if store is None or store.client_id != client_id:
        raise HTTPException(status_code=403, detail="Not authorized to update this link")

    parsed_url = urlparse(link)
    base = db.query(BaseLinks).filter(BaseLinks.name == parsed_url.netloc).first()
    local_link.link = link
    if base is not None:
        local_link.icon = base.icon
        local_link.label = base.label
    else:
        local_link.icon = None
        local_link.label = label if label is not None else parsed_url.netloc

    db.add(local_link)
    db.commit()
    db.refresh(local_link)
    return {
        "message": "Link updated",
    }

@app.post("/create-store")
async def create_store(store: Store, client_id: int = Depends(get_current_client_id), db: Session = Depends(get_db)):
    new_store = StoreDB(
        title=store.title,
        subtitle=store.subtitle,
        image=store.image,
        client_id=client_id,
    )
    db.add(new_store)
    db.commit()
    db.refresh(new_store)
    return {
        "message": "Store created",
        "store": new_store.id,
    }

@app.get("/get-stores")
async def get_stores(db: Session = Depends(get_db)):
    stores = db.query(StoreDB).all()
    return {
        "stores": stores,
    }

@app.get("/get-my-store")
async def get_stor_by_id(client_id: int = Depends(get_current_client_id), db: Session = Depends(get_db)):
    store = db.query(StoreDB).filter(StoreDB.client_id == client_id).first()
    if store is None:
        store = StoreDB(
            client_id=client_id,
            title="Название",
            subtitle="Описание / адрес",
            image="https://i.pinimg.com/736x/02/62/99/0262999a902deb8fcd8137e005a57551.jpg",
        )
        db.add(store)
        db.commit()
        db.refresh(store)
    client = db.get(ClientsDB, client_id)
    return {
        "store_id": store.id,
        "mail": client.mail,
    }

@app.post("/delete-store")
async def delete_store(store_id: int, client_id: int = Depends(get_current_client_id), db: Session = Depends(get_db)):
    store = db.get(StoreDB, store_id)
    if store is None:
        raise HTTPException(status_code=404, detail="Store not found")
    if store.client_id != client_id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this store")
    db.delete(store)
    db.commit()
    return {
        "message": "Store deleted",
    }

@app.post("/update-store")
async def update_store(store_id: int, store: Store, client_id: int = Depends(get_current_client_id), db: Session = Depends(get_db)):
    local_store = db.get(StoreDB, store_id)
    if local_store is None:
        raise HTTPException(status_code=404, detail="Store not found")
    if local_store.client_id != client_id:
        raise HTTPException(status_code=403, detail="Not authorized to update this store")
    local_store.title = store.title
    local_store.subtitle = store.subtitle
    local_store.image = store.image
    db.add(local_store)
    db.commit()
    db.refresh(local_store)
    return {
        "message": "Store updated",
    }

@app.post("/register")
async def register(client: Client, db: Session = Depends(get_db)):
    existing = db.query(ClientsDB).filter(ClientsDB.login == client.login).first()
    if existing is not None:
        raise HTTPException(status_code=400, detail="Login already taken")

    new_client = ClientsDB(
        mail=client.mail,
        login=client.login,
        password=hash_password(client.password),
    )
    db.add(new_client)
    db.commit()
    db.refresh(new_client)
    token = create_access_token(new_client.id)
    return {
        "message": "Client registered",
        "access_token": token,
        "token_type": "bearer",
    }

@app.post("/login")
async def login(credentials: ClientLogin, db: Session = Depends(get_db)):
    client = db.query(ClientsDB).filter(ClientsDB.login == credentials.login).first()
    if client is None or not verify_password(credentials.password, client.password):
        raise HTTPException(status_code=401, detail="Invalid login or password")

    token = create_access_token(client.id)
    return {
        "message": "Login successful",
        "access_token": token,
        "token_type": "bearer",
    }

@app.get("/get-clients")
async def get_clients(db: Session = Depends(get_db)):
    clients = db.query(ClientsDB).all()
    return {
        "clients": [{"id": c.id, "mail": c.mail, "login": c.login} for c in clients],
    }

@app.post("/delete-client")
async def delete_client(client_id: int = Depends(get_current_client_id), db: Session = Depends(get_db)):
    client = db.get(ClientsDB, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found")
    db.delete(client)
    db.commit()
    return {
        "message": "Client deleted",
    }

@app.post("/update-mail")
async def update_mail(mail: str, client_id: int = Depends(get_current_client_id), db: Session = Depends(get_db)):
    client = db.get(ClientsDB, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found")
    client.mail = mail
    db.add(client)
    db.commit()
    db.refresh(client)
    return {
        "message": "Mail updated",
    }

@app.post("/update-client")
async def update_client(client: Client, client_id: int = Depends(get_current_client_id), db: Session = Depends(get_db)):
    local_client = db.get(ClientsDB, client_id)
    if local_client is None:
        raise HTTPException(status_code=404, detail="Client not found")
    local_client.mail = client.mail
    local_client.login = client.login
    local_client.password = hash_password(client.password)
    db.add(local_client)
    db.commit()
    db.refresh(local_client)
    return {
        "message": "Client updated",
    }

LINKS = {
    "yandex.ru": {
        "src": "./icons/ya.svg",
        "label": "Яндекс Карты",
    },
    "t.me": {
        "src": "./icons/tg.svg",
        "label": "Телеграм"
    },
    "avito.ru": {
        "src": "./icons/avito.png",
        "label": "Авито"
    },
    "go.2gis.com": {
        "src": "./icons/gis.svg",
        "label": "2гис"
    },
    "www.avito.ru": {
        "src": "./icons/avito.png",
        "label": "Авито"
    },
    "vk.ru": {
        "src": "./icons/vk.svg",
        "label": "ВКонтакте"
    },
    "max.ru": {
        "src": "./icons/max.svg",
        "label": "Max"
    },
    "wa.me": {
        "src": "./icons/wa.svg",
        "label": "Whatsapp "
    }
}

@app.get("/get-base-links")
async def get_base_links(db: Session = Depends(get_db)):
    base = db.query(BaseLinks).all()
    return {
        "base": base,
    }


@app.get("/create-base-links")
async def create_base_links(name: str, src: str, label: str, db: Session = Depends(get_db)):
    new_base = BaseLinks(
        name=name,
        src=src,
        label=label,
    )
    db.add(new_base)
    db.commit()
    db.refresh(new_base)
    return {
        "message": "Base link created",
    }

@app.delete("/delete-base-links")
async def delete_base_links(link_id: int, db: Session = Depends(get_db)):
    base = db.get(BaseLinks, link_id)
    if base is None:
        raise HTTPException(status_code=404, detail="Base link not found")
    db.delete(base)
    db.commit()

    return {
        "message": "Base link deleted",
    }

@app.post("/update-base-links")
async def update_base_link(baselink_id: int, name: str, src: str, label: str, db: Session = Depends(get_db)):
    base = db.get(BaseLinks, baselink_id)
    if base is None:
        raise HTTPException(status_code=404, detail="Base link not found")
    base.name = name
    base.src = src
    base.label = label
    db.add(base)
    db.commit()
    db.refresh(base)
    return {
        "message": "Base link updated",
    }

@app.get("/start-base-links")
async def start_base_links(db: Session = Depends(get_db)):
    for name, data in LINKS.items():
        await create_base_links(
            name=name,
            src=data["src"],
            label=data["label"],
            db=db
        )

    return {
        "message": "Base links created",
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
