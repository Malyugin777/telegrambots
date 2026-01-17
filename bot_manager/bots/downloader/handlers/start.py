from aiogram import Router, types
from aiogram.filters import CommandStart

router = Router()


@router.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.answer(
        "<b>Привет! Я SaveNinja</b>\n\n"
        "Отправь мне ссылку на видео из:\n"
        "• TikTok\n"
        "• Instagram Reels\n"
        "• YouTube Shorts\n"
        "• Pinterest\n\n"
        "И я скачаю его для тебя без водяных знаков!"
    )
