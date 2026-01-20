# API Costs & Subscriptions

**Последнее обновление:** 2026-01-20

## RapidAPI Subscriptions

### 1. Social Download All In One
- **URL:** https://rapidapi.com/manhgdev/api/social-download-all-in-one
- **Host:** `social-download-all-in-one.p.rapidapi.com`
- **Используется для:** TikTok, Instagram, Pinterest
- **Текущий план:** Basic (бесплатный)

| План | Цена | Requests | Overage | Rate Limit |
|------|------|----------|---------|------------|
| Basic | $0/мес | 100/мес | Hard Limit | 1000/hour |
| Pro | $2/мес | 6,000/мес | +$0.003 | 3/sec |
| Ultra | $5/мес | 22,000/мес | +$0.001 | 4/sec |
| Mega | $10/мес | 60,000/мес | +$0.001 | 5/sec |

**Bandwidth:** 10GB/мес включено, +$0.001/MB сверх

**Проблема:** Для YouTube возвращает googlevideo.com URLs → бан IP сервера

---

### 2. YouTube Info & Download API (НОВЫЙ) 🏆
- **URL:** https://rapidapi.com/valsuttlej53/api/youtube-info-download-api
- **Host:** `youtube-info-download-api.p.rapidapi.com`
- **Используется для:** YouTube (длинные видео)
- **Backend:** SaveNow.to (CDN проксирование)
- **Текущий план:** Basic (бесплатный)

**Важно:** SaveNow.to сайт показывает рекламу, но через RapidAPI wrapper получаем прямые CDN ссылки БЕЗ рекламы. API убирает рекламный слой.

| План | Цена | Units | Overage | Rate Limit |
|------|------|-------|---------|------------|
| Basic | $0/мес | 500/day | Hard Limit | 1000/hour |
| Pro | $5/мес | 100,000/мес | +$0.000047/unit | — |

**Pricing per download (units):**

| Формат | Цена | ~Downloads за 100K units |
|--------|------|--------------------------|
| MP3, M4A, WEBM, AAC, FLAC, WAV | $0.00030 | ~33,000 |
| MP4 360p-1080p, MOV | $0.00030 | ~33,000 |
| MP4 1440p, MOV 1440p | $0.00040 | ~25,000 |
| MP4 4K/8K, MOV 4K/8K | $0.00050 | ~20,000 |

**Duration multipliers:**
- До стандартного лимита: x1
- +90 мин сверх лимита: x3
- +180 мин сверх лимита: x5
- Каждые +90 мин: +x2 (x7, x9...)

**Стандартные лимиты по формату:**
- 4K/8K: 15 мин
- 1440p: 60 мин
- 1080p: 90 мин
- Остальные: 120 мин

**Преимущество:** CDN `*.savenow.to` — НЕ googlevideo.com, IP не банится!

**Тесты (2026-01-20):**
| Видео | Длина | Prep time | Cost |
|-------|-------|-----------|------|
| Rick Astley | 3:33 | 5 сек | $0.0003 |
| C# Tutorial | 4:31:09 | 50 сек | $0.0015 |
| Harvard CS50 | 24+ часа | — | ❌ Too long |

---

## Другие API (backup варианты)

### youtube-download-api.org
- **Цена:** $199/мес flat rate
- **CDN:** ✅ `media.yt-data-proxy.org` — проксируют через свой CDN
- **Лимиты:** Без лимитов? (нужен trial для проверки)
- **Статус:** 💰 Backup — слишком дорого для старта, но вариант при масштабе

### video-download-api.com
- **Цена:** ~$0.00030/download (pay-per-use)
- **CDN:** ❓ Нужно проверить — тот же автор что RapidAPI wrapper
- **Статус:** 🔄 Альтернатива если RapidAPI недоступен

### Cobalt.tools
- **Цена:** Бесплатно (self-hosted)
- **Статус:** ❌ Забанен YouTube с mid-2025

---

## Текущие расходы

| Сервис | План | Цена/мес |
|--------|------|----------|
| Social Download All In One | Basic | $0 |
| YouTube Info & Download API | Basic | $0 |
| **ИТОГО** | | **$0/мес** |

## Рекомендации по апгрейду

При росте трафика:

1. **YouTube Info & Download API → Pro ($5/мес)**
   - Когда: >500 YouTube downloads/day
   - Даст: 100K units = ~16K-33K downloads/мес

2. **Social Download All In One → Ultra ($5/мес)**
   - Когда: >100 TikTok/Instagram downloads/мес
   - Даст: 22K requests/мес

---

## API Keys

```env
# Social Download All In One (TikTok, Instagram)
RAPIDAPI_KEY=3a98632be0msh6686aaf9450a750p1cf661jsn3100d744f778
RAPIDAPI_HOST=social-download-all-in-one.p.rapidapi.com

# YouTube Info & Download API (YouTube CDN)
RAPIDAPI_YT_KEY=3a98632be0msh6686aaf9450a750p1cf661jsn3100d744f778
RAPIDAPI_YT_HOST=youtube-info-download-api.p.rapidapi.com
```

**Note:** Один и тот же RapidAPI key работает для обоих API.

---

## Мониторинг квоты через API

RapidAPI отправляет quota headers в каждом ответе:

```
x-ratelimit-requests-remaining: 4523    # Оставшиеся запросы
x-ratelimit-requests-reset: 86400       # Секунды до сброса
x-ratelimit-{billing-object}-remaining  # Для unit-based billing
```

**Логирование в боте:**
- `savenow_downloader.py` автоматически логирует `[SAVENOW-QUOTA]`
- Предупреждение при `remaining < 100`

**Dashboard:**
- RapidAPI: https://rapidapi.com/developer/billing/subscriptions-and-usage
