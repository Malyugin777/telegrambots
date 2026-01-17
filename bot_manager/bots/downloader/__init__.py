from aiogram import Router
from .handlers import start, download

router = Router(name="downloader")
router.include_router(start.router)
router.include_router(download.router)
