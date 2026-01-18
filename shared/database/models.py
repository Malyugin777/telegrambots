from datetime import datetime
from enum import Enum as PyEnum
from sqlalchemy import (
    Column, Integer, BigInteger, String, DateTime,
    Boolean, Text, Enum, ForeignKey, Index, JSON
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func

Base = declarative_base()


class UserRole(str, PyEnum):
    USER = "user"
    ADMIN = "admin"
    OWNER = "owner"


class BotStatus(str, PyEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    MAINTENANCE = "maintenance"


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
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    bot_users = relationship("BotUser", back_populates="bot")
    action_logs = relationship("ActionLog", back_populates="bot")


class BotUser(Base):
    __tablename__ = "bot_users"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    bot_id = Column(Integer, ForeignKey("bots.id", ondelete="CASCADE"), nullable=False)
    joined_at = Column(DateTime, server_default=func.now())
    is_active = Column(Boolean, default=True)

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

    user = relationship("User", back_populates="action_logs")
    bot = relationship("Bot", back_populates="action_logs")


class AdminUser(Base):
    __tablename__ = "admin_users"

    id = Column(Integer, primary_key=True)
    username = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    last_login = Column(DateTime, nullable=True)
