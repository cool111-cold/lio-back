from fastapi import HTTPException
from fastapi import FastAPI, Depends, Form, Request, UploadFile, File, Query
from fastapi.staticfiles import StaticFiles
from typing import Optional
from fastapi.middleware.cors import CORSMiddleware
from pip._internal.models.link import Link

from database import SessionLocal, ClientsDB, LinksDB, StoreDB, BaseLinks, CodesDB, CrmUsersDB
from sqlalchemy.orm import Session
from local_types import Client, ClientLogin, Store, CrmUser, CrmUserUpdate
from auth import (
    hash_password, verify_password, create_access_token, get_current_client_id, get_optional_client_id,
    create_crm_access_token, get_current_crm_user, get_current_crm_admin,
)
from datetime import datetime
from time import perf_counter
from contextlib import asynccontextmanager
from urllib.parse import urlparse
import secrets
import os
import uuid
import mimetypes

#  source .venv/bin/activate
# uvicorn api:app --no-access-log --loop uvloop --http httptools

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://vapira.ru"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

DEFAULT_STORE_IMAGE = "/uploads/def.jpg"

ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif", "image/jpg"}
MAX_IMAGE_SIZE = 10 * 1024 * 1024
MAX_GIF_SIZE = 20 * 1024 * 1024
UPLOAD_CHUNK_SIZE = 1024 * 1024

def save_image(image: UploadFile) -> str:
    if image.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported image type")
    max_size = MAX_GIF_SIZE if image.content_type == "image/gif" else MAX_IMAGE_SIZE
    ext = os.path.splitext(image.filename or "")[1] or mimetypes.guess_extension(image.content_type) or ""
    filename = f"{uuid.uuid4().hex}{ext}"
    path = os.path.join(UPLOAD_DIR, filename)
    size = 0
    try:
        with open(path, "wb") as f:
            while chunk := image.file.read(UPLOAD_CHUNK_SIZE):
                size += len(chunk)
                if size > max_size:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Image too large (max {max_size // (1024 * 1024)}MB)",
                    )
                f.write(chunk)
    except HTTPException:
        if os.path.isfile(path):
            os.remove(path)
        raise
    return f"/uploads/{filename}"

def delete_uploaded_file(url: Optional[str]):
    if not url or not url.startswith("/uploads/") or url == DEFAULT_STORE_IMAGE:
        return
    path = os.path.join(UPLOAD_DIR, os.path.basename(url))
    if os.path.isfile(path):
        try:
            os.remove(path)
        except OSError:
            pass

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
async def create_link(
    link: str = Query(...),
    label: Optional[str] = Query(None),
    image: Optional[UploadFile] = File(None),
    client_id: int = Depends(get_current_client_id),
    db: Session = Depends(get_db),
):
    store = db.query(StoreDB).filter(StoreDB.client_id == client_id, StoreDB.isMain == True).first()
    if store is None:
        raise HTTPException(status_code=404, detail="Store not found")

    icon_url = save_image(image) if image is not None and image.filename else None

    parsed_url = urlparse(link)
    base = db.query(BaseLinks).filter(BaseLinks.name == parsed_url.netloc).first()
    if icon_url is not None:
        new_link = LinksDB(
            icon=icon_url,
            link=link,
            label=label if label is not None else (base.label if base is not None else parsed_url.netloc),
            store_id=store.id,
        )
    elif base is not None:
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
        "link": new_link,
    }

@app.post("/delete-link")
async def delete_link(link_id: int, client_id: int = Depends(get_current_client_id), db: Session = Depends(get_db)):
    link = db.get(LinksDB, link_id)
    if link is None:
        raise HTTPException(status_code=404, detail="Link not found")
    store = db.get(StoreDB, link.store_id)
    if store is None or store.client_id != client_id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this link")
    old_icon = link.icon
    db.delete(link)
    db.commit()
    delete_uploaded_file(old_icon)
    return {
        "message": "Link deleted",
    }

