"""Барча жадваллар."""
from __future__ import annotations
import datetime, enum, hashlib, re
from sqlalchemy import (
    BigInteger, Boolean, DateTime, Enum, ForeignKey,
    Integer, Numeric, String, Text, UniqueConstraint, func
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database import Base


# ── Enumlar ─────────────────────────────────────────────────────────

class UserRole(str, enum.Enum):
    SUPER_ADMIN = "super_admin"
    ADMIN       = "admin"
    MANAGER     = "manager"
    EMPLOYEE    = "employee"

class SubPlan(str, enum.Enum):
    BASIC    = "basic"     # Admin belgilagan cheklov
    STANDARD = "standard"  # Admin belgilagan cheklov
    PREMIUM  = "premium"   # Admin belgilagan cheklov

class SubStatus(str, enum.Enum):
    ACTIVE  = "active"
    EXPIRED = "expired"
    TRIAL   = "trial"

class DocStatus(str, enum.Enum):
    CREATED  = "created"
    RECEIVED = "received"

class DocType(str, enum.Enum):
    CHIQIM    = "chiqim"
    QAYTARISH = "qaytarish"


# ── Tashkilot ────────────────────────────────────────────────────────

class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[int]          = mapped_column(primary_key=True)
    name: Mapped[str]        = mapped_column(String(255))
    object_text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    users:    Mapped[list["User"]]       = relationship(back_populates="org")
    materials:Mapped[list["Material"]]   = relationship(back_populates="org")
    vehicles: Mapped[list["Vehicle"]]    = relationship(back_populates="org")
    sub:      Mapped["Subscription"]     = relationship(back_populates="org", uselist=False)
    counters: Mapped[list["NakCounter"]] = relationship(back_populates="org")
    allowed:  Mapped[list["AllowedPhone"]]= relationship(back_populates="org")
    plan_cfg: Mapped[list["PlanConfig"]] = relationship(back_populates="org")


class AllowedPhone(Base):
    __tablename__ = "allowed_phones"
    __table_args__ = (UniqueConstraint("phone_number"),)
    id: Mapped[int]              = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"))
    phone_number: Mapped[str]    = mapped_column(String(20), index=True)
    full_name: Mapped[str]       = mapped_column(String(255))
    role: Mapped[UserRole]       = mapped_column(Enum(UserRole), default=UserRole.EMPLOYEE)
    position: Mapped[str]        = mapped_column(String(255), default="")
    org: Mapped["Organization"]  = relationship(back_populates="allowed")


# ── Foydalanuvchi ────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"
    id: Mapped[int]            = mapped_column(primary_key=True)
    telegram_id: Mapped[int]   = mapped_column(BigInteger, unique=True, index=True)
    phone: Mapped[str]         = mapped_column(String(20), index=True)
    full_name: Mapped[str]     = mapped_column(String(255), default="")
    username: Mapped[str]      = mapped_column(String(64), unique=True, index=True)
    pw_hash: Mapped[str]       = mapped_column(String(128), default="")
    role: Mapped[UserRole]     = mapped_column(Enum(UserRole), default=UserRole.EMPLOYEE)
    organization_id: Mapped[int|None] = mapped_column(ForeignKey("organizations.id"), nullable=True)
    position: Mapped[str]      = mapped_column(String(255), default="")
    is_active: Mapped[bool]    = mapped_column(Boolean, default=True)
    is_frozen: Mapped[bool]    = mapped_column(Boolean, default=False)  # tekshirish rejimi
    language: Mapped[str]      = mapped_column(String(5), default="uz")
    last_seen: Mapped[datetime.datetime|None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime.datetime]     = mapped_column(DateTime(timezone=True), server_default=func.now())

    org:  Mapped["Organization"] = relationship(back_populates="users")
    docs: Mapped[list["Nakladnaya"]] = relationship(back_populates="creator")

    @staticmethod
    def gen_username(full_name: str, tg_id: int) -> str:
        parts = full_name.strip().lower().split()
        base  = "_".join(re.sub(r"[^\w]", "", p, flags=re.UNICODE) for p in parts[:2]) or "user"
        return f"{base}_{str(tg_id)[-4:]}"

    def set_pw(self, raw: str):
        self.pw_hash = hashlib.sha256(raw.encode()).hexdigest()

    def check_pw(self, raw: str) -> bool:
        return self.pw_hash == hashlib.sha256(raw.encode()).hexdigest()


# ── Obuna ────────────────────────────────────────────────────────────

class PlanConfig(Base):
    """
    Admin har bir tarif uchun:
    - Nima chiqadi (funksiyalar)
    - Narx
    - Limit (nakladnoy soni)
    ni o'zi belgilaydi.
    """
    __tablename__ = "plan_configs"
    __table_args__ = (UniqueConstraint("organization_id", "plan"),)
    id: Mapped[int]              = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"))
    plan: Mapped[SubPlan]        = mapped_column(Enum(SubPlan))
    name: Mapped[str]            = mapped_column(String(100), default="")      # Tarif nomi (admin belgilaydi)
    description: Mapped[str]     = mapped_column(Text, default="")             # Tavsif
    price: Mapped[float]         = mapped_column(Numeric(12,2), default=0)
    currency: Mapped[str]        = mapped_column(String(10), default="UZS")
    doc_limit: Mapped[int]       = mapped_column(Integer, default=10)          # Oy/cheklov soni
    # Qaysi formatlar ochiq
    allow_excel: Mapped[bool]    = mapped_column(Boolean, default=True)
    allow_word:  Mapped[bool]    = mapped_column(Boolean, default=False)
    allow_pdf:   Mapped[bool]    = mapped_column(Boolean, default=False)
    # Qo'shimcha funksiyalar
    allow_ocr:       Mapped[bool] = mapped_column(Boolean, default=False)
    allow_report:    Mapped[bool] = mapped_column(Boolean, default=False)
    allow_transport: Mapped[bool] = mapped_column(Boolean, default=False)
    allow_calc:      Mapped[bool] = mapped_column(Boolean, default=True)
    allow_templates: Mapped[int]  = mapped_column(Integer, default=2)
    unlimited:       Mapped[bool] = mapped_column(Boolean, default=False)
    # Gemini AI funksiyalar
    allow_ai_calc:      Mapped[bool] = mapped_column(Boolean, default=False)
    allow_ai_chat:      Mapped[bool] = mapped_column(Boolean, default=False)
    allow_ai_search:    Mapped[bool] = mapped_column(Boolean, default=False)
    allow_ai_report:    Mapped[bool] = mapped_column(Boolean, default=False)
    allow_ai_anomaly:   Mapped[bool] = mapped_column(Boolean, default=False)
    allow_ai_briefing:  Mapped[bool] = mapped_column(Boolean, default=False)
    allow_ai_voice:     Mapped[bool] = mapped_column(Boolean, default=False)
    allow_ai_translate: Mapped[bool] = mapped_column(Boolean, default=False)

    org: Mapped["Organization"] = relationship(back_populates="plan_cfg")


class Subscription(Base):
    __tablename__ = "subscriptions"
    id: Mapped[int]              = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), unique=True)
    plan: Mapped[SubPlan]        = mapped_column(Enum(SubPlan), default=SubPlan.BASIC)
    status: Mapped[SubStatus]    = mapped_column(Enum(SubStatus), default=SubStatus.TRIAL)
    docs_used: Mapped[int]       = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime.datetime|None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_by: Mapped[str]      = mapped_column(String(255), default="")
    org: Mapped["Organization"]  = relationship(back_populates="sub")

    def can_create(self, cfg: PlanConfig|None) -> tuple[bool, str]:
        if self.status == SubStatus.EXPIRED:
            return False, "expired"
        if cfg and not cfg.unlimited and self.docs_used >= cfg.doc_limit:
            return False, f"limit:{self.docs_used}/{cfg.doc_limit}"
        return True, ""


