"""
Обработчики команд /start и /help
"""
from aiogram import Router, types
from aiogram.filters import CommandStart, Command

from ..messages import get_start_message, get_help_message
from bot_manager.middlewares import log_action

router = Router()


@router.message(CommandStart())
async def cmd_start(message: types.Message):
    """Команда /start"""
    await log_action(message.from_user.id, "start")
    await message.answer(get_start_message())


@router.message(Command("help"))
async def cmd_help(message: types.Message):
    """Команда /help"""
    await log_action(message.from_user.id, "help")
    await message.answer(get_help_message())
