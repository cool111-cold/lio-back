from sqlalchemy import create_engine, Column, Integer, String, JSON, Float, Boolean, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.ext.mutable import MutableList

DATABASE_URL = "sqlite:///app.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

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
    metric = Column(Integer, default=0)

class StoreDB(Base):
    __tablename__ = "stores"
    id = Column(Integer, primary_key=True)
    title = Column(String)
    subtitle = Column(String)
    image = Column(String)
    client_id = Column(Integer)
    isMain = Column(Boolean, default=False)

class ClientsDB(Base):
    __tablename__ = "clients"
    id = Column(Integer, primary_key=True)
    mail = Column(String, nullable=True)
    login = Column(String)
    password = Column(String)


class CodesDB(Base):
    __tablename__ = "codes"
    id = Column(Integer, primary_key=True)
    code = Column(String)
    store_id = Column(Integer, nullable=True)

class CrmUsersDB(Base):
    __tablename__ = "crm_users"
    id = Column(Integer, primary_key=True)
    login = Column(String)
    password = Column(String)
    status = Column(String, default="user")


Base.metadata.create_all(bind=engine)