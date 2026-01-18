-- Добавление новых сообщений для этапов скачивания
-- SaveNinja Bot (bot_id=1)

-- Обновляем существующие
UPDATE bot_messages SET text_ru = '⏳ Скачиваю видео...' WHERE bot_id = 1 AND message_key = 'downloading';
UPDATE bot_messages SET text_ru = '📤 Отправляю...' WHERE bot_id = 1 AND message_key = 'sending';

-- Добавляем новые этапы
INSERT INTO bot_messages (bot_id, message_key, text_ru, text_en, is_active, updated_at)
VALUES
    (1, 'processing', '🎬 Обрабатываю видео...', '🎬 Processing video...', true, NOW()),
    (1, 'compressing', '📦 Сжимаю под формат Telegram...', '📦 Compressing for Telegram...', true, NOW()),
    (1, 'uploading', '📤 Отправляю...', '📤 Uploading...', true, NOW()),
    (1, 'rate_limit_user', '⏳ Подожди, у тебя уже качается видео...', '⏳ Please wait, you already have a download in progress...', true, NOW())
ON CONFLICT (bot_id, message_key) DO UPDATE
SET
    text_ru = EXCLUDED.text_ru,
    text_en = EXCLUDED.text_en,
    is_active = EXCLUDED.is_active,
    updated_at = NOW();