@app.post("/update-link")
async def update_link(
    link_id: int,
    link: str = Query(...),
    label: Optional[str] = Query(None),
    image: Optional[UploadFile] = File(None),
    client_id: int = Depends(get_current_client_id),
    db: Session = Depends(get_db),
):
    local_link = db.get(LinksDB, link_id)
    if local_link is None:
        raise HTTPException(status_code=404, detail="Link not found")
    store = db.get(StoreDB, local_link.store_id)
    if store is None or store.client_id != client_id:
        raise HTTPException(status_code=403, detail="Not authorized to update this link")

    icon_url = save_image(image) if image is not None and image.filename else None

    parsed_url = urlparse(link)
    base = db.query(BaseLinks).filter(BaseLinks.name == parsed_url.netloc).first()
    old_icon = local_link.icon
    local_link.link = link
    if icon_url is not None:
        local_link.icon = icon_url
    elif base is not None:
        local_link.icon = base.src
    else:
        local_link.icon = None

    if label is not None:
        local_link.label = label
    elif base is not None:
        local_link.label = base.label
    else:
        local_link.label = parsed_url.netloc

    db.add(local_link)
    db.commit()
    db.refresh(local_link)
    if local_link.icon != old_icon:
        delete_uploaded_file(old_icon)
    return {
        "message": "Link updated",
        "link": local_link,
    }

@app.post("/create-store")
async def create_store(store: Optional[Store] = None, reference_id: Optional[int] = None, client_id: int = Depends(get_current_client_id), db: Session = Depends(get_db)):
    if reference_id is None:
        new_store = StoreDB(
            title=store.title,
            subtitle=store.subtitle,
            image=store.image,
            client_id=client_id,
            isMain=False,
        )
    else:
        old_store = db.get(StoreDB, reference_id)
        if old_store is None:
            raise HTTPException(status_code=404, detail="Store not found")
        new_store = StoreDB(
            title=old_store.title,
            subtitle=old_store.subtitle,
            image=old_store.image,
            client_id=client_id,
            isMain=False,
        )
    db.add(new_store)
    db.commit()
    db.refresh(new_store)
    return {
        "message": "Store created",
        "store": new_store.id,
    }


@app.post("/change-main-store")
async def change_main_store(store_id: int, client_id: int = Depends(get_current_client_id), db: Session = Depends(get_db)):
    store = db.query(StoreDB).filter(StoreDB.id == store_id, StoreDB.client_id == client_id).first()
    old_main_store = db.query(StoreDB).filter(StoreDB.client_id == client_id, StoreDB.isMain == True).first()
    if store is None:
        raise HTTPException(status_code=404, detail="Store not found")
    if old_main_store is None:
        raise HTTPException(status_code=404, detail="Store not found")
    store.isMain = True
    old_main_store.isMain = False
    db.commit()
    db.refresh(old_main_store)
    return {
        "message": "Main store changed",
        "store": store.id,

    }


@app.get("/get-my-store")
async def get_stor_by_id(client_id: int = Depends(get_current_client_id), db: Session = Depends(get_db)):
    store = db.query(StoreDB).filter(StoreDB.client_id == client_id, StoreDB.isMain == True).first()
    if store is None:
        store = StoreDB(
            client_id=client_id,
            title="Название",
            subtitle="Описание / адрес",
            image=DEFAULT_STORE_IMAGE,
            isMain=True,
        )
        db.add(store)
        db.commit()
        db.refresh(store)
    client = db.get(ClientsDB, client_id)
    return {
        "store_id": store.id,
        "mail": client.mail,
    }

@app.get("/get-my-stories")
def get_my_stories(offset: int = 0, limit: int = 0, client_id: int = Depends(get_current_client_id), db: Session = Depends(get_db)):
    stores = db.query(StoreDB).filter(StoreDB.client_id == client_id).offset(offset).limit(limit).all()
    if stores is None:
        raise HTTPException(status_code=404, detail="Store not found")
    return {
        "stores": stores,
        "offset": offset,
        "limit": limit,
    }

@app.post("/delete-store")
async def delete_store(store_id: int, client_id: int = Depends(get_current_client_id), db: Session = Depends(get_db)):
    store = db.get(StoreDB, store_id)
    if store is None:
        raise HTTPException(status_code=404, detail="Store not found")
    if store.client_id != client_id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this store")
    old_image = store.image
    db.delete(store)
    db.commit()
    delete_uploaded_file(old_image)
    return {
        "message": "Store deleted",
    }

@app.post("/update-store")
async def update_store(
    store_id: int,
    title: str = Form(...),
    subtitle: str = Form(...),
    image: Optional[UploadFile] = File(None),
    client_id: int = Depends(get_current_client_id),
    db: Session = Depends(get_db),
):
    local_store = db.get(StoreDB, store_id)
    if local_store is None:
        raise HTTPException(status_code=404, detail="Store not found")
    if local_store.client_id != client_id:
        raise HTTPException(status_code=403, detail="Not authorized to update this store")
    local_store.title = title
    local_store.subtitle = subtitle
    if image is not None and image.filename:
        old_image = local_store.image
        local_store.image = save_image(image)
        delete_uploaded_file(old_image)
    db.add(local_store)
    db.commit()
    db.refresh(local_store)
    return {
        "message": "Store updated",
        "store": local_store,
    }

