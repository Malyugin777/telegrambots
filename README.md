# Nexus Project - Telegram Bot Network

Multi-bot Telegram network with shared database and admin panel.

## Quick Start (Development)

### 1. Prerequisites
- Python 3.12+
- Docker & Docker Compose
- Telegram Bot tokens from [@BotFather](https://t.me/BotFather)

### 2. Setup Environment

```bash
cd infrastructure
cp .env.example .env
# Edit .env with your tokens and settings
```

### 3. Start Database (Docker)

```bash
cd infrastructure
docker-compose -f docker-compose.dev.yml up -d
```

### 4. Install Dependencies

```bash
cd bot_net
pip install -r requirements.txt
```

### 5. Run Bots

```bash
# From project root
python -m bot_net.main
```

## Project Structure

```
nexus_project/
├── infrastructure/     # Docker, configs
├── bot_net/           # Telegram bots (Aiogram 3)
│   ├── core/          # Shared: DB, middlewares
│   └── bots/          # Individual bots
├── admin_panel/       # Web panel (FastAPI + React)
├── shared/            # Shared config
└── userbots/          # Telethon (future)
```

## Adding a New Bot

1. Create folder in `bot_net/bots/your_bot/`
2. Create `handlers.py` with your handlers
3. Create `bot.py` with factory function
4. Import and run in `bot_net/main.py`

## Tech Stack

- **Bots**: Aiogram 3, Python 3.12
- **Database**: PostgreSQL 16, SQLAlchemy 2.0 (async)
- **Cache/FSM**: Redis 7
- **API**: FastAPI (planned)
- **Frontend**: React (planned)
