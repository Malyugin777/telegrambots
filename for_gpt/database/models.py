from datetime import datetime
from enum import Enum as PyEnum
from sqlalchemy import (
    Column, Integer, BigInteger, String, DateTime,
    Boolean, Text, Enum, ForeignKey, Index, JSON, Float, UniqueConstraint
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func

Base = declarative_base()


class UserRole(str, PyEnum):
    USER = "user"
    MODERATOR = "moderator"
    ADMIN = "admin"
    OWNER = "owner"


class BotStatus(str, PyEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    PAUSED = "paused"
    MAINTENANCE = "maintenance"
    DISABLED = "disabled"


class APISource(str, PyEnum):
    YTDLP = "ytdlp"
    RAPIDAPI = "rapidapi"
    COBALT = "cobalt"
    PYTUBEFIX = "pytubefix"
    INSTALOADER = "instaloader"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String(255), nullable=True)
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)
    language_code = Column(String(10), default="ru")
    role = Column(Enum(UserRole), default=UserRole.USER)
    is_banned = Column(Boolean, default=False)
    is_blocked = Column(Boolean, default=False)  # User blocked the bot
    ban_reason = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    last_active_at = Column(DateTime, server_default=func.now())
    extra_data = Column(JSON, nullable=True)

    bot_users = relationship("BotUser", back_populates="user")
    action_logs = relationship("ActionLog", back_populates="user")


class Bot(Base):
    __tablename__ = "bots"

    id = Column(Integer, primary_key=True)
    bot_id = Column(BigInteger, unique=True, nullable=False)
    username = Column(String(255), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    token_hash = Column(String(64), nullable=True)
    status = Column(Enum(BotStatus), default=BotStatus.ACTIVE)
    description = Column(Text, nullable=True)
    webhook_url = Column(String(500), nullable=True)
    settings = Column(JSON, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    bot_users = relationship("BotUser", back_populates="bot")
    action_logs = relationship("ActionLog", back_populates="bot")


class BotUser(Base):
    __tablename__ = "bot_users"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    bot_id = Column(Integer, ForeignKey("bots.id", ondelete="CASCADE"), nullable=False)
    is_subscribed = Column(Boolean, default=True)
    joined_at = Column(DateTime, server_default=func.now())
    last_interaction = Column(DateTime, nullable=True)
    bot_data = Column(JSON, nullable=True)

    user = relationship("User", back_populates="bot_users")
    bot = relationship("Bot", back_populates="bot_users")

    __table_args__ = (
        Index("ix_bot_users_user_bot", "user_id", "bot_id", unique=True),
    )


class ActionLog(Base):
    __tablename__ = "action_logs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    bot_id = Column(Integer, ForeignKey("bots.id", ondelete="SET NULL"), nullable=True)
    action = Column(String(100), nullable=False, index=True)
    details = Column(JSON, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), index=True)

    # Performance metrics
    download_time_ms = Column(Integer, nullable=True)
    file_size_bytes = Column(BigInteger, nullable=True)
    download_speed_kbps = Column(Integer, nullable=True)

    # API tracking
    api_source = Column(Enum(APISource), nullable=True, index=True)

    user = relationship("User", back_populates="action_logs")
    bot = relationship("Bot", back_populates="action_logs")


class AdminUser(Base):
    __tablename__ = "admin_users"

    id = Column(Integer, primary_key=True)
    username = Column(String(255), unique=True, nullable=False)
    email = Column(String(255), unique=True, nullable=True)
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())
    last_login = Column(DateTime, nullable=True)


class DownloadError(Base):
    """Tracks download errors for monitoring and debugging."""
    __tablename__ = "download_errors"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    bot_id = Column(Integer, ForeignKey("bots.id", ondelete="SET NULL"), nullable=True)
    platform = Column(String(50), nullable=False, index=True)
    url = Column(Text, nullable=False)
    error_type = Column(String(100), nullable=False, index=True)
    error_message = Column(Text, nullable=True)
    error_details = Column(JSON, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), index=True)

    user = relationship("User")
    bot = relationship("Bot")


