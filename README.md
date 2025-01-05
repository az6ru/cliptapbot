# Video Download Telegram Bot

Telegram бот для скачивания видео с использованием Video Metadata Service API.

## Возможности

- Получение информации о видео (название, автор, длительность)
- Выбор качества и формата видео
- Скачивание видео по прямой ссылке
- Поддержка различных видео платформ

## Установка

1. Клонируйте репозиторий:
```bash
git clone <repository-url>
cd <repository-name>
```

2. Создайте виртуальное окружение и активируйте его:
```bash
python -m venv venv
source venv/bin/activate  # для Linux/Mac
venv\Scripts\activate     # для Windows
```

3. Установите зависимости:
```bash
pip install -r requirements.txt
```

4. Создайте файл `.env` на основе `.env.example`:
```bash
cp .env.example .env
```

5. Отредактируйте `.env` файл:
- Получите токен бота у [@BotFather](https://t.me/BotFather)
- Укажите API ключ для Video Metadata Service
- При необходимости измените базовый URL API

## Запуск

```bash
python bot.py
```

## Использование

1. Начните чат с ботом командой `/start`
2. Отправьте боту ссылку на видео
3. Выберите желаемый формат из предложенных
4. Получите ссылку на скачивание

## Требования

- Python 3.7+
- Токен Telegram бота
- Ключ доступа к Video Metadata Service API

## Лицензия

MIT 