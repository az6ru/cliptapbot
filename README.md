# Video Download Bot

Telegram бот для скачивания видео с различных платформ (YouTube, Vimeo, TikTok и др.)

## Возможности

- Скачивание видео в разных качествах (SD, HD, FullHD, 4K)
- Извлечение аудио в MP3
- Поддержка множества платформ
- Удобный интерфейс с кнопками
- Отображение прогресса загрузки

## Требования

- Docker и Docker Compose
- Telegram Bot Token (получить у @BotFather)
- API ключ для Video API

## Установка и запуск

1. Клонируйте репозиторий:
```bash
git clone <repository-url>
cd video-download-bot
```

2. Создайте файл .env на основе .env.example:
```bash
cp .env.example .env
```

3. Отредактируйте .env файл:
```
TELEGRAM_TOKEN=your_telegram_bot_token
VIDEO_API_KEY=your_video_api_key
API_BASE_URL=https://api-url/api
```

4. Запустите бота через Docker Compose:
```bash
docker-compose up -d
```

## Мониторинг

Просмотр логов:
```bash
docker-compose logs -f bot
```

## Обновление

1. Остановите бота:
```bash
docker-compose down
```

2. Получите последние изменения:
```bash
git pull
```

3. Пересоберите и запустите:
```bash
docker-compose up -d --build
```

## Поддерживаемые платформы

- YouTube
- Vimeo
- DailyMotion
- Facebook
- Instagram
- Twitter/X
- TikTok

## Лицензия

MIT License 