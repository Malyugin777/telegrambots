"""
Текстовые сообщения бота SaveNinja
"""

# Подпись под медиа
CAPTION = "@SaveNinja_bot"

# Статусы загрузки
STATUS_DOWNLOADING = "\u23f3 Скачиваю..."
STATUS_SENDING = "\U0001f4e4 Отправляю..."
STATUS_EXTRACTING_AUDIO = "\U0001f3b5 Извлекаю аудио..."

# Приветствие
START_MESSAGE = """
<b>\U0001f44b Привет! Я SaveNinja</b>

Отправь мне ссылку и я скачаю для тебя:
\u2022 \U0001f3ac <b>Видео</b> (автопроигрывание)
\u2022 \U0001f3b5 <b>Аудио MP3</b> (320 kbps)

<b>Поддерживаемые платформы:</b>

\U0001f4f8 <b>Instagram</b> \u2014 фото, видео, карусели, истории
\U0001f4cc <b>Pinterest</b> \u2014 фото и видео
\U0001f3b5 <b>TikTok</b> \u2014 видео без водяного знака
\u25b6\ufe0f <b>YouTube Shorts</b> \u2014 короткие видео

Просто отправь ссылку!
""".strip()

# Сообщение об ошибке - неподдерживаемая ссылка
UNSUPPORTED_URL_MESSAGE = """
\u26d4\ufe0f <b>Ссылка не поддерживается!</b>

<b>Что поддерживается?</b>

\U0001f4f8 <b>Instagram</b> \u2014 фото, видео, карусели, истории
\U0001f4cc <b>Pinterest</b> \u2014 фото и видео
\U0001f3b5 <b>TikTok</b> \u2014 видео без водяного знака
\u25b6\ufe0f <b>YouTube Shorts</b> \u2014 короткие видео

Отправь корректную ссылку с одной из этих платформ.
""".strip()

# Помощь
HELP_MESSAGE = """
<b>\u2753 Помощь</b>

<b>Как пользоваться:</b>
1. Скопируй ссылку на видео
2. Отправь её мне
3. Получи видео + аудио!

<b>Поддерживаемые ссылки:</b>
\u2022 <code>https://vm.tiktok.com/...</code>
\u2022 <code>https://www.instagram.com/reel/...</code>
\u2022 <code>https://www.instagram.com/p/...</code>
\u2022 <code>https://youtube.com/shorts/...</code>
\u2022 <code>https://pin.it/...</code>
\u2022 <code>https://pinterest.com/pin/...</code>

<b>Ограничения:</b>
\u2022 Максимальный размер файла: 50MB
\u2022 Приватные видео не поддерживаются
""".strip()
