# NEXUS ROADMAP

## Текущий статус: Фаза 7 В РАБОТЕ 🔥

**Версия:** 1.3.0
**Последнее обновление:** 2026-01-20

### Выполнено:
- [x] Исправлен график активности (включает сегодня)
- [x] Исправлен подсчёт юзеров бота
- [x] Исправлен парсинг details в логах
- [x] Статистика по платформам (Pie chart)
- [x] Drag & Drop загрузка изображений
- [x] Профиль пользователя с активностью
- [x] Версия в футере
- [x] Исправлен aspect ratio видео (SAR fix)
- [x] **JSON парсинг ffprobe (критический баг)** — v1.2.1
- [x] **Billing Tracker (Фаза 3)** — управление подписками
- [x] **Bot Messages Editor (Фаза 5)** — редактирование текстов бота
- [x] **Performance Monitor (Фаза 6)** — метрики производительности
- [x] **YouTube полные видео** — sendVideo до 2GB (Local Bot API)
- [x] **Pinterest pin.it** — поддержка коротких ссылок
- [x] **YouTube 3-step fallback** — yt-dlp → pytubefix → RapidAPI
- [x] **A+ remux** — stream copy с SAR metadata fix

### В работе (Фаза 7):
- [ ] Research альтернативных API (SaveNow, Cobalt)
- [ ] Ops Dashboard для мониторинга провайдеров
- [ ] Error classification (HARD-KILL vs STALL)
- [ ] Cooldown система для failed провайдеров
- [ ] Budget guardrails для платных API
- [ ] Routing UI в админке

---

## ФАЗА 3: Исправление видео + Счётчик ошибок

### 3.1 Видео Aspect Ratio ✅ ЗАВЕРШЕНО
- [x] Проверка SAR через ffprobe (JSON формат)
- [x] Если SAR=1:1 и H.264 — пропускаем
- [x] Если кодек не H.264 — перекодируем в H.264
- [x] Если SAR≠1:1 — scale с явным расчётом пикселей
- [x] Исправлено в rapidapi_downloader.py и downloader.py
- [x] Детальное логирование [FIX_VIDEO] / [FIX_TIKTOK]

### 3.2 Страница ошибок /errors ✅ ЗАВЕРШЕНО
- [x] Таблица ошибок с фильтрами
- [x] Статистика: всего, сегодня, по платформам
- [x] Используется ActionLog с action='error'

---

## ФАЗА 4: Billing Tracker (Трекер оплат) ✅ ЗАВЕРШЕНО

### Таблица `subscriptions`:
```sql
CREATE TABLE subscriptions (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100),           -- "Aeza VPS", "RapidAPI", "Hostkey"
    provider_url VARCHAR(255),    -- Ссылка на ЛК
    amount DECIMAL(10,2),
    currency VARCHAR(3),          -- RUB, USD
    billing_cycle VARCHAR(20),    -- monthly, yearly
    next_payment_date DATE,
    auto_renew BOOLEAN,
    notes TEXT,
    created_at TIMESTAMP
);
```

### Функционал:
- [x] CRUD подписок через админку
- [x] Страница /subscriptions в меню
- [x] Dashboard виджет "Ближайшие платежи"
- [x] История платежей

---

## ФАЗА 5: Bot Customization (Настройка бота) ✅ ЗАВЕРШЕНО

### 5.1 Редактор сообщений
```
Таблица bot_messages:
- id
- bot_id
- message_key (start, help, download_success, error, etc.)
- text_ru
- text_en
- is_active
- updated_at
```

### Функционал:
- [x] Страница /bot-messages в админке
- [x] Редактор текстов с сохранением в БД
- [x] Авто-обновление кэша бота (60s TTL)
- [x] Поддержка русского и английского языков
- [x] Эмодзи в сообщениях

---

## ФАЗА 6: Performance Monitor ✅ ЗАВЕРШЕНО

### 6.1 Метрики скачивания
```python
# В ActionLog добавлены поля:
- download_time_ms: int      # Время скачивания
- file_size_bytes: bigint    # Размер файла
- download_speed_kbps: int   # Скорость KB/s
```

