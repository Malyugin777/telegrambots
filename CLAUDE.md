# NEXUS PROJECT - ПРАВИЛА

**Версия:** 1.5.0
**Последнее обновление:** 2026-01-19

## Цель продукта

SaveNinja Bot (@SaveNinja_bot) - Telegram бот для скачивания медиа из социальных сетей.

**Поддерживаемые платформы:** Instagram, TikTok, YouTube (Shorts + Full), Pinterest
**Ограничения:** Telegram лимит 50MB для видео, 2GB для документов (Local Bot API Server)
**Фокус:** Максимальное качество, правильный aspect ratio, превью как у конкурентов

## Пайплайн обработки видео

```
URL от пользователя
       │
       ▼
┌──────────────────┐
│ Определение      │
│ платформы        │
└────────┬─────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────┐
│                    ПРОВАЙДЕРЫ                            │
├──────────────────────────────────────────────────────────┤
│ Instagram    → RapidAPI (primary)                        │
│ YouTube <5m  → pytubefix → RapidAPI (fallback)           │
│ YouTube ≥5m  → pytubefix (720p adaptive)                 │
│ TikTok       → yt-dlp → RapidAPI (fallback)              │
│ Pinterest    → yt-dlp → RapidAPI (fallback)              │
└────────┬─────────────────────────────────────────────────┘
         │
         ▼
┌──────────────────┐
│ Скачивание       │
│ video + audio    │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐     ┌─────────────────────────────────┐
│ Merge/Remux      │────►│ pytubefix: ffmpeg -c copy       │
│ (если adaptive)  │     │ + h264_metadata SAR=1:1         │
└────────┬─────────┘     │ + movflags +faststart           │
         │               └─────────────────────────────────┘
         ▼
┌──────────────────┐     ┌─────────────────────────────────┐
│ fix_video()      │────►│ SAR != 1:1 → scale + re-encode  │
│                  │     │ codec != h264 → re-encode       │
└────────┬─────────┘     │ SAR=1:1 + h264 → SKIP           │
         │               └─────────────────────────────────┘
         ▼
┌──────────────────┐     ┌─────────────────────────────────┐
│ ensure_faststart │────►│ ffmpeg -c copy -movflags        │
│ (RapidAPI only)  │     │ +faststart -fflags +genpts      │
└────────┬─────────┘     └─────────────────────────────────┘
         │
         ▼
┌──────────────────┐     ┌─────────────────────────────────┐
│ download_thumb   │────►│ urllib + ffmpeg scale 320px     │
│ (YouTube)        │     │ JPEG quality 5                  │
└────────┬─────────┘     └─────────────────────────────────┘
         │
         ▼
┌──────────────────┐     ┌─────────────────────────────────┐
│ sendVideo        │────►│ duration, width, height         │
│                  │     │ thumbnail, supports_streaming   │
└────────┬─────────┘     └─────────────────────────────────┘
         │
         ▼
┌──────────────────┐
│ Cleanup          │
│ video + thumb    │
└──────────────────┘
```

## Провайдеры

| Провайдер | Платформы | Когда используется | Типичные ошибки | Fallback |
|-----------|-----------|-------------------|-----------------|----------|
| **pytubefix** | YouTube | Primary для всех YouTube | HTTP 500, throttling | RapidAPI (Shorts) |
| **RapidAPI** | Instagram, YouTube Full | Primary для IG, fallback для YT | Rate limits, slow download | Нет |
| **yt-dlp** | TikTok, Pinterest | Primary | Login required (IG), geo-blocks | RapidAPI |

### pytubefix
- **Когда:** YouTube Shorts (<5 мин), YouTube Full (≥5 мин)
- **Качество:** 720p fixed (adaptive streams + merge)
- **Ошибки:** HTTP 500 от YouTube, cipher issues
- **При ошибке:** Для Shorts → RapidAPI fallback, для Full → показываем ошибку

### RapidAPI (Social Download All In One)
- **Когда:** Instagram always, YouTube fallback, TikTok/Pinterest fallback
- **Лимиты:** ~500 req/day (бесплатный план)
- **Качество:** Адаптивное (720p <60 мин, 480p >60 мин)
- **Время скачки:** 1-15 мин для длинных видео (68 мин ≈ 10 мин download)

### yt-dlp
- **Когда:** TikTok, Pinterest (primary)
- **Особенности:** Chrome impersonate для TikTok, H.264 preferred
- **При ошибке:** RapidAPI fallback

## Telegram отправка

### sendVideo vs sendDocument
| Размер | Метод | Причина |
|--------|-------|---------|
| ≤50MB | `sendVideo` | Превью, автоплей, duration в UI |
| >50MB, ≤2GB | `sendDocument` | Только для YouTube Full |

### Параметры sendVideo
```python
await message.answer_video(
    video=media_file,
    thumbnail=thumb_file,        # FSInputFile ~320px JPEG
    duration=duration,           # int секунды (из ffprobe)
    width=width,                 # int пиксели
    height=height,               # int пиксели
    supports_streaming=True,     # КРИТИЧНО для автоплея
    caption=CAPTION,
)
```