@app.post("/register")
async def register(client: Client, card: Optional[str] = None, db: Session = Depends(get_db)):
    existing = db.query(ClientsDB).filter(ClientsDB.login == client.login).first()
    if existing is not None:
        raise HTTPException(status_code=400, detail="Login already taken")

    if card is None:
        raise HTTPException(status_code=400, detail="Invalid card")

    code = db.query(CodesDB).filter(CodesDB.code == card).first()
    if code is None:
        raise HTTPException(status_code=400, detail="Invalid card")

    new_client = ClientsDB(
        mail=client.mail,
        login=client.login,
        password=hash_password(client.password),
    )
    db.add(new_client)
    db.flush()

    new_store = StoreDB(
        client_id=new_client.id,
        title="Название",
        subtitle="Описание / адрес",
        image=DEFAULT_STORE_IMAGE,
        isMain=True,
    )
    db.add(new_store)
    db.flush()

    code.store_id = new_store.id
    db.add(code)

    db.commit()
    db.refresh(new_client)
    token = create_access_token(new_client.id)
    return {
        "message": "Client registered",
        "access_token": token,
        "token_type": "bearer",
    }

@app.post("/login")
async def login(credentials: ClientLogin, card: Optional[str] = None, db: Session = Depends(get_db)):
    client = db.query(ClientsDB).filter(ClientsDB.login == credentials.login).first()
    if client is None or not verify_password(credentials.password, client.password):
        raise HTTPException(status_code=401, detail="Invalid login or password")

    token = create_access_token(client.id)
    if card is not None:
        code = db.query(CodesDB).filter(CodesDB.code == card).first()
        new_store_id = db.query(StoreDB).filter(StoreDB.client_id == client.id, StoreDB.isMain == True).first()
        code.store_id = new_store_id.id
        db.add(code)
        db.commit()
        db.refresh(code)

    return {
        "message": "Login successful",
        "access_token": token,
        "token_type": "bearer",
    }

