"""
api/db/models.py – SQLAlchemy ORM model cho bảng `food`.

Không tạo bảng (schema do build_pack_online.py tạo sẵn).
Chỉ map Python class ↔ SQLite table.
"""
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class Food(Base):
    __tablename__ = "food"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    ten_quan     = Column(String,  nullable=True, default="")
    ten_mon      = Column(String,  nullable=True, default="")
    dia_chi      = Column(String,  nullable=True, default="")
    quan         = Column(String,  nullable=True, default="")
    thanh_pho    = Column(String,  nullable=True, default="")
    gia_min      = Column(Integer, nullable=True, default=0)
    gia_max      = Column(Integer, nullable=True, default=0)
    note         = Column(String,  nullable=True, default="")
    so_lan_click = Column(Integer, nullable=True, default=0)

    def __repr__(self) -> str:
        return f"<Food id={self.id} ten_quan={self.ten_quan!r}>"
