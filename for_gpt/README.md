# Файлы для GPT - SaveNinja Bot

## Структура

```
for_gpt/
├── CLAUDE.md              # Главный документ проекта (правила, архитектура)
├── API_COSTS.md           # Стоимость API, квоты, лимиты
├── README.md              # Этот файл
│
├── bot_handlers/
│   └── download.py        # Главный handler скачивания
│
├── bot_services/
│   ├── action_logger.py   # Middleware логирования в БД
│   ├── cache.py           # Rate limiting, Redis cache
│   ├── downloader.py      # Базовый класс downloader (yt-dlp)
│   ├── pytubefix_downloader.py  # YouTube через pytubefix
│   ├── rapidapi_downloader.py   # Instagram/fallback через RapidAPI
│   └── savenow_downloader.py    # YouTube через SaveNow CDN (NEW!)
│
├── shared/
│   └── video_fixer.py     # FFmpeg: fix_video, ensure_faststart, download_thumbnail
│
├── database/
│   └── models.py          # SQLAlchemy модели (User, Bot, ActionLog, ErrorLog)
│
└── admin_backend/
    ├── models.py          # Pydantic models для API
    ├── schemas.py         # Request/Response schemas
    ├── database.py        # DB connection
    └── api_stats.py       # Эндпоинты статистики (/stats, /chart, /performance)

└── admin_frontend/
    ├── dashboard.tsx      # Главная страница дашборда
    ├── activity_logs_list.tsx  # Список action_logs
    └── errors_list.tsx    # Список ошибок
```

## Ключевые концепции

### 1. Fallback Chain (YouTube)
```
yt-dlp → pytubefix → SaveNow (RapidAPI CDN)
```

### 2. Провайдеры по платформам
- **Instagram**: RapidAPI (primary)
- **TikTok**: yt-dlp → RapidAPI (fallback)
- **Pinterest**: yt-dlp → RapidAPI (fallback)
- **YouTube**: yt-dlp → pytubefix → SaveNow

### 3. Метрики в action_logs
- `download_time_ms` - полное время обработки
- `file_size_bytes` - размер файла
- `download_speed_kbps` - скорость
- `api_source` - провайдер (ytdlp/rapidapi/pytubefix/savenow)

### 4. Error Classification (Phase 7.0)
- `HARD_KILL` - фатальные (private video, not found)
- `STALL` - временные (rate limit, timeout)
- `PROVIDER_BUG` - баги провайдера

### 5. Duration Buckets
- `shorts` - < 5 мин
- `medium` - 5-30 мин
- `long` - > 30 мин

## Что нужно улучшить в админке

1. **Dashboard widgets:**
   - График downloads по дням
   - Breakdown по платформам (pie chart)
   - Средняя скорость по провайдерам
   - Error rate по категориям

2. **Performance monitoring:**
   - P50/P95 latency по провайдерам
   - Success rate trends
   - Duration bucket distribution

3. **API Usage:**
   - RapidAPI quota remaining
   - Daily/monthly usage
   - Cost estimation
