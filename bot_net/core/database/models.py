"""
SQLAlchemy models for the bot network.
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, JSON, Enum as SQLEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
import enum


class Base(DeclarativeBase):
    """Base class for all models."""
    pass


class UserRole(str, enum.Enum):
    """User roles in the system."""
    USER = "user"
    MODERATOR = "moderator"
    ADMIN = "admin"
    OWNER = "owner"


class BotStatus(str, enum.Enum):
    """Bot operational status."""
    ACTIVE = "active"
    PAUSED = "paused"
    MAINTENANCE = "maintenance"
    DISABLED = "disabled"


class User(Base):
    """
    Telegram user model.
    Stores users across all bots in the network.
    """
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    language_code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

    role: Mapped[UserRole] = mapped_column(
        SQLEnum(UserRole), default=UserRole.USER, server_default="user"
    )
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    ban_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default="now()"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    last_active_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Extra data (JSON for flexibility)
    extra_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Relationships
    bot_users: Mapped[list["BotUser"]] = relationship(back_populates="user", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<User {self.telegram_id} @{self.username}>"


class Bot(Base):
    """
    Bot configuration model.
    Each bot in the network is registered here.
    """
    __tablename__ = "bots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    token_hash: Mapped[str] = mapped_column(String(64))  # SHA-256 hash of token
    bot_username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    status: Mapped[BotStatus] = mapped_column(
        SQLEnum(BotStatus), default=BotStatus.ACTIVE, server_default="active"
    )

    # Settings (JSON for flexibility)
    settings: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default="now()"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    bot_users: Mapped[list["BotUser"]] = relationship(back_populates="bot", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Bot {self.name}>"


class BotUser(Base):
    """
    Many-to-many relationship between users and bots.
    Tracks which users interact with which bots.
    """
    __tablename__ = "bot_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id", ondelete="CASCADE"))

    # Bot-specific user data
    is_subscribed: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    joined_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default="now()"
    )
    last_interaction: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Bot-specific extra data
    bot_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="bot_users")
    bot: Mapped["Bot"] = relationship(back_populates="bot_users")

    def __repr__(self) -> str:
        return f"<BotUser user={self.user_id} bot={self.bot_id}>"


class ActionLog(Base):
    """
    Action logging for analytics and audit.
    """
    __tablename__ = "action_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    bot_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("bots.id", ondelete="SET NULL"), nullable=True
    )

    action: Mapped[str] = mapped_column(String(100), index=True)
    details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default="now()", index=True
    )

    def __repr__(self) -> str:
        return f"<ActionLog {self.action} at {self.created_at}>"
