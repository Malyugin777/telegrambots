-- Bot Messages table and initial data for SaveNinja bot
-- Run on Hostkey PostgreSQL

-- Create table
CREATE TABLE IF NOT EXISTS bot_messages (
    id SERIAL PRIMARY KEY,
    bot_id INTEGER REFERENCES bots(id) ON DELETE CASCADE,
    message_key VARCHAR(50) NOT NULL,
    text_ru TEXT NOT NULL,
    text_en TEXT,
    is_active BOOLEAN DEFAULT true,
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(bot_id, message_key)
);

-- Create index
CREATE INDEX IF NOT EXISTS idx_bot_messages_bot_id ON bot_messages(bot_id);

-- Insert initial messages for SaveNinja (bot_id = 1)
-- First check if bot exists
DO $$
DECLARE
    v_bot_id INTEGER;
BEGIN
    SELECT id INTO v_bot_id FROM bots WHERE name ILIKE '%SaveNinja%' OR name ILIKE '%downloader%' LIMIT 1;

    IF v_bot_id IS NOT NULL THEN
        INSERT INTO bot_messages (bot_id, message_key, text_ru, text_en) VALUES
        (v_bot_id, 'start',
         '🎬 Привет! Я SaveNinja — бот для скачивания видео.

Отправь мне ссылку на видео из:
• Instagram (Reels, Stories, Posts)
• TikTok
• YouTube Shorts
• Twitter/X

И я скачаю его для тебя! 🚀',
         '🎬 Hi! I''m SaveNinja — video download bot.

Send me a video link from:
• Instagram (Reels, Stories, Posts)
• TikTok
• YouTube Shorts
• Twitter/X

And I''ll download it for you! 🚀'),

        (v_bot_id, 'help',
         '📖 Как пользоваться:

1. Скопируй ссылку на видео
2. Отправь её мне
3. Получи видео!

Поддерживаемые платформы:
• Instagram — Reels, Stories, Posts
• TikTok — любые видео
• YouTube — Shorts
• Twitter/X — видео из твитов

❓ Проблемы? Напиши @support',
         '📖 How to use:

1. Copy video link
2. Send it to me
3. Get your video!

Supported platforms:
• Instagram — Reels, Stories, Posts
• TikTok — any videos
• YouTube — Shorts
• Twitter/X — videos from tweets

❓ Issues? Contact @support'),

        (v_bot_id, 'downloading', '⏳ Скачиваю видео...', '⏳ Downloading video...'),
        (v_bot_id, 'success', '✅ Готово!', '✅ Done!'),
        (v_bot_id, 'error_not_found', '❌ Видео не найдено. Проверь ссылку.', '❌ Video not found. Check the link.'),
        (v_bot_id, 'error_timeout', '⏱ Превышено время ожидания. Попробуй позже.', '⏱ Timeout. Try again later.'),
        (v_bot_id, 'error_too_large', '📦 Файл слишком большой (>50MB). Telegram не позволяет.', '📦 File too large (>50MB). Telegram limit.'),
        (v_bot_id, 'error_unknown', '❌ Произошла ошибка. Попробуй позже.', '❌ An error occurred. Try again later.'),
        (v_bot_id, 'error_invalid_url', '🔗 Неверная ссылка. Отправь ссылку на видео.', '🔗 Invalid link. Send a video URL.'),
        (v_bot_id, 'error_private', '🔒 Это приватный контент. Доступ ограничен.', '🔒 This is private content. Access denied.')
        ON CONFLICT (bot_id, message_key) DO NOTHING;

        RAISE NOTICE 'Bot messages inserted for bot_id: %', v_bot_id;
    ELSE
        RAISE NOTICE 'SaveNinja bot not found, skipping message insertion';
    END IF;
END $$;