### 6.2 Dashboard виджеты:
- [x] Средняя скорость скачивания
- [x] Средний размер файла
- [x] Среднее время скачивания
- [x] API endpoint GET /api/v1/stats/performance
- [x] Метрики по платформам (Instagram, TikTok, YouTube, Pinterest)

---

## ФАЗА 7: YouTube Provider Routing System 🔥 ТЕКУЩИЙ ПРИОРИТЕТ

**Проблема:** YouTube банит/тротлит IP сервера. yt-dlp, pytubefix и RapidAPI (который возвращает googlevideo.com URL) все ломаются на длинных видео. Конкуренты качают 8-часовые видео за секунды.

**SLA:** 2-5 минут макс или показать ошибку. 8+ минут недопустимо.

**Ключевая политика:**
```python
MAX_USER_WAIT_SEC = 180  # 3 минуты — после этого либо background queue, либо отказ
```

---

### 7.0 Telemetry Baseline (Phase 0) ✅ ЧАСТИЧНО

**Цель:** Собрать данные для принятия решений, "соединить Клода с реальностью".

**Уже реализовано:**
- [x] `download_host` logging в RapidAPI (googlevideo.com = плохо)
- [x] `download_time_ms`, `file_size_bytes`, `download_speed_kbps` в ActionLog

**Нужно добавить:**
- [ ] `redirect_chain` — если API редиректит на googlevideo
- [ ] `ttfb_ms` (time to first byte) — показывает latency провайдера
- [ ] `error_type` в ActionLog (HARD_KILL / STALL / PROVIDER_BUG)
- [ ] `duration_bucket` (shorts/medium/long) для аналитики

---

### 7.1 Research APIs (Phase 1) ✅ ИССЛЕДОВАНО

**Задача:** Найти API которые РЕАЛЬНО проксируют контент через свой CDN, а не возвращают googlevideo.com URLs.

| API | CDN | Цена | Downloads/мес | Статус |
|-----|-----|------|---------------|--------|
| **RapidAPI (YouTube Info & Download API)** | ✅ `*.savenow.to` | $5/мес Pro | ~16K-33K | 🏆 **РЕКОМЕНДУЕТСЯ** |
| **youtube-download-api.org** | ✅ `media.yt-data-proxy.org` | $199/мес | без лимитов? | 💰 Backup (дорого) |
| **video-download-api.com** | ✅ тот же backend | ~$0.00030/download | pay-per-use | 🔄 Альтернатива |
| **RapidAPI (Social Download All In One)** | ❌ googlevideo.com | ~$0.004/download | — | ❌ Бан IP |
| **Cobalt.tools** | ❌ Забанен YouTube | — | — | ❌ Нестабилен |

**Важно про SaveNow.to:** Сайт показывает рекламу, но через RapidAPI wrapper получаем прямые CDN ссылки без рекламы. API убирает рекламный слой.

**Результаты тестирования (2026-01-20):**

### 🏆 RapidAPI "YouTube Info & Download API" — ПРОТЕСТИРОВАНО, РАБОТАЕТ!

**Ключевые данные:**
- **Host:** `youtube-info-download-api.p.rapidapi.com`
- **Backend:** SaveNow.to (wrapper API, без рекламы)
- **CDN:** ✅ `*.savenow.to` (rose44, pamela88, etc.) — **НЕ googlevideo.com!**
- **Наш IP не банится YouTube!**

**Тесты:**

| Видео | Длина | Prep time | Размер | Cost | CDN Host |
|-------|-------|-----------|--------|------|----------|
| Rick Astley | 3:33 | ~5 сек | 30 MB | $0.0003 | `rose44.savenow.to` |
| C# Tutorial | 4:31:09 | ~50 сек | 432 MB | $0.0015 | `pamela88.savenow.to` |
| Harvard CS50 | 24+ часа | — | — | — | ❌ "Video too long" |

**Лимиты:**
- Pro Plan: **$5/мес** = 100,000 units
- 720p/1080p = ~6 units = **~16,000 downloads/мес**
- Extended duration: x3 (90 min over), x5 (180 min over), x33 (24h)
- Overage: $0.000047/unit
- Max video: **~4-5 часов** (24h не работает)

**Скорость скачивания:** ~1.4 MB/s (с локальной машины)