class SubscriptionProvider(str, PyEnum):
    AEZA = "aeza"
    HOSTKEY = "hostkey"
    RAPIDAPI = "rapidapi"
    DOMAIN = "domain"
    GITHUB = "github"
    OTHER = "other"


class BillingCycle(str, PyEnum):
    MONTHLY = "monthly"
    YEARLY = "yearly"
    USAGE = "usage"


class SubscriptionStatus(str, PyEnum):
    ACTIVE = "active"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class Subscription(Base):
    """Billing tracker for services and subscriptions."""
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)

    # Provider info
    provider = Column(Enum(SubscriptionProvider), default=SubscriptionProvider.OTHER)
    provider_url = Column(String(500), nullable=True)

    # Billing
    amount = Column(Float, default=0.0)
    currency = Column(String(3), default="RUB")
    billing_cycle = Column(Enum(BillingCycle), default=BillingCycle.MONTHLY)
    next_payment_date = Column(DateTime, nullable=True)

    # Settings
    auto_renew = Column(Boolean, default=True)
    notify_days = Column(JSON, default=[7, 3, 1])
    status = Column(Enum(SubscriptionStatus), default=SubscriptionStatus.ACTIVE)

    # Timestamps
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class BroadcastStatus(str, PyEnum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Broadcast(Base):
    """Broadcast/mailing model."""
    __tablename__ = "broadcasts"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    text = Column(Text, nullable=False)
    image_url = Column(String(500), nullable=True)
    message_video = Column(String(500), nullable=True)
    buttons = Column(JSON, nullable=True)  # Inline keyboard

    # Targeting
    target_type = Column(String(50), default="all")  # 'all', 'segment', 'list'
    target_bots = Column(JSON, nullable=True)  # Bot IDs
    target_languages = Column(JSON, nullable=True)  # ['en', 'ru']
    target_segment_id = Column(Integer, nullable=True)
    target_user_ids = Column(JSON, nullable=True)  # [telegram_id, ...]

    # Status
    status = Column(Enum(BroadcastStatus), default=BroadcastStatus.DRAFT)
    scheduled_at = Column(DateTime, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Stats
    total_recipients = Column(Integer, default=0)
    sent_count = Column(Integer, default=0)
    delivered_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)

    created_at = Column(DateTime, server_default=func.now())
    created_by = Column(Integer, nullable=True)

    # Relations
    logs = relationship("BroadcastLog", back_populates="broadcast")


class BroadcastLog(Base):
    """Logs for individual message sends in broadcasts."""
    __tablename__ = "broadcast_logs"

    id = Column(Integer, primary_key=True)
    broadcast_id = Column(Integer, ForeignKey("broadcasts.id", ondelete="CASCADE"), nullable=False)
    telegram_id = Column(BigInteger, nullable=False)
    status = Column(String(50), nullable=False)  # 'sent', 'delivered', 'failed', 'blocked'
    error_message = Column(Text, nullable=True)
    sent_at = Column(DateTime, server_default=func.now())

    # Relations
    broadcast = relationship("Broadcast", back_populates="logs")


class Segment(Base):
    """User segments for targeted broadcasts."""
    __tablename__ = "segments"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    conditions = Column(JSON, default=dict)
    cached_count = Column(Integer, nullable=True)
    cached_at = Column(DateTime, nullable=True)
    is_dynamic = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class BotMessage(Base):
    """Editable bot messages/texts."""
    __tablename__ = "bot_messages"

    id = Column(Integer, primary_key=True)
    bot_id = Column(Integer, ForeignKey("bots.id", ondelete="CASCADE"), nullable=False)
    message_key = Column(String(50), nullable=False)  # 'start', 'help', etc.
    text_ru = Column(Text, nullable=False)
    text_en = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Unique constraint
    __table_args__ = (
        UniqueConstraint('bot_id', 'message_key', name='uq_bot_message_key'),
    )

    # Relationship
    bot = relationship("Bot", backref="messages")
