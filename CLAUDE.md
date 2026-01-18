# NEXUS PROJECT - ПРАВИЛА

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

**Загрузчики:**
- Instagram → RapidAPI (yt-dlp требует авторизации)
- TikTok, YouTube Shorts, Pinterest → yt-dlp (работает без API)

## Поддерживаемые платформы

| Платформа | Форматы | Движок |
|-----------|---------|--------|
| Instagram | Фото, видео, карусели, истории, актуальное | RapidAPI |
| Pinterest | Фото и видео | yt-dlp |
| TikTok | Видео без водяного знака | yt-dlp |
| YouTube Shorts | Короткие видео | yt-dlp |

## Трекинг пользователей

Бот автоматически:
- Сохраняет пользователей в `users` при первом сообщении
- Обновляет `last_active_at` при каждом сообщении
- Логирует действия в `action_logs`: start, help, download_request, download_success, audio_extracted
- Регистрирует себя в `bots` при запуске

Middleware: `bot_manager/middlewares/`

## Частые команды

```bash
# Логи ботов
ssh root@66.151.33.167 "docker logs nexus_bot_manager --tail 50"

# Логи админки API
ssh root@185.96.80.254 "docker logs admin_api --tail 50"

# Перезапуск ботов
ssh root@66.151.33.167 "cd /root/telegrambots/infrastructure && docker compose restart bot_manager"

# Перезапуск админки API
ssh root@185.96.80.254 "cd /root/admin_panel && docker compose restart"

# Пересборка ботов
ssh root@66.151.33.167 "cd /root/telegrambots && git pull && cd infrastructure && docker compose up -d --build bot_manager"
```

## Структура на серверах

### Hostkey (66.151.33.167)
```
/root/telegrambots/
├── infrastructure/
│   ├── docker-compose.yml
│   └── .env
├── bot_manager/
├── shared/
└── admin_panel/  # НЕ ИСПОЛЬЗУЕТСЯ!
```

### Aeza (185.96.80.254)
```
/root/admin_panel/
├── backend/
├── frontend/
├── docker-compose.yml
└── .env

/var/www/shadow-api/   # Собранный frontend
├── index.html
└── assets/
```

## ОБЯЗАТЕЛЬНО ДЕЛАТЬ

- **После значимых изменений обновлять:**
  - `CLAUDE.md` - если изменилась архитектура, креды, команды
  - `README.md` - если изменился функционал, поддерживаемые платформы

## НЕ ДЕЛАТЬ

- Не редактировать код через SSH
- Не создавать дубли моделей
- Не путать серверы!
- Не деплоить админку на Hostkey
- Не вставлять bcrypt хэши через shell (экранирование $)
