# Changelog

All notable changes to this project will be documented in this file.

## [1.2.1] - 2026-01-18

### Fixed
- **Critical: JSON парсинг ffprobe** — CSV формат не сохранял порядок полей, что приводило к width=0 и пропуску обработки видео
- Видео корректно отображается на iOS Telegram (SAR fix работает)
- VP9 видео автоматически перекодируются в H.264

### Added
- Детальное логирование обработки видео: `[FIX_VIDEO]`, `[FIX_TIKTOK]`
- Логи показывают: probe output, parsed values, decision (SKIP/RECODE/SCALE), result

### Changed
- ffprobe теперь использует JSON формат вместо CSV для надёжного парсинга

### Session Stats
- **Время сессии**: ~30 минут
- **Основная задача**: Диагностика и исправление деформации видео на iPhone
- **Коммиты**: 2 (logging + critical fix)

---

## [1.2.0] - 2026-01-17

### Added
- Профиль пользователя с активностью
- Статистика по платформам (Pie chart)
- Drag & Drop загрузка изображений
- Версия в футере

### Fixed
- График активности включает сегодняшний день
- Подсчёт юзеров бота
- Парсинг details в логах

---

## [1.1.0] - 2026-01-15

### Added
- SAR fix для видео (первая версия)
- Redis кэширование file_id
- RapidAPI интеграция для Instagram

---

## [1.0.0] - 2026-01-10

### Added
- Базовая админ-панель (Refine + Ant Design)
- Downloader бот (@SaveNinja_bot)
- PostgreSQL + Redis инфраструктура
- Docker Compose деплой