# ── Mahsulot bazasi ──────────────────────────────────────────────────

class Material(Base):
    __tablename__ = "materials"
    __table_args__ = (UniqueConstraint("organization_id", "code"),)
    id: Mapped[int]              = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"))
    code: Mapped[str]            = mapped_column(String(50), index=True)
    name: Mapped[str]            = mapped_column(String(500))
    unit: Mapped[str]            = mapped_column(String(20))
    qty_on_hand: Mapped[float|None] = mapped_column(Numeric(14,3), nullable=True)
    org: Mapped["Organization"]  = relationship(back_populates="materials")


# ── Transport ─────────────────────────────────────────────────────────

class Vehicle(Base):
    __tablename__ = "vehicles"
    __table_args__ = (UniqueConstraint("organization_id", "plate"),)
    id: Mapped[int]              = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"))
    plate: Mapped[str]           = mapped_column(String(20))
    model: Mapped[str]           = mapped_column(String(100), default="")
    driver: Mapped[str]          = mapped_column(String(255), default="")
    org: Mapped["Organization"]  = relationship(back_populates="vehicles")


# ── Raqamlash ─────────────────────────────────────────────────────────

class NakCounter(Base):
    __tablename__ = "nak_counters"
    __table_args__ = (UniqueConstraint("organization_id", "year"),)
    id: Mapped[int]              = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"))
    year: Mapped[int]            = mapped_column()
    last_num: Mapped[int]        = mapped_column(default=0)
    org: Mapped["Organization"]  = relationship(back_populates="counters")