**API Flow:**
```
1. POST /ajax/download.php → получаем job ID + progress_url
2. Poll progress_url каждые 5 сек
3. Когда success=1 → download_url готов
4. download_url = их CDN (*.savenow.to), не googlevideo!
```

**Пример запроса:**
```bash
curl "https://youtube-info-download-api.p.rapidapi.com/ajax/download.php?format=720&url=VIDEO_URL&allow_extended_duration=1" \
  -H "x-rapidapi-host: youtube-info-download-api.p.rapidapi.com" \
  -H "x-rapidapi-key: YOUR_KEY"
```

### ✅ youtube-download-api.org — CDN ПОДТВЕРЖДЁН, НО ДОРОГО
- Возвращает URL их CDN: `https://media.yt-data-proxy.org/...`
- НЕ googlevideo.com → наш IP не банится
- <2 сек на получение ссылки
- $199/мес flat rate — **backup если $5 API перестанет работать**

### ✅ video-download-api.com — ТОТ ЖЕ BACKEND
- Тот же автор что и RapidAPI wrapper (sp_golubev@protonmail.com)
- Pay-per-use ~$0.00030/download
- Альтернатива если RapidAPI недоступен

**Следующие шаги:**
1. [x] ~~Тест CDN~~ → **CDN подтверждён!**
2. [x] Интеграция в бота → `savenow_downloader.py` создан!
3. [x] Quota monitoring → headers `x-ratelimit-*` логируются
4. [ ] A/B тест: pytubefix vs savenow для длинных видео
5. [ ] Мониторинг costs в админке

---

### 7.2 Routing Engine Backend (Phase 2)

**Архитектура провайдеров:**

```python
# Таблица download_providers
CREATE TABLE download_providers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50),           -- "yt-dlp", "pytubefix", "rapidapi", "savenow", "cobalt"
    provider_type VARCHAR(20),  -- "local", "api", "egress_pool"
    is_active BOOLEAN,
    priority INT,               -- 1 = highest

    -- Для API провайдеров
    api_key VARCHAR(255),
    api_host VARCHAR(255),
    rate_limit_per_min INT,

    -- Health tracking
    health_status VARCHAR(20),  -- "healthy", "degraded", "down"
    last_success_at TIMESTAMP,
    last_error_at TIMESTAMP,
    error_count_1h INT,
    success_rate_24h DECIMAL,
    avg_speed_kbps INT,

    -- Cooldown
    cooldown_until TIMESTAMP,   -- NULL = active, datetime = disabled until

    -- Budget (для платных API)
    daily_budget_usd DECIMAL,
    daily_spent_usd DECIMAL,
    budget_reset_at TIMESTAMP,

    created_at TIMESTAMP
);

# Таблица routing_rules
CREATE TABLE routing_rules (
    id SERIAL PRIMARY KEY,
    platform VARCHAR(20),       -- "youtube", "youtube_shorts", "tiktok", etc
    duration_min INT,           -- NULL = any, 0 = shorts, 300 = >5min
    duration_max INT,           -- NULL = any
    file_size_max_mb INT,

    provider_chain JSONB,       -- ["yt-dlp", "pytubefix", "rapidapi", "savenow"]

    is_active BOOLEAN,
    priority INT,
    created_at TIMESTAMP
);
```

**Error Classification:**
```python
# HARD-KILL errors (мгновенный fallback + cooldown 15-60 мин)
HARD_KILL_ERRORS = [
    "SSL: UNEXPECTED_EOF",      # YouTube ban
    "HTTP 403 Forbidden",       # IP blocked
    "HTTP 429 Too Many",        # Rate limited
    "Sign in to confirm",       # Age/auth required
]

# STALL errors (retry once, then fallback)
STALL_ERRORS = [
    "Download stalled",         # No progress >30 sec
    "Connection timeout",       # Network issue
    "Incomplete read",          # Partial download
]
```