**Важно:** `duration` передаётся ЯВНО - не зависит от moov atom в файле.

### Local Bot API Server
- **URL:** `http://telegram_bot_api:8081`
- **Лимит:** 2GB (вместо 50MB стандартного API)
- **Файлы:** `/tmp/downloads/` (внутри контейнера)
- **Таймауты:** 30 мин для документов, 15 мин для видео

## FFmpeg политика

### Используемые команды

**1. Merge (pytubefix adaptive streams):**
```bash
ffmpeg -y -i video.mp4 -i audio.m4a \
  -map 0:v:0 -map 1:a:0 \
  -c copy \
  -bsf:v h264_metadata=sample_aspect_ratio=1/1 \
  -movflags +faststart \
  -shortest output.mp4
```

**2. ensure_faststart (RapidAPI videos):**
```bash
ffmpeg -y -fflags +genpts -i input.mp4 \
  -map 0 -c copy \
  -movflags +faststart \
  output.mp4
```

**3. fix_video (SAR correction):**
```bash
# Если SAR != 1:1
ffmpeg -i input.mp4 \
  -vf "scale=NEW_W:NEW_H,setsar=1:1" \
  -c:v libx264 -preset fast -crf 20 \
  -c:a aac -b:a 128k \
  -movflags +faststart \
  output.mp4
```

**4. download_thumbnail:**
```bash
ffmpeg -y -i thumb.jpg \
  -vf "scale='min(320,iw)':-2" \
  -q:v 5 \
  thumb_resized.jpg
```

### Что НЕ делаем
- ❌ Crop (обрезка) - теряем контент
- ❌ Blur-fill для 4:3 - слишком тяжело
- ❌ Forced aspect ratio (`-aspect 16:9`) - растягивает 4:3
- ❌ Re-encode без необходимости - теряем качество

## Хранилище и очистка

| Что | Путь | TTL |
|-----|------|-----|
| Видео | `/tmp/downloads/*.mp4` | Удаляется после отправки |
| Thumbnail | `/tmp/downloads/thumb_*.jpg` | Удаляется после отправки |
| Redis cache | `file_id:{url_hash}` | 24 часа |

**Очистка:** Файлы удаляются в `finally` блоке handler'а.

## Метрики и логирование

### Что измеряем
- `download_time_ms` - время от запроса до отправки
- `file_size_bytes` - размер файла
- `download_speed_kbps` - скорость скачивания
- `api_source` - какой провайдер использовался (ytdlp/rapidapi/pytubefix)

### Логи
```
[PYTUBEFIX] Starting download: URL, quality=720p
[PYTUBEFIX] Video info: title, author, duration
[PYTUBEFIX] Detected codec: h264
[FIX_VIDEO] SKIP - already OK: 1280x720, codec=h264, sar=1:1
[FASTSTART] SUCCESS: path, size=204857344
[THUMBNAIL] SUCCESS: path, size=15234
```

## Открытые проблемы/риски

| Проблема | Причина | Митигация |
|----------|---------|-----------|
| YouTube HTTP 500 | YouTube throttling/blocks | RapidAPI fallback для Shorts |
| Долгое скачивание >60 мин видео | RapidAPI медленный | Progress updates каждые 60 сек |
| Instagram login required | yt-dlp блокируется | RapidAPI primary для IG |
| 4:3 видео выглядит "уже" | Не растягиваем | Это правильное поведение |

---

## КРИТИЧЕСКИ ВАЖНО

1. **ДВА СЕРВЕРА - НЕ ПУТАТЬ!**
   - Hostkey (66.151.33.167) = ТОЛЬКО боты + PostgreSQL + Redis
   - Aeza (185.96.80.254) = ТОЛЬКО админка (API + Frontend)

2. **НЕ ДЕПЛОИТЬ АДМИНКУ НА HOSTKEY!**
3. **НЕ ДЕПЛОИТЬ БОТОВ НА AEZA!**

## Архитектура

```
HOSTKEY VPS (66.151.33.167)          AEZA (185.96.80.254)
├── PostgreSQL :5432                  ├── API (FastAPI) :8000
├── Redis :6379                       ├── Frontend (React)
└── bot_manager                       └── Nginx + SSL
    └── bots/
        └── downloader/               Домены:
                                      - shadow-api.ru
Бот: @SaveNinja_bot                   - api.shadow-api.ru
```

## Деплой

### Боты (Hostkey):
```bash
cd C:\Projects\TelegramBots
git add -A && git commit -m "msg" && git push
# GitHub Actions деплоит на 66.151.33.167
```

### Админка (Aeza):

**Frontend** (статика):
```bash
cd admin_panel/frontend
npm run build
scp -r dist/* root@185.96.80.254:/var/www/shadow-api/
```

**Backend** (Docker):
```bash
ssh root@185.96.80.254 "cd /root/admin_panel && docker compose up -d --build"
```

## Credentials

