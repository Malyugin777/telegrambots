# Plan: Ops Dashboard v2 - Production Level

## Обзор изменений

Текущее состояние:
- `bucket` = duration-based (shorts/medium/long)
- Нет управления провайдерами
- Frontend показывает только platform без детализации

Целевое состояние:
- `bucket` = content-type based (shorts/full, reel/post/story/carousel, etc.)
- Provider state management (enable/disable/cooldown)
- Frontend с toggle "Платформы / Подтипы" + управление провайдерами

---

## Phase 1: Telemetry Enhancement (bot_manager)

### 1.1 Изменить bucket логику

**Файл:** `bot_manager/bots/downloader/handlers/download.py`

Изменить функцию `get_duration_bucket()` → `get_content_bucket()`:

```python
def get_content_bucket(platform: str, content_type: str = None, duration_sec: int = 0) -> str:
    """
    Определяет bucket по типу контента:
    - youtube: shorts (<5min) / full (>=5min)
    - instagram: reel / post / story / carousel
    - tiktok: video
    - pinterest: photo / video
    """
    if platform == "youtube":
        return "shorts" if duration_sec < 300 else "full"
    elif platform == "instagram":
        return content_type or "post"  # reel/post/story/carousel
    elif platform == "tiktok":
        return "video"
    elif platform == "pinterest":
        return content_type or "video"  # photo/video
    return "unknown"
```

### 1.2 Обновить все log_action вызовы

Места в `download.py` где нужно добавить bucket:

1. **Instagram carousel** (строка ~586):
   ```python
   "bucket": "carousel",
   ```

2. **Instagram single file** (строка ~840 для photo, ~964 для video):
   - Для reel: `"bucket": "reel"` (проверить по URL или metadata)
   - Для post: `"bucket": "post"`
   - Для story: `"bucket": "story"`

3. **YouTube** (строка ~964):
   ```python
   "bucket": "shorts" if duration < 300 else "full"
   ```

4. **TikTok/Pinterest** - добавить bucket в существующую телеметрию

### 1.3 Определение Instagram bucket

Добавить helper для определения типа Instagram контента:

```python
def detect_instagram_bucket(url: str, metadata: dict = None) -> str:
    """Определяет тип Instagram контента по URL/metadata"""
    url_lower = url.lower()
    if "/reel/" in url_lower or "/reels/" in url_lower:
        return "reel"
    elif "/stories/" in url_lower:
        return "story"
    elif metadata and metadata.get("is_carousel"):
        return "carousel"
    return "post"
```

---

## Phase 2: Ops API Enhancement (admin_panel/backend)

### 2.1 Добавить group_by parameter

**Файл:** `admin_panel/backend/src/api/ops.py`

Изменить endpoint `/ops/platforms`:

```python
@router.get("/platforms", response_model=PlatformsResponse)
async def get_platforms_stats(
    range: str = Query("24h"),
    group_by: str = Query("platform", description="platform or bucket"),
    ...
):
```

Если `group_by == "bucket"`:
- Группировать по `platform + bucket`
- Ключ в ответе: `"youtube:shorts"`, `"youtube:full"`, `"instagram:reel"`, etc.

### 2.2 Добавить p95_upload_ms

В `PlatformStats` добавить:
```python
p95_upload_ms: Optional[float] = None
```

В aggregation добавить сбор `upload_ms` из `details`.

### 2.3 Provider State Management

**Новые Redis ключи:**
```
provider:ytdlp:enabled = "true"
provider:ytdlp:cooldown_until = "2026-01-21T12:00:00Z"
```

**Новые endpoints:**

```python
@router.post("/providers/{provider}/enable")
async def enable_provider(provider: str):
    redis = await get_redis()
    await redis.set(f"provider:{provider}:enabled", "true")
    return {"status": "enabled"}

@router.post("/providers/{provider}/disable")
async def disable_provider(provider: str):
    redis = await get_redis()
    await redis.set(f"provider:{provider}:enabled", "false")
    return {"status": "disabled"}

@router.post("/providers/{provider}/cooldown")
async def set_cooldown(provider: str, minutes: int = Query(30)):
    redis = await get_redis()
    until = datetime.utcnow() + timedelta(minutes=minutes)
    await redis.set(f"provider:{provider}:cooldown_until", until.isoformat())
    await redis.expire(f"provider:{provider}:cooldown_until", minutes * 60)
    return {"status": "cooldown", "until": until.isoformat()}
```

### 2.4 Обновить /ops/providers response

Добавить в `ProviderStats`:
```python
enabled: bool = True
cooldown_until: Optional[datetime] = None
health: str = "healthy"  # healthy / degraded / down
```

---

## Phase 3: Frontend Enhancement

### 3.1 Platforms Tab - Toggle

**Файл:** `admin_panel/frontend/src/pages/ops/index.tsx`

Добавить:
```tsx
const [groupBy, setGroupBy] = useState<'platform' | 'bucket'>('platform');

// В query
config: { query: { range: timeRange, group_by: groupBy } }

// UI toggle
<Segmented
  options={[
    { label: 'Платформы', value: 'platform' },
    { label: 'Подтипы', value: 'bucket' },
  ]}
  value={groupBy}
  onChange={setGroupBy}
/>
```

### 3.2 Providers Tab - Controls

```tsx
// Enabled toggle
<Switch
  checked={provider.enabled}
  onChange={(checked) => toggleProvider(provider.provider, checked)}
/>

// Cooldown badge
{provider.cooldown_until && (
  <Badge color="orange">
    Cooldown до {formatTime(provider.cooldown_until)}
  </Badge>
)}

// Health badge
<Badge color={provider.health === 'healthy' ? 'green' : provider.health === 'degraded' ? 'yellow' : 'red'}>
  {provider.health === 'healthy' ? '🟢' : provider.health === 'degraded' ? '🟡' : '🔴'}
</Badge>
```

### 3.3 Русификация + Tooltips

```tsx
// P95 tooltip
<Tooltip title="95% загрузок быстрее этого времени">
  <span>P95</span>
</Tooltip>

// Переводы
const translations = {
  'Overall Success Rate': 'Общий % успеха',
  'Worst P95 Latency': 'Худшая P95 задержка',
  'Quota Forecast': 'Прогноз квоты',
  'Active Operations': 'Активные операции',
  'Platforms': 'Платформы',
  'Subtypes': 'Подтипы',
  'Providers': 'Провайдеры',
  'System & Quota': 'Система и квота',
};
```

---

## Порядок выполнения

1. **Phase 1.1-1.3**: Telemetry в bot_manager (30 min)
2. **Phase 2.1-2.2**: Ops API group_by + p95_upload (20 min)
3. **Phase 2.3-2.4**: Provider state management (25 min)
4. **Phase 3.1-3.3**: Frontend updates (30 min)
5. **Deploy**: git push + Aeza deploy (10 min)

**Total: ~2 часа**

---

## Файлы для изменения

| Файл | Изменения |
|------|-----------|
| `bot_manager/bots/downloader/handlers/download.py` | bucket logic, detect_instagram_bucket |
| `admin_panel/backend/src/api/ops.py` | group_by, p95_upload, provider state |
| `admin_panel/frontend/src/pages/ops/index.tsx` | toggle, controls, русификация |