**Cooldown Logic (per provider:platform:bucket):**
```python
# Cooldown key = {provider}:{platform}:{bucket}
# Пример: "yt-dlp:youtube:long" — yt-dlp дохнет на длинных, но работает на shorts
# bucket = "shorts" (<5 min) | "medium" (5-30 min) | "long" (>30 min)

async def on_provider_error(provider: str, platform: str, duration_sec: int, error_type: str):
    bucket = get_duration_bucket(duration_sec)  # shorts/medium/long
    cooldown_key = f"{provider}:{platform}:{bucket}"

    if error_type == "HARD_KILL":
        # Мгновенно отключаем на 30 мин (только для этого bucket!)
        await set_cooldown(cooldown_key, minutes=30)
    elif error_type == "STALL":
        # Увеличиваем cooldown экспоненциально
        current = await get_error_count_1h(cooldown_key)
        if current >= 3:
            await set_cooldown(cooldown_key, minutes=15)

def get_duration_bucket(duration_sec: int) -> str:
    if duration_sec < 300: return "shorts"      # <5 min
    if duration_sec < 1800: return "medium"     # 5-30 min
    return "long"                                # >30 min
```

**Budget Guardrails (платные API):**
```python
async def check_budget(provider_id: str) -> bool:
    provider = await get_provider(provider_id)
    if provider.daily_spent_usd >= provider.daily_budget_usd:
        logger.warning(f"[ROUTING] {provider.name} budget exceeded, skipping")
        return False
    return True

async def track_api_cost(provider_id: str, cost_usd: float):
    await increment_daily_spent(provider_id, cost_usd)
```

**Egress Pool (multi-IP):**
```python
# Провайдер типа "egress_pool" для multi-IP скачивания
# Пример: несколько VPS или прокси для yt-dlp
class EgressPoolProvider:
    def __init__(self, endpoints: list[str]):
        # ["vps1.example.com", "vps2.example.com", ...]
        self.endpoints = endpoints
        self.current_index = 0

    async def download(self, url: str) -> DownloadResult:
        # Round-robin или выбор по здоровью
        endpoint = self.get_healthy_endpoint()
        return await self.download_via_endpoint(endpoint, url)
```

**Concurrency Manager (платформо-специфичный):**
```python
# Redis-based concurrency limits
# ВАЖНО: YouTube банит быстрее при параллельных запросах!
CONCURRENCY_LIMITS = {
    # YouTube — агрессивный IP бан, держим низко
    "youtube:yt-dlp": 2,        # Max 2 concurrent yt-dlp YouTube
    "youtube:pytubefix": 2,     # Max 2 concurrent pytubefix
    "youtube:rapidapi": 3,      # RapidAPI чуть больше (их IP)

    # Другие платформы — более лояльные
    "instagram:rapidapi": 5,    # Instagram через RapidAPI
    "tiktok:yt-dlp": 5,         # TikTok более лоялен
    "pinterest:yt-dlp": 5,      # Pinterest тоже

    # Общие лимиты
    "telegram_upload": 10,      # Max 10 concurrent uploads
    "ffmpeg_process": 3,        # Max 3 concurrent ffmpeg
}

async def acquire_slot(category: str, timeout: int = 60) -> bool:
    key = f"concurrency:{category}"
    current = await redis.incr(key)
    if current > CONCURRENCY_LIMITS.get(category, 10):
        await redis.decr(key)
        return False
    await redis.expire(key, timeout)
    return True
```

---

### 7.3 Admin Panel UI (Phase 3)

**Порядок реализации (начинаем с Ops Dashboard):**