| Что | Значение |
|-----|----------|
| PostgreSQL | nexus / nexus_secure_pwd_2024 @ 66.151.33.167:5432 |
| Redis | redis://66.151.33.167:6379 |
| Админка | admin / Admin123 |
| SSH Hostkey | root / mcMdC3d+2b @ 66.151.33.167 |
| SSH Aeza | root / mcMdC3d+2b @ 185.96.80.254 |

## API Keys

```env
# RapidAPI (Social Download All In One) - для Instagram
RAPIDAPI_KEY=3a98632be0msh6686aaf9450a750p1cf661jsn3100d744f778
RAPIDAPI_HOST=social-download-all-in-one.p.rapidapi.com
```

## Частые команды

```bash
# Логи ботов
ssh root@66.151.33.167 "docker logs nexus_bot_manager --tail 50"

# Логи админки API
ssh root@185.96.80.254 "docker logs admin_api --tail 50"

# Перезапуск ботов
ssh root@66.151.33.167 "cd /root/telegrambots/infrastructure && docker compose restart bot_manager"

# Пересборка ботов
ssh root@66.151.33.167 "cd /root/telegrambots && git pull && cd infrastructure && docker compose up -d --build bot_manager"
```

## НЕ ДЕЛАТЬ

### ДЕПЛОЙ — ТОЛЬКО GIT PUSH!

❌ **ЗАПРЕЩЕНО:**
- ssh для деплоя кода
- scp для копирования файлов на сервер
- docker compose up через ssh для обновления

✅ **РАЗРЕШЕНО:**
- **git push** — GitHub Actions сам деплоит
- **ssh ТОЛЬКО для:** миграции БД, просмотр логов, экстренный рестарт

---

## Приложение: Реальные кейсы

### Кейс 1: YouTube Shorts (успех)
```
URL: https://youtube.com/shorts/abc123
Провайдер: pytubefix
Результат: ✅ 720p, 45MB, duration=58s, thumb=OK
Время: 12 сек
```

### Кейс 2: YouTube Full с fallback
```
URL: https://youtube.com/watch?v=xyz789 (68 мин)
Провайдер: pytubefix → HTTP 500 → RapidAPI fallback
Результат: ✅ 480p, 204MB, duration=4115s, thumb=OK
Время: 11 мин (slow RapidAPI download)
```

### Кейс 3: Instagram карусель
```
URL: https://instagram.com/p/abc123
Провайдер: RapidAPI
Результат: ✅ 5 фото + 2 видео, MediaGroup
Время: 8 сек
```

### Кейс 4: TikTok без водяного знака
```
URL: https://vm.tiktok.com/xyz
Провайдер: yt-dlp (Chrome impersonate)
Результат: ✅ 1080x1920, 15MB, no watermark
Время: 5 сек
```

## Приложение: Примеры логов

### Успешное скачивание YouTube
```
2026-01-19 12:00:00 - [PYTUBEFIX] Starting download: https://youtube.com/watch?v=abc, quality=720p
2026-01-19 12:00:01 - [PYTUBEFIX] Video info: title='Test Video', author='Channel', duration=120s, thumb=https://i.ytimg.com/...
2026-01-19 12:00:01 - [PYTUBEFIX] Using adaptive streams: video=720p, audio=128kbps
2026-01-19 12:00:15 - [PYTUBEFIX] Merging video+audio (stream copy, no re-encode)
2026-01-19 12:00:15 - [PYTUBEFIX] Detected codec: h264
2026-01-19 12:00:16 - [PYTUBEFIX] Merge success (instant)
2026-01-19 12:00:16 - [FIX_VIDEO] SKIP - already OK: 1280x720, codec=h264, sar=1:1
2026-01-19 12:00:16 - [THUMBNAIL] Downloading: https://i.ytimg.com/vi/abc/maxresdefault.jpg
2026-01-19 12:00:17 - [THUMBNAIL] SUCCESS: /tmp/downloads/thumb_abc123.jpg, size=15234
2026-01-19 12:00:20 - Sent video: user=123456, size=45000000, time=20000ms
```

### RapidAPI fallback
```
2026-01-19 12:00:00 - [PYTUBEFIX] Starting download: https://youtube.com/watch?v=xyz
2026-01-19 12:00:05 - [PYTUBEFIX] Download error: HTTP Error 500
2026-01-19 12:00:05 - Trying RapidAPI fallback for: https://youtube.com/watch?v=xyz
2026-01-19 12:00:06 - [RAPIDAPI] Available qualities: ['360p', '480p', '720p']
2026-01-19 12:00:06 - [ADAPTIVE] duration=4115s -> desired=480p, selected=480p
2026-01-19 12:10:00 - [FIX_VIDEO] SKIP - already OK
2026-01-19 12:10:00 - [FASTSTART] SUCCESS: /tmp/downloads/xyz.mp4, size=204857344
```

### Ошибка (private video)
```
2026-01-19 12:00:00 - [PYTUBEFIX] Starting download: https://youtube.com/watch?v=private
2026-01-19 12:00:02 - [PYTUBEFIX] Download error: Video is private
2026-01-19 12:00:02 - Download failed: user=123456, error=🔒 Это приватное видео
```
