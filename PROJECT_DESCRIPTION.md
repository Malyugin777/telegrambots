# Nexus Project - Полное описание

## Обзор проекта

Nexus Project — сетка Telegram-ботов с единой базой данных, системой управления и веб-панелью администратора "Nexus Control".

---

## Текущий статус

### Фаза 1: Infrastructure + База — ГОТОВО

| Компонент | Статус | Описание |
|-----------|--------|----------|
| Docker Compose | ✅ | PostgreSQL 16 + Redis 7 + Nginx |
| Конфигурация | ✅ | Pydantic Settings, .env |
| База данных | ✅ | SQLAlchemy 2.0 async |
| Модели | ✅ | User, Bot, BotUser, ActionLog, Broadcast |

### Фаза 2: Core ботов — ГОТОВО

| Компонент | Статус | Описание |
|-----------|--------|----------|
| DatabaseMiddleware | ✅ | Инъекция session в хендлеры |
| UserRegisterMiddleware | ✅ | Авторегистрация пользователей |
| BanCheckMiddleware | ✅ | Блокировка забаненных |
| Logging | ✅ | Настроенное логирование |

### Фаза 3: Первый бот — ГОТОВО

| Компонент | Статус | Описание |
|-----------|--------|----------|
| Main Bot | ✅ | Базовые команды: /start, /help, /me, /stats |
| Bot Factory | ✅ | Фабрика для создания бота |
| Entry Point | ✅ | main.py для запуска всех ботов |

### Фаза 4: Admin Bot — В ОЧЕРЕДИ

| Компонент | Статус | Описание |
|-----------|--------|----------|
| Admin Bot | ⏳ | Управление через Telegram |
| User Management | ⏳ | Бан/разбан, смена ролей |
| Statistics | ⏳ | Статистика по ботам |
| Broadcast | ⏳ | Рассылка по пользователям |

### Фаза 5: Веб-панель "Nexus Control" — ГОТОВО

| Компонент | Статус | Описание |
|-----------|--------|----------|
| FastAPI Backend | ✅ | REST API для админки |
| React + Refine Frontend | ✅ | Веб-интерфейс с Ant Design |
| JWT Auth | ✅ | Авторизация с токенами |
| Dashboard | ✅ | Статистика и графики |
| Bot Fleet | ✅ | CRUD управление ботами |
| Broadcasts | ✅ | Создание и управление рассылками |
| Users | ✅ | Просмотр, бан, смена ролей |

### Фаза 6: Деплой — ГОТОВО

| Компонент | Статус | Описание |
|-----------|--------|----------|
| Docker Production | ✅ | Nginx + SSL + Let's Encrypt |
| Domain Setup Guide | ✅ | Инструкция для Reg.ru |

---

## Архитектура

### Структура проекта

```
nexus_project/
├── infrastructure/
│   ├── docker-compose.yml          # Полный production стек
│   ├── docker-compose.dev.yml      # Dev: только БД + Redis
│   ├── nginx/
│   │   └── nginx.conf              # Reverse proxy + SSL
│   ├── certbot/                    # SSL сертификаты
│   ├── init-letsencrypt.sh         # Скрипт получения SSL
│   ├── .env.example                # Шаблон переменных
│   └── .env                        # Секреты (не в git!)
│
├── bot_net/                        # Сетка ботов (Aiogram 3)
│   ├── core/
│   │   ├── database/
│   │   │   ├── models.py           # SQLAlchemy модели
│   │   │   └── connection.py       # Async подключение
│   │   ├── middlewares/
│   │   │   ├── database.py         # Инъекция сессии
│   │   │   ├── user_register.py    # Регистрация юзеров
│   │   │   └── ban_check.py        # Проверка банов
│   │   └── utils/
│   │       └── logging.py          # Логирование
│   ├── bots/
│   │   ├── main_bot/
│   │   │   ├── bot.py              # Фабрика бота
│   │   │   └── handlers.py         # Хендлеры команд
│   │   └── admin_bot/              # [В РАЗРАБОТКЕ]
│   ├── main.py                     # Точка входа
│   ├── requirements.txt
│   └── Dockerfile
│
├── admin_panel/
│   ├── backend/                    # FastAPI API
│   │   ├── src/
│   │   │   ├── main.py             # Entry point
│   │   │   ├── config.py           # Настройки
│   │   │   ├── database.py         # DB connection
│   │   │   ├── redis_client.py     # Redis connection
│   │   │   ├── models.py           # SQLAlchemy модели
│   │   │   ├── schemas.py          # Pydantic схемы
│   │   │   ├── auth.py             # JWT авторизация
│   │   │   └── api/
│   │   │       ├── auth.py         # /auth endpoints
│   │   │       ├── stats.py        # /stats endpoints
│   │   │       ├── bots.py         # /bots CRUD
│   │   │       ├── users.py        # /users endpoints
│   │   │       └── broadcasts.py   # /broadcasts CRUD
│   │   ├── requirements.txt
│   │   └── Dockerfile
│   │
│   └── frontend/                   # React + Refine + Ant Design
│       ├── src/
│       │   ├── App.tsx             # Главный компонент
│       │   ├── providers/
│       │   │   ├── dataProvider.ts # API клиент
│       │   │   └── authProvider.ts # Авторизация
│       │   └── pages/
│       │       ├── dashboard/      # Статистика
│       │       ├── bots/           # Управление ботами
│       │       ├── broadcasts/     # Рассылки
│       │       ├── users/          # Пользователи
│       │       └── login/          # Вход
│       ├── package.json
│       ├── vite.config.ts
│       ├── nginx.conf              # SPA routing
│       └── Dockerfile
│
├── shared/
│   └── config.py                   # Общая конфигурация
│
├── .gitignore
├── README.md
├── PROJECT_DESCRIPTION.md          # Этот файл
└── DOMAIN_SETUP_GUIDE.md           # Инструкция по домену
```