# ── Nakladnoy ─────────────────────────────────────────────────────────

class Nakladnaya(Base):
    __tablename__ = "nakladnaya"
    id: Mapped[int]              = mapped_column(primary_key=True)
    number: Mapped[str]          = mapped_column(String(30), index=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"))
    creator_id: Mapped[int]      = mapped_column(ForeignKey("users.id"))
    doc_type: Mapped[DocType]    = mapped_column(Enum(DocType), default=DocType.CHIQIM)
    object_text: Mapped[str]     = mapped_column(Text, default="")
    sender: Mapped[str]          = mapped_column(String(255), default="")
    receiver: Mapped[str]        = mapped_column(String(255), default="")
    vehicle_plate: Mapped[str]   = mapped_column(String(20), default="")
    vehicle_model: Mapped[str]   = mapped_column(String(100), default="")
    driver: Mapped[str]          = mapped_column(String(255), default="")
    destination: Mapped[str]     = mapped_column(Text, default="")
    template_id: Mapped[int]     = mapped_column(Integer, default=1)
    status: Mapped[DocStatus]    = mapped_column(Enum(DocStatus), default=DocStatus.CREATED)
    pin: Mapped[str]             = mapped_column(String(6), default="")
    source: Mapped[str]          = mapped_column(String(20), default="manual")  # manual | ocr
    preview_file_id: Mapped[str|None] = mapped_column(String(255), nullable=True)  # Telegram file_id
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    received_at: Mapped[datetime.datetime|None] = mapped_column(DateTime(timezone=True), nullable=True)

    items:   Mapped[list["NakItem"]] = relationship(back_populates="doc", cascade="all, delete-orphan")
    creator: Mapped["User"]          = relationship(back_populates="docs")


class NakItem(Base):
    __tablename__ = "nak_items"
    id: Mapped[int]           = mapped_column(primary_key=True)
    doc_id: Mapped[int]       = mapped_column(ForeignKey("nakladnaya.id"))
    row_no: Mapped[int]       = mapped_column()
    code: Mapped[str]         = mapped_column(String(50), default="")
    name: Mapped[str]         = mapped_column(String(500))
    unit: Mapped[str]         = mapped_column(String(20))
    quantity: Mapped[str]     = mapped_column(String(30))
    doc: Mapped["Nakladnaya"] = relationship(back_populates="items")


# ── Audit ─────────────────────────────────────────────────────────────

class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int]             = mapped_column(primary_key=True)
    user_id: Mapped[int|None]   = mapped_column(ForeignKey("users.id"), nullable=True)
    org_id: Mapped[int|None]    = mapped_column(ForeignKey("organizations.id"), nullable=True)
    action: Mapped[str]         = mapped_column(String(100))
    detail: Mapped[str]         = mapped_column(Text, default="")
    suspicious: Mapped[bool]    = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
