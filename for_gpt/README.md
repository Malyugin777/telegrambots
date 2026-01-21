# Тексты проекта SaveNinja для GPT-ревью

## Структура папки

```
for_gpt/
├── README.md           # Этот файл
├── bot_texts.json      # Тексты Telegram бота (28 записей)
└── admin_texts.json    # Тексты админ-панели (82 записи)
```

## Формат записей

Каждая запись содержит:

```json
{
  "key": "error_timeout",
  "lang": "ru",
  "text": "⏱ Превышено время ожидания. Попробуй позже.",
  "where_used": ["bot_manager/bots/downloader/messages.py:82"],
  "category": "error|status|info|cta|admin_ui",
  "placeholders": ["{seconds}"],
  "notes": "Таймаут при скачивании"
}
```

### Поля

| Поле | Описание |
|------|----------|
| `key` | Уникальный ключ сообщения |
| `lang` | Язык (сейчас только `ru`) |
| `text` | Текст сообщения |
| `where_used` | Массив файлов и строк где используется |
| `category` | Категория: `error`, `status`, `info`, `cta`, `admin_ui` |
| `placeholders` | Массив плейсхолдеров типа `{minutes}` |
| `notes` | Контекст: когда показывается |

## Категории

### Bot (bot_texts.json)

| Категория | Примеры | Когда |
|-----------|---------|-------|
| `status` | downloading, uploading, processing | Во время операции |
| `error` | error_timeout, error_private | При ошибках |
| `info` | start, help, caption | Общая информация |

### Admin (admin_texts.json)

| Категория | Примеры | Где |
|-----------|---------|-----|
| `admin_ui` | Все тексты | Ops Dashboard, таблицы, KPI |

## Контекст использования

### Бот (@SaveNinja_bot)

Telegram бот для скачивания медиа из:
- Instagram (посты, reels, stories, карусели)
- TikTok (без водяного знака)
- YouTube Shorts
- Pinterest

Пользователи отправляют ссылку → бот скачивает → отправляет медиа.

### Админ-панель (shadow-api.ru)

Дашборд для мониторинга:
- Статистика по платформам и провайдерам
- Управление routing (порядок провайдеров)
- Квоты API
- Системные метрики

## Требования к переводу/ревью

1. **Единый стиль** - обращение на "ты", дружелюбный тон
2. **Эмодзи** - сохранить существующие
3. **Placeholders** - НЕ менять `{minutes}`, `{count}` и т.д.
4. **HTML теги** - НЕ менять `<b>`, `<code>` в bot текстах
5. **Краткость** - Telegram ограничивает длину сообщений

## Статистика

- **bot_texts.json**: 28 записей
  - status: 9
  - error: 15
  - info: 4

- **admin_texts.json**: 82 записи
  - admin_ui: 82

## Файлы-источники

### Бот
- `bot_manager/bots/downloader/messages.py` - основные сообщения
- `bot_manager/bots/downloader/handlers/download.py` - inline тексты

### Админка
- `admin_panel/frontend/src/pages/ops/index.tsx` - Ops Dashboard