@app.post("/delete-client")
async def delete_client(client_id: int = Depends(get_current_client_id), db: Session = Depends(get_db)):
    client = db.get(ClientsDB, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found")
    stores = db.query(StoreDB).filter(StoreDB.client_id == client.id).all()

    icon_files = []
    store_images = []
    for store in stores:
        codes = db.query(CodesDB).filter(CodesDB.store_id == store.id).all()
        for code in codes:
            code.store_id = None

        links = db.query(LinksDB).filter(LinksDB.store_id == store.id).all()
        icon_files.extend(link.icon for link in links)
        for link in links:
            db.delete(link)

        store_images.append(store.image)
        db.delete(store)

    db.delete(client)
    db.commit()

    for icon in icon_files:
        delete_uploaded_file(icon)
    for store_image in store_images:
        delete_uploaded_file(store_image)

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

@app.get("/get-code")
async def get_code(
    code_id: str,
    db: Session = Depends(get_db),
    client_id: Optional[int] = Depends(get_optional_client_id),
):

    code = db.query(CodesDB).filter(CodesDB.code == code_id).first()
    if code is None:
        raise HTTPException(status_code=404, detail="Code not found")

    if code.store_id is None:
        if client_id is None:
            return {
                "message": "registration",
                "link": f"/admin/{code_id}"
            }
        else:
            new_store_id = db.query(StoreDB).filter(StoreDB.client_id == client_id, StoreDB.isMain == True).first()
            code.store_id = new_store_id.id
            db.add(code)
            db.commit()
            db.refresh(code)

            return {
                "message": "Code updated",
                "link": f"/{code.store_id}"
            }
    else:
        return {
            "message": 'redirect',
            "link": f"/{code.store_id}"
        }

@app.get("/get-my-codes")
async def get_my_codes(offset: int = 0, limit: int = 10, client_id: int = Depends(get_current_client_id), db: Session = Depends(get_db)):
    store = db.query(StoreDB).filter(StoreDB.client_id == client_id, StoreDB.isMain == True).first()
    if store is None:
        raise HTTPException(status_code=404, detail="Store not found")
    codes = db.query(CodesDB).filter(CodesDB.store_id == store.id).offset(offset).limit(limit).all()
    return {
        "codes": codes,
        "offset": offset,
        "limit": limit,
    }

def generate_unique_code(db: Session, length: int = 16) -> str:
    while True:
        code = secrets.token_urlsafe(length)
        exists = db.query(CodesDB).filter(CodesDB.code == code).first()
        if exists is None:
            return code

@app.post("/reset-store-from-code")
async def reset_store_from_code(code_id: int, client_id: int = Depends(get_current_client_id), db: Session = Depends(get_db)):
    code = db.get(CodesDB, code_id)
    if code is None:
        raise HTTPException(status_code=404, detail="Code not found")
    if code.store_id is None:
        raise HTTPException(status_code=404, detail="Code not found")
    store = db.get(StoreDB, code.store_id)
    if store is None or store.client_id != client_id:
        raise HTTPException(status_code=403, detail="Not authorized to reset this code")
    code.store_id = None
    db.add(code)
    db.commit()
    db.refresh(code)
    return {
        "message": f"Code {code_id} reset",
    }

@app.post("/metric")
async def metric(link_id: int, db: Session = Depends(get_db)):
    link = db.get(LinksDB, link_id)
    if link is None:
        raise HTTPException(status_code=404, detail="Link not found")
    link.metric = link.metric + 1
    db.add(link)
    db.commit()
    db.refresh(link)

    return {
        "message": 'success',
    }


def crm_user_to_dict(user: CrmUsersDB) -> dict:
    return {"id": user.id, "login": user.login, "status": user.status}

@app.post("/crm/init-admin")
async def crm_init_admin(credentials: ClientLogin, db: Session = Depends(get_db)):
    # Первый админ создаётся без авторизации, но только пока в базе нет ни одного админа
    if db.query(CrmUsersDB).filter(CrmUsersDB.status == "admin").first() is not None:
        raise HTTPException(status_code=403, detail="Admin already exists")
    if db.query(CrmUsersDB).filter(CrmUsersDB.login == credentials.login).first() is not None:
        raise HTTPException(status_code=400, detail="Login already taken")
    admin = CrmUsersDB(
        login=credentials.login,
        password=hash_password(credentials.password),
        status="admin",
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return {
        "message": "Admin created",
        "access_token": create_crm_access_token(admin.id),
        "token_type": "bearer",
    }

@app.post("/crm/login")
async def crm_login(credentials: ClientLogin, db: Session = Depends(get_db)):
    user = db.query(CrmUsersDB).filter(CrmUsersDB.login == credentials.login).first()
    if user is None or not verify_password(credentials.password, user.password):
        raise HTTPException(status_code=401, detail="Invalid login or password")
    return {
        "message": "Login successful",
        "access_token": create_crm_access_token(user.id),
        "token_type": "bearer",
        "user": crm_user_to_dict(user),
    }

@app.get("/crm/me")
async def crm_me(user: CrmUsersDB = Depends(get_current_crm_user)):
    return {
        "user": crm_user_to_dict(user),
    }

@app.get("/crm/get-users")
async def crm_get_users(db: Session = Depends(get_db)):
    users = db.query(CrmUsersDB).all()
    return {
        "users": [crm_user_to_dict(u) for u in users],
    }

@app.post("/crm/create-user")
async def crm_create_user(user: CrmUser, admin: CrmUsersDB = Depends(get_current_crm_admin), db: Session = Depends(get_db)):
    if db.query(CrmUsersDB).filter(CrmUsersDB.login == user.login).first() is not None:
        raise HTTPException(status_code=400, detail="Login already taken")
    new_user = CrmUsersDB(
        login=user.login,
        password=hash_password(user.password),
        status=user.status,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {
        "message": "CRM user created",
        "user": crm_user_to_dict(new_user),
    }

@app.post("/crm/update-user")
async def crm_update_user(user_id: int, user: CrmUserUpdate, admin: CrmUsersDB = Depends(get_current_crm_admin), db: Session = Depends(get_db)):
    local_user = db.get(CrmUsersDB, user_id)
    if local_user is None:
        raise HTTPException(status_code=404, detail="CRM user not found")
    if user.login is not None and user.login != local_user.login:
        if db.query(CrmUsersDB).filter(CrmUsersDB.login == user.login).first() is not None:
            raise HTTPException(status_code=400, detail="Login already taken")
        local_user.login = user.login
    if user.password is not None:
        local_user.password = hash_password(user.password)
    if user.status is not None:
        if local_user.id == admin.id and user.status != "admin":
            raise HTTPException(status_code=400, detail="Cannot remove admin rights from yourself")
        local_user.status = user.status
    db.add(local_user)
    db.commit()
    db.refresh(local_user)
    return {
        "message": "CRM user updated",
        "user": crm_user_to_dict(local_user),
    }

@app.delete("/crm/delete-user")
async def crm_delete_user(user_id: int, admin: CrmUsersDB = Depends(get_current_crm_admin), db: Session = Depends(get_db)):
    user = db.get(CrmUsersDB, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="CRM user not found")
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    db.delete(user)
    db.commit()
    return {
        "message": "CRM user deleted",
    }
@app.get("/crm/get-clients")
async def get_clients(offset: int = 0, limit: int = 10, admin: CrmUsersDB = Depends(get_current_crm_admin), db: Session = Depends(get_db)):
    if admin.status != "admin":
        raise HTTPException(status_code=401, detail="Invalid rules")

    clients = db.query(ClientsDB).offset(offset).limit(limit).all()
    return {
        "clients": [{"id": c.id, "mail": c.mail, "login": c.login} for c in clients],
        "offset": offset,
        "limit": limit,
    }

@app.get("/crm/get-base-links")
async def get_base_links(admin: CrmUsersDB = Depends(get_current_crm_admin), db: Session = Depends(get_db)):
    if admin.status != "admin":
        raise HTTPException(status_code=401, detail="Invalid rules")
    base = db.query(BaseLinks).all()
    return {
        "base": base,
    }


@app.get("/crm/create-base-links")
async def create_base_links(name: str, src: str, label: str, admin: CrmUsersDB = Depends(get_current_crm_admin), db: Session = Depends(get_db)):
    if admin.status != "admin":
        raise HTTPException(status_code=401, detail="Invalid rules")
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

@app.delete("/crm/delete-base-links")
async def delete_base_links(link_id: int, admin: CrmUsersDB = Depends(get_current_crm_admin), db: Session = Depends(get_db)):
    if admin.status != "admin":
        raise HTTPException(status_code=401, detail="Invalid rules")
    base = db.get(BaseLinks, link_id)
    if base is None:
        raise HTTPException(status_code=404, detail="Base link not found")
    db.delete(base)
    db.commit()

    return {
        "message": "Base link deleted",
    }

@app.post("/crm/update-base-links")
async def update_base_link(baselink_id: int, name: str, src: str, label: str, admin: CrmUsersDB = Depends(get_current_crm_admin), db: Session = Depends(get_db)):
    if admin.status != "admin":
        raise HTTPException(status_code=401, detail="Invalid rules")
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

@app.get("/crm/start-base-links")
async def start_base_links(admin: CrmUsersDB = Depends(get_current_crm_admin), db: Session = Depends(get_db)):
    if admin.status != "admin":
        raise HTTPException(status_code=401, detail="Invalid rules")
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

@app.post("/crm/create-code")
async def create_code(admin: CrmUsersDB = Depends(get_current_crm_admin), db: Session = Depends(get_db)):
    if admin.status != "admin":
        raise HTTPException(status_code=401, detail="Invalid rules")
    new_code = CodesDB(
        code=generate_unique_code(db),
    )
    db.add(new_code)
    db.commit()
    db.refresh(new_code)
    return {
        "message": f"Code {new_code.id} created",
    }

@app.delete("/crm/delete-code")
async def delete_code(code_id: int, admin: CrmUsersDB = Depends(get_current_crm_admin), db: Session = Depends(get_db)):
    if admin.status != "admin":
        raise HTTPException(status_code=401, detail="Invalid rules")
    code = db.get(CodesDB, code_id)
    if code is None:
        raise HTTPException(status_code=404, detail="Code not found")
    db.delete(code)
    db.commit()
    return {
        "message": f"Code {code_id} deleted",
    }

@app.get("/crm/get-codes")
async def get_codes(offset: int = 0, limit: int = 10, onlyFree: Optional[bool] = None, onlyBusy: Optional[bool] = False,  admin: CrmUsersDB = Depends(get_current_crm_admin), db: Session = Depends(get_db)):
    if admin.status != "admin":
        raise HTTPException(status_code=401, detail="Invalid rules")
    if onlyFree:
        codes = db.query(CodesDB).filter(CodesDB.store_id == None).offset(offset).limit(limit).all()
    elif onlyBusy:
        codes = db.query(CodesDB).filter(CodesDB.store_id != None).offset(offset).limit(limit).all()
    else:
        codes = db.query(CodesDB).offset(offset).limit(limit).all()
    return {
        "codes": codes,
        "offset": offset,
        "limit": limit,
    }

@app.get("/crm/get-stores")
async def get_stores(offset: int = 0, limit: int = 10, admin: CrmUsersDB = Depends(get_current_crm_admin),  db: Session = Depends(get_db)):
    stores = db.query(StoreDB).offset(offset).limit(limit).all()
    return {
        "stores": stores,
        "offset": offset,
        "limit": limit,
    }