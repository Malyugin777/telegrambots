# Nexus Project

Система управления сетью Telegram-ботов с веб-админкой.

## Боты

| Бот | Username | Описание |
|-----|----------|----------|
| SaveNinja | @SaveNinja_bot | Скачивание видео из TikTok, Instagram, YouTube Shorts, Pinterest |

## Домены

| Домен | Назначение |
|-------|------------|
| admin.shadow-api.ru | Админ-панель |
| shadow-api.ru | Админ-панель |
| api.shadow-api.ru | API (FastAPI) |

## Архитектура

```
                         NGINX (порт 80)
              admin.shadow-api.ru -> Frontend
              api.shadow-api.ru -> API
                         |
          +--------------+--------------+
          |                             |
          v                             v
   Frontend (React)              API (FastAPI)
   Refine + Ant Design            /api/v1/...
                                       |
                        +--------------+--------------+
                        |                             |
                        v                             v
                   PostgreSQL                      Redis
                     :5432                         :6379
                        ^                             ^
                        |                             |
                        +-------------+---------------+
                                      |
                              Downloader Bot
                              (SaveNinja)
```

## Стек технологий

**Backend:**
- Python 3.12
- FastAPI + Uvicorn
- SQLAlchemy 2.0 (async)
- PostgreSQL 16
- Redis 7

**Frontend:**
- React 18 + TypeScript
- Refine.dev (admin framework)
- Ant Design 5
- Vite

**Боты:**
- Aiogram 3
- yt-dlp (скачивание видео)
- ffmpeg (конвертация)
- FSM на Redis

**Инфраструктура:**
- Docker + Docker Compose
- Nginx (reverse proxy)
- GitHub Actions (CI/CD)

## Структура проекта

```
nexus_project/
├── infrastructure/              # Docker, Nginx конфиги
│   ├── docker-compose.yml
│   ├── nginx/nginx.conf
│   └── .env.example
│
├── bot_net/                     # Telegram боты
│   ├── core/                    # Общий код
│   │   ├── database/
│   │   └── utils/
│   └── bots/
│       └── downloader_bot/      # SaveNinja (@SaveNinja_bot)
│           ├── Dockerfile
│           ├── main.py
│           ├── config.py
│           ├── handlers/
│           ├── middlewares/
│           ├── services/
│           └── keyboards/
│
├── admin_panel/
│   ├── backend/                 # FastAPI
│   │   └── src/
│   └── frontend/                # React + Refine
│       └── src/
│
└── shared/                      # Общий код
```

## Деплой

### Автоматический (GitHub Actions)

При пуше в `main` автоматически:
1. SSH на сервер
2. `git pull`
3. `docker compose down`
4. `docker compose up -d --build`

### Ручной

```bash
ssh root@66.151.33.167 "cd /root/nexus_project && git pull && cd infrastructure && docker compose up -d --build"
```

## Настройка

### 1. Переменные окружения

Файл `infrastructure/.env`:

```env
# Database
POSTGRES_USER=nexus
POSTGRES_PASSWORD=<пароль>
POSTGRES_DB=nexus_db
DATABASE_URL=postgresql+asyncpg://nexus:<пароль>@postgres:5432/nexus_db

# Redis
REDIS_URL=redis://redis:6379/0

# Downloader Bot (SaveNinja)
DOWNLOADER_BOT_TOKEN=<токен от BotFather>
FORCE_SUB_CHANNELS=@channel1,@channel2
MAX_FILE_SIZE_MB=50

# API
JWT_SECRET=<случайная строка>
```

### 2. Токен бота

1. Открой @BotFather в Telegram
2. `/newbot` -> получи токен
3. Добавь в `.env` как `DOWNLOADER_BOT_TOKEN`
4. Перезапусти: `docker compose restart nexus_downloader`

## Добавление нового бота

1. Создай папку `bot_net/bots/new_bot/`
2. Добавь структуру:
   ```
   new_bot/
   ├── Dockerfile
   ├── main.py
   ├── config.py
   ├── handlers/
   ├── middlewares/
   └── services/
   ```
3. Добавь сервис в `docker-compose.yml`:
   ```yaml
   new_bot:
     build:
       context: ..
       dockerfile: bot_net/bots/new_bot/Dockerfile
     container_name: nexus_new_bot
     env_file:
       - .env
     depends_on:
       postgres:
         condition: service_healthy
       redis:
         condition: service_healthy
   ```
4. Добавь токен в `.env`: `NEW_BOT_TOKEN=...`
5. Задеплой: `git push`

## API Endpoints

**Auth:**
- `POST /api/v1/auth/login` — получить JWT токен
- `POST /api/v1/auth/register` — регистрация админа

**Stats:**
- `GET /api/v1/stats` — статистика (users, bots, активность)
- `GET /api/v1/stats/load-chart` — график нагрузки

**Bots:**
- `GET /api/v1/bots` — список ботов
- `POST /api/v1/bots` — добавить бота
- `PATCH /api/v1/bots/{id}` — изменить статус

**Users:**
- `GET /api/v1/users` — список пользователей
- `PATCH /api/v1/users/{id}/ban` — забанить

## Полезные команды

```bash
# Логи всех сервисов
ssh root@66.151.33.167 "cd /root/nexus_project/infrastructure && docker compose logs -f"

# Логи конкретного сервиса
docker logs nexus_downloader --tail 100
docker logs nexus_api --tail 100
docker logs nexus_nginx --tail 100

# Перезапуск сервиса
docker restart nexus_downloader

# Статус контейнеров
docker ps
```

## GitHub Secrets

| Secret | Значение |
|--------|----------|
| SERVER_HOST | 66.151.33.167 |
| SERVER_USER | root |
| SERVER_PASSWORD | пароль от VPS |

## Сборка Frontend

Frontend собирается локально (VPS не хватает RAM):

```bash
cd admin_panel/frontend
npm install
npm run build
git add dist/
git commit -m "build frontend"
git push
```

## Контакты

- VPS IP: 66.151.33.167
- Репозиторий: https://github.com/Malyugin777/telegrambots