#### 7.3.1 Ops Dashboard (ПЕРВЫЙ ПРИОРИТЕТ)
```
┌─────────────────────────────────────────────────────────────┐
│ 🎛️ Operations Dashboard                                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ ┌─── Provider Health ───────────────────────────────────┐  │
│ │ yt-dlp      🟢 Healthy   Speed: 5.2 MB/s   Err: 2%    │  │
│ │ pytubefix   🟡 Degraded  Speed: 3.1 MB/s   Err: 15%   │  │
│ │ RapidAPI    🔴 Down      Cooldown: 28 min  Err: 89%   │  │
│ │ SaveNow     🟢 Healthy   Speed: 8.4 MB/s   Err: 1%    │  │
│ └───────────────────────────────────────────────────────┘  │
│                                                             │
│ ┌─── Real-time Metrics ─────────────────────────────────┐  │
│ │ Downloads/hour: 847     Success rate: 94%             │  │
│ │ Avg speed: 4.8 MB/s     Avg time: 12.3s               │  │
│ │ YouTube errors: 23      Budget used: $4.20/$10        │  │
│ └───────────────────────────────────────────────────────┘  │
│                                                             │
│ ┌─── Active Cooldowns ──────────────────────────────────┐  │
│ │ RapidAPI: SSL_EOF (28 min left)                       │  │
│ │ yt-dlp:youtube_long: STALL (12 min left)             │  │
│ └───────────────────────────────────────────────────────┘  │
│                                                             │
│ ┌─── Recent Errors ─────────────────────────────────────┐  │
│ │ 14:23  YouTube  RapidAPI  SSL_UNEXPECTED_EOF          │  │
│ │ 14:21  YouTube  yt-dlp    Download stalled            │  │
│ │ 14:18  TikTok   yt-dlp    Rate limited                │  │
│ └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

#### 7.3.2 Alerts System
```python
# Алерты отправляются в Telegram админу
ALERT_RULES = {
    "provider_down": {
        "condition": "error_rate_1h > 50%",
        "cooldown": "15 min",
        "message": "🔴 {provider} down: {error_rate}% errors"
    },
    "budget_warning": {
        "condition": "daily_spent > 80% of budget",
        "cooldown": "1 hour",
        "message": "💰 {provider} budget warning: ${spent}/${budget}"
    },
    "all_providers_down": {
        "condition": "all providers for platform in cooldown",
        "cooldown": "5 min",
        "message": "🚨 CRITICAL: No working providers for {platform}"
    }
}
```

#### 7.3.3 Routing UI (ВТОРОЙ ПРИОРИТЕТ)
```
┌─────────────────────────────────────────────────────────────┐
│ 🔀 Download Routing Rules                                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ Platform: [YouTube ▼]  Duration: [Any ▼]                    │
│                                                             │
│ ┌─── Provider Chain (drag to reorder) ──────────────────┐  │
│ │ 1. ⬛ yt-dlp          [🟢 Active] [⚙️ Config]         │  │
│ │ 2. ⬛ pytubefix       [🟢 Active] [⚙️ Config]         │  │
│ │ 3. ⬛ SaveNow API     [🟢 Active] [⚙️ Config]         │  │
│ │ 4. ⬛ RapidAPI        [🟡 Budget] [⚙️ Config]         │  │
│ │                                                        │  │
│ │ [+ Add Provider]                                       │  │
│ └────────────────────────────────────────────────────────┘  │
│                                                             │
│ ┌─── Rule Settings ─────────────────────────────────────┐  │
│ │ Duration min: [    ] sec   Duration max: [    ] sec   │  │
│ │ Max file size: [2000] MB   Priority: [1]              │  │
│ └────────────────────────────────────────────────────────┘  │
│                                                             │
│ [Save Rule] [Test Rule] [Delete]                            │
└─────────────────────────────────────────────────────────────┘
```

#### 7.3.4 Provider Management
```
┌─────────────────────────────────────────────────────────────┐
│ ⚙️ Provider: SaveNow API                                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ Type: [API ▼]  Status: [🟢 Active ▼]                        │
│                                                             │
│ ┌─── API Configuration ─────────────────────────────────┐  │
│ │ API Key: [sk-xxxxxxxxxxxxxxxx]                        │  │
│ │ API Host: [api.savenow.io]                            │  │
│ │ Rate Limit: [60] req/min                              │  │
│ └────────────────────────────────────────────────────────┘  │
│                                                             │
│ ┌─── Budget ────────────────────────────────────────────┐  │
│ │ Daily Budget: [$10.00]    Spent Today: $4.20          │  │
│ │ [x] Auto-disable when budget exceeded                 │  │
│ └────────────────────────────────────────────────────────┘  │
│                                                             │
│ ┌─── Health (24h) ──────────────────────────────────────┐  │
│ │ Success Rate: 98.5%       Avg Speed: 8.4 MB/s         │  │
│ │ Total Downloads: 1,247    Errors: 19                  │  │
│ │ [📊 View detailed stats]                              │  │
│ └────────────────────────────────────────────────────────┘  │
│                                                             │
│ [Save] [Test Connection] [View Logs]                        │
└─────────────────────────────────────────────────────────────┘
```

---

### 7.4 Future Improvements (Post-MVP)

**Отложено на потом:**
- [ ] **Async delivery mode** — для видео >30 мин: "готовлю, пришлю позже" + background worker
- [ ] **Soft fail budget** — бюджет кончился → "YouTube перегружен, попробуй позже" вместо hard block
- [ ] **Cancellation-safe downloads** — async cancel не оставляет мусор (tmp files, zombie processes)
- [ ] **Centralized download orchestrator** — один модуль для fallback логики (сейчас размазано по файлам)

---

### 7.5 Testing & Optimization (Phase 4)

**Тестовые сценарии:**
- [ ] Short video (<5 min) - должен качаться за <10 сек
- [ ] Medium video (5-30 min) - должен качаться за <2 мин
- [ ] Long video (30-60 min) - должен качаться за <5 мин или показать ошибку
- [ ] Very long video (>60 min) - fallback chain должен отрабатывать корректно

**Метрики успеха:**
- Success rate >95% для коротких видео
- Success rate >85% для длинных видео
- Среднее время fallback <5 сек
- Алерты приходят в течение 1 мин после проблемы

---

### 7.6 VPS Scaling

**Текущий VPS (Hostkey):**
- 2 vCore, 2GB RAM, 3TB traffic
- Недостаточно для 10K+ users/day

**Требования для масштабирования:**
- Traffic: 20-30TB/month минимум
- RAM: 4-8GB для concurrent downloads
- CPU: 4+ cores для ffmpeg
- Возможно: отдельный VPS для egress pool

---

## ФАЗА 8: Деплой на Hostkey

### Текущая архитектура:
```
HOSTKEY (66.151.33.167)          AEZA (185.96.80.254)
├── PostgreSQL :5432              ├── API (FastAPI) :8000
├── Redis :6379                   ├── Frontend (shadow-api.ru)
└── bot_manager                   └── Nginx + SSL
    └── @SaveNinja_bot
