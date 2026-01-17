"""
Обработчики команд /start и /help
"""
from aiogram import Router, types
from aiogram.filters import CommandStart, Command

from ..messages import START_MESSAGE, HELP_MESSAGE

router = Router()


@router.message(CommandStart())
async def cmd_start(message: types.Message):
    """Команда /start"""
    await message.answer(START_MESSAGE)


@router.message(Command("help"))
async def cmd_help(message: types.Message):
    """Команда /help"""
    await message.answer(HELP_MESSAGE)
