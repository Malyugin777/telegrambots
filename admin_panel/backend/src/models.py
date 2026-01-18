"""
SQLAlchemy models for Admin API.
Mirrors bot_net models for consistency.
"""
from datetime import datetime
from typing import Optional
import enum

from sqlalchemy import (
    BigInteger, Boolean, DateTime, ForeignKey,
    Integer, String, Text, JSON, Enum as SQLEnum, UniqueConstraint
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class UserRole(str, enum.Enum):
    USER = "user"
    MODERATOR = "moderator"
    ADMIN = "admin"
    OWNER = "owner"


class BotStatus(str, enum.Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    MAINTENANCE = "maintenance"
    DISABLED = "disabled"


class BroadcastStatus(str, enum.Enum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    language_code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    role: Mapped[UserRole] = mapped_column(SQLEnum(UserRole), default=UserRole.USER)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)  # Blocked the bot
    ban_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_active_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    extra_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)


class Bot(Base):
    __tablename__ = "bots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bot_id: Mapped[Optional[int]] = mapped_column(BigInteger, unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    token_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    webhook_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    status: Mapped[BotStatus] = mapped_column(SQLEnum(BotStatus), default=BotStatus.ACTIVE)
    settings: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class BotUser(Base):
    __tablename__ = "bot_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id", ondelete="CASCADE"))
    is_subscribed: Mapped[bool] = mapped_column(Boolean, default=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_interaction: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    bot_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)


class Broadcast(Base):
    """Broadcast/mailing model."""
    __tablename__ = "broadcasts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    text: Mapped[str] = mapped_column(Text)
    image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    message_video: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    buttons: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # Inline keyboard

    # Targeting
    target_type: Mapped[str] = mapped_column(String(50), default="all")  # 'all', 'segment', 'list'
    target_bots: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)  # Bot IDs
    target_languages: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)  # ['en', 'ru']
    target_segment_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    target_user_ids: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)  # [telegram_id, ...]

    # Status
    status: Mapped[BroadcastStatus] = mapped_column(SQLEnum(BroadcastStatus), default=BroadcastStatus.DRAFT)
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Stats
    total_recipients: Mapped[int] = mapped_column(Integer, default=0)
    sent_count: Mapped[int] = mapped_column(Integer, default=0)
    delivered_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_by: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Relations
    logs: Mapped[list["BroadcastLog"]] = relationship("BroadcastLog", back_populates="broadcast")


class AdminUser(Base):
    """Admin panel users (separate from Telegram users)."""
    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class ActionLog(Base):
    """Action logging for analytics."""
    __tablename__ = "action_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    bot_id: Mapped[Optional[int]] = mapped_column(ForeignKey("bots.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String(100), index=True)
    details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    # Performance metrics
    download_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    download_speed_kbps: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


class Segment(Base):
    """User segments for targeted broadcasts."""
    __tablename__ = "segments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    conditions: Mapped[dict] = mapped_column(JSON, default=dict)
    cached_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    cached_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_dynamic: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class BroadcastLog(Base):
    """Logs for individual message sends in broadcasts."""
    __tablename__ = "broadcast_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    broadcast_id: Mapped[int] = mapped_column(ForeignKey("broadcasts.id", ondelete="CASCADE"))
    telegram_id: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(50))  # 'sent', 'delivered', 'failed', 'blocked'
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relations
    broadcast: Mapped["Broadcast"] = relationship("Broadcast", back_populates="logs")


class DownloadError(Base):
    """Tracks download errors for monitoring and debugging."""
    __tablename__ = "download_errors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    bot_id: Mapped[Optional[int]] = mapped_column(ForeignKey("bots.id", ondelete="SET NULL"), nullable=True)
    platform: Mapped[str] = mapped_column(String(50), index=True)
    url: Mapped[str] = mapped_column(Text)
    error_type: Mapped[str] = mapped_column(String(100), index=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class SubscriptionProvider(str, enum.Enum):
    AEZA = "aeza"
    HOSTKEY = "hostkey"
    RAPIDAPI = "rapidapi"
    DOMAIN = "domain"
    GITHUB = "github"
    OTHER = "other"


class BillingCycle(str, enum.Enum):
    MONTHLY = "monthly"
    YEARLY = "yearly"
    USAGE = "usage"  # Pay-as-you-go


class SubscriptionStatus(str, enum.Enum):
    ACTIVE = "active"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class Subscription(Base):
    """Billing tracker for services and subscriptions."""
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Provider info
    provider: Mapped[SubscriptionProvider] = mapped_column(
        SQLEnum(SubscriptionProvider), default=SubscriptionProvider.OTHER
    )
    provider_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Billing
    amount: Mapped[float] = mapped_column(default=0.0)
    currency: Mapped[str] = mapped_column(String(3), default="RUB")  # RUB, USD, EUR
    billing_cycle: Mapped[BillingCycle] = mapped_column(
        SQLEnum(BillingCycle), default=BillingCycle.MONTHLY
    )
    next_payment_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Settings
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_days: Mapped[list] = mapped_column(JSON, default=[7, 3, 1])  # Days before to notify
    status: Mapped[SubscriptionStatus] = mapped_column(
        SQLEnum(SubscriptionStatus), default=SubscriptionStatus.ACTIVE
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class BotMessage(Base):
    """Editable bot messages/texts."""
    __tablename__ = "bot_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bot_id: Mapped[int] = mapped_column(Integer, ForeignKey("bots.id"), nullable=False)
    message_key: Mapped[str] = mapped_column(String(50), nullable=False)  # 'start', 'help', etc.
    text_ru: Mapped[str] = mapped_column(Text, nullable=False)
    text_en: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Unique constraint
    __table_args__ = (
        UniqueConstraint('bot_id', 'message_key', name='uq_bot_message_key'),
    )

    # Relationship
    bot: Mapped["Bot"] = relationship("Bot", backref="messages")