```

### Задачи:
- [ ] Автоматический деплой через GitHub Actions
- [ ] Мониторинг контейнеров
- [ ] Логи в централизованное хранилище

---

## ФАЗА 9: VPN Bot (Новый проект)

### Концепция:
- Telegram бот для продажи VPN
- Интеграция с Outline/WireGuard
- Оплата через Telegram Stars / криптой

### Задачи:
- [ ] Архитектура
- [ ] Выбор VPN протокола
- [ ] Интеграция оплаты
- [ ] Админка для управления ключами

---

## ПРИОРИТЕТЫ

| Приоритет | Задача | Сложность | Статус |
|-----------|--------|-----------|--------|
| ~~1~~ | ~~Фаза 3: Видео SAR + Ошибки~~ | ~~Средняя~~ | ✅ Готово |
| ~~2~~ | ~~Фаза 4: Billing Tracker~~ | ~~Средняя~~ | ✅ Готово |
| ~~3~~ | ~~Фаза 5: Bot Messages Editor~~ | ~~Средняя~~ | ✅ Готово |
| ~~4~~ | ~~Фаза 6: Performance Monitor~~ | ~~Средняя~~ | ✅ Готово |
| ~~5~~ | ~~YouTube полные видео~~ | ~~Низкая~~ | ✅ Готово |
| **1** | **Фаза 7: YouTube Provider Routing** | **Высокая** | 🔥 В работе |
| 2 | Фаза 8: GitHub Actions CI/CD | Средняя | Частично |
| 3 | Фаза 9: VPN Bot | Высокая | Отдельный проект |

---

## ПРАВИЛА РАБОТЫ С CLAUDE CODE

### Скорость:
```
ЛОКАЛЬНО: Редактирование, npm build, тесты
СЕРВЕР: Только деплой (scp, git pull, docker restart)
```

### Эффективные промпты:
```
✅ "Работай ЛОКАЛЬНО в C:\Projects\TelegramBots"
✅ "Покажи план, потом делай"
✅ "НЕ делай npm install на сервере"
✅ Маленькие задачи вместо "сделай всё"

❌ Длинные сессии (контекст теряется)
❌ Сборка на сервере с 1 ядром
```

### Субагенты:
Это нормально — Claude запускает параллельные задачи для чтения файлов.
Ускоряет работу при исследовании кодовой базы.

### Токены:
Показываются в конце задачи. Если прервал — не покажет.
