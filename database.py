from sqlalchemy import create_engine, Column, Integer, String, JSON, Float, Boolean, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.ext.mutable import MutableList

DATABASE_URL = "sqlite:///app.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class SaleDB(Base):
    __tablename__ = "sales"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    code = Column(String)

    active = Column(Boolean)
    started_at = Column(DateTime)
    ended_at = Column(DateTime)
    summary = Column(Boolean)
    isProduct = Column(Boolean)

    priority = Column(Integer)
    discount = Column(Float)
    condition = Column(
        MutableList.as_mutable(JSON),
        nullable=False,
        default=list
    )

class UserDB(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    region = Column(String)
    status = Column(String)

class OrderDB(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)
    product_id = Column(
        MutableList.as_mutable(JSON),
        nullable=False,
        default=list
    )
    sale_id = Column(
        MutableList.as_mutable(Integer),
        nullable=False,
        default=list
    )

class ProductDB(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    price = Column(Float)
    card_price = Column(Float)
    category = Column(String)

# links

class BaseLinks(Base):
    __tablename__ = "base_links"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    src = Column(String)
    label = Column(String)

class LinksDB(Base):
    __tablename__ = "links"
    id = Column(Integer, primary_key=True)
    icon = Column(String)
    link = Column(String)
    label = Column(String)
    store_id = Column(Integer)

class StoreDB(Base):
    __tablename__ = "stores"
    id = Column(Integer, primary_key=True)
    title = Column(String)
    subtitle = Column(String)
    image = Column(String)
    client_id = Column(Integer)

class ClientsDB(Base):
    __tablename__ = "clients"
    id = Column(Integer, primary_key=True)
    mail = Column(String, nullable=True)
    login = Column(String)
    password = Column(String)



Base.metadata.create_all(bind=engine)