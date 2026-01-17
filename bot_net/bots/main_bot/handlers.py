"""
Main bot handlers.
"""
from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message

from bot_net.core.database import User

router = Router(name="main_bot")


@router.message(CommandStart())
async def cmd_start(message: Message, user: User) -> None:
    """Handle /start command."""
    await message.answer(
        f"Hello, {user.first_name or 'friend'}!\n\n"
        f"Welcome to the bot network.\n"
        f"Your ID: <code>{user.telegram_id}</code>",
        parse_mode="HTML",
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Handle /help command."""
    await message.answer(
        "<b>Available commands:</b>\n\n"
        "/start - Start the bot\n"
        "/help - Show this message\n"
        "/me - Show your profile\n"
        "/stats - Bot statistics",
        parse_mode="HTML",
    )


@router.message(Command("me"))
async def cmd_me(message: Message, user: User) -> None:
    """Handle /me command - show user profile."""
    await message.answer(
        f"<b>Your profile:</b>\n\n"
        f"ID: <code>{user.telegram_id}</code>\n"
        f"Username: @{user.username or 'not set'}\n"
        f"Name: {user.first_name or ''} {user.last_name or ''}\n"
        f"Role: {user.role.value}\n"
        f"Registered: {user.created_at.strftime('%Y-%m-%d %H:%M')}",
        parse_mode="HTML",
    )


@router.message(Command("stats"))
async def cmd_stats(message: Message, session) -> None:
    """Handle /stats command - show bot statistics."""
    from sqlalchemy import func, select
    from bot_net.core.database import User

    result = await session.execute(select(func.count(User.id)))
    total_users = result.scalar()

    await message.answer(
        f"<b>Bot Statistics:</b>\n\n"
        f"Total users: {total_users}",
        parse_mode="HTML",
    )