---

## Веб-панель "Nexus Control"

### Страницы

#### Dashboard
- Карточки статистики: всего ботов, активных, пользователей, DAU, очередь сообщений
- График активности за 7 дней (сообщения + пользователи)

#### Bot Fleet
- Таблица ботов с фильтрами и поиском
- Колонки: ID, Name, Username, Status, Token (hash), Webhook
- Действия: View, Edit, Restart, Delete
- Создание нового бота

#### Broadcasts
- Список рассылок с фильтром по статусу
- Создание рассылки: текст, картинка, inline-кнопки
- Таргетинг: по ботам, по языку
- Планирование отправки
- Прогресс выполнения

#### Users
- Список Telegram-пользователей
- Фильтры: по роли, по статусу бана
- Детали пользователя
- Действия: смена роли, бан/разбан

### API Endpoints

```
POST /api/v1/auth/login           # Вход
POST /api/v1/auth/setup           # Первый админ
GET  /api/v1/auth/me              # Текущий пользователь

GET  /api/v1/stats                # Статистика
GET  /api/v1/stats/chart          # Данные для графика

GET  /api/v1/bots                 # Список ботов
POST /api/v1/bots                 # Создать бота
GET  /api/v1/bots/{id}            # Детали бота
PATCH /api/v1/bots/{id}           # Обновить бота
DELETE /api/v1/bots/{id}          # Удалить бота
POST /api/v1/bots/{id}/restart    # Перезапустить

GET  /api/v1/users                # Список пользователей
GET  /api/v1/users/{id}           # Детали пользователя
PATCH /api/v1/users/{id}/ban      # Бан/разбан
PATCH /api/v1/users/{id}/role     # Смена роли

GET  /api/v1/broadcasts           # Список рассылок
POST /api/v1/broadcasts           # Создать рассылку
GET  /api/v1/broadcasts/{id}      # Детали
PATCH /api/v1/broadcasts/{id}     # Обновить
DELETE /api/v1/broadcasts/{id}    # Удалить
POST /api/v1/broadcasts/{id}/start  # Запустить
POST /api/v1/broadcasts/{id}/cancel # Отменить
```

---

## Модели базы данных

### User
| Поле | Тип | Описание |
|------|-----|----------|
| id | Integer | PK |
| telegram_id | BigInteger | Telegram ID |
| username | String(255) | @username |
| first_name | String(255) | Имя |
| last_name | String(255) | Фамилия |
| language_code | String(10) | Код языка |
| role | Enum | user/moderator/admin/owner |
| is_banned | Boolean | Забанен ли |
| ban_reason | Text | Причина бана |
| created_at | DateTime | Регистрация |
| last_active_at | DateTime | Активность |

### Bot
| Поле | Тип | Описание |
|------|-----|----------|
| id | Integer | PK |
| name | String(100) | Уникальное имя |
| token_hash | String(64) | SHA-256 хеш токена |
| bot_username | String(255) | @username бота |
| webhook_url | String(500) | Webhook URL |
| status | Enum | active/paused/maintenance/disabled |
| settings | JSON | Настройки |

### Broadcast
| Поле | Тип | Описание |
|------|-----|----------|
| id | Integer | PK |
| name | String(255) | Название |
| text | Text | Текст сообщения |
| image_url | String(500) | URL картинки |
| buttons | JSON | Inline кнопки |
| target_bots | JSON | Список ID ботов |
| target_languages | JSON | Список языков |
| status | Enum | draft/scheduled/running/completed/cancelled |
| total_recipients | Integer | Всего получателей |
| sent_count | Integer | Отправлено |
| failed_count | Integer | Ошибок |

### AdminUser
| Поле | Тип | Описание |
|------|-----|----------|
| id | Integer | PK |
| username | String(100) | Логин |
| email | String(255) | Email |
| password_hash | String(255) | Хеш пароля |
| is_superuser | Boolean | Суперадмин |

---

## Технологии

| Категория | Технология | Версия |
|-----------|------------|--------|
| **Боты** | Aiogram | 3.14.0 |
| **Backend** | FastAPI | 0.115.6 |
| **Frontend** | React | 18.3.1 |
| **UI Framework** | Refine.dev | 4.54.0 |
| **UI Library** | Ant Design | 5.22.2 |
| **Графики** | Ant Design Charts | 2.2.1 |
| **ORM** | SQLAlchemy | 2.0.36 |
| **БД** | PostgreSQL | 16 |
| **Кеш** | Redis | 7 |
| **Proxy** | Nginx | alpine |
| **SSL** | Let's Encrypt | certbot |

---

## Запуск

### Development (локально)

```bash
# 1. Запустить БД
cd infrastructure
docker-compose -f docker-compose.dev.yml up -d

# 2. Backend
cd ../admin_panel/backend
pip install -r requirements.txt
uvicorn src.main:app --reload --port 8000

# 3. Frontend
cd ../frontend
npm install
npm run dev

# 4. Боты
cd ../../bot_net
pip install -r requirements.txt
python -m bot_net.main
```

### Production (Docker)

```bash
cd infrastructure

# 1. Настроить .env
cp .env.example .env
nano .env

# 2. Получить SSL (первый раз)
./init-letsencrypt.sh

# 3. Запустить всё
docker-compose up -d
```

---

## Дополнительные документы

- `DOMAIN_SETUP_GUIDE.md` — пошаговая инструкция настройки домена на Reg.ru
- `README.md` — краткая документация
