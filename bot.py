import os
import logging
from typing import Optional
from datetime import datetime
import asyncio
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters
import aiohttp
from pydantic import BaseModel
import time
import re
from colorama import init, Fore, Style

# Initialize colorama
init()

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Constants
API_BASE_URL = os.getenv("API_BASE_URL")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
VIDEO_API_KEY = os.getenv("VIDEO_API_KEY")

PROGRESS_EMOJIS = ["⏳", "⌛️"]  # Чередовать при обновлении

SUPPORTED_DOMAINS = [
    "youtube.com",
    "youtu.be",
    "vimeo.com",
    "dailymotion.com",
    "facebook.com",
    "fb.watch",
    "instagram.com",
    "twitter.com",
    "x.com",
    "tiktok.com",
    "vm.tiktok.com"
]

def is_valid_url(url: str) -> bool:
    """Проверяет, является ли строка корректной ссылкой на поддерживаемый сайт."""
    # Базовая проверка на URL
    url_pattern = re.compile(
        r'^https?://'  # http:// или https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # домен
        r'localhost|'  # localhost
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # IP
        r'(?::\d+)?'  # порт
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    
    if not url_pattern.match(url):
        return False
    
    # Проверка на поддерживаемые домены
    return any(domain in url.lower() for domain in SUPPORTED_DOMAINS)

class VideoFormat(BaseModel):
    format_id: str
    format: str
    ext: str
    resolution: Optional[str]
    filesize: Optional[int]
    filesize_approx: Optional[int]

async def cleanup_messages(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_message_id: Optional[int] = None):
    """Удаляет предыдущие сообщения бота и сообщение пользователя."""
    if "message_ids" not in context.chat_data:
        context.chat_data["message_ids"] = []
    
    # Удаляем сообщения бота
    for message_id in context.chat_data["message_ids"]:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception as e:
            logger.error(f"Error deleting message {message_id}: {e}")
    
    # Удаляем сообщение пользователя, если оно есть
    if user_message_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=user_message_id)
        except Exception as e:
            logger.error(f"Error deleting user message {user_message_id}: {e}")
    
    context.chat_data["message_ids"] = []

async def store_message(context: ContextTypes.DEFAULT_TYPE, message):
    """Сохраняет ID сообщения для последующей очистки."""
    if "message_ids" not in context.chat_data:
        context.chat_data["message_ids"] = []
    context.chat_data["message_ids"].append(message.message_id)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    # Очищаем предыдущие сообщения и команду пользователя
    await cleanup_messages(context, update.message.chat_id, update.message.message_id)
    
    # Отправляем приветственное сообщение
    message = await update.message.reply_text(
        "👋 Привет! Я бот для скачивания видео.\n\n"
        "Просто отправь мне ссылку на видео, и я помогу тебе скачать его в нужном формате."
    )
    await store_message(context, message)

async def log_api_request(method: str, url: str, params: dict = None, headers: dict = None):
    """Логирование API запросов с цветом."""
    log_message = f"\n{Fore.CYAN}API Request:{Style.RESET_ALL}\n"
    log_message += f"{Fore.GREEN}Method:{Style.RESET_ALL} {method}\n"
    log_message += f"{Fore.GREEN}URL:{Style.RESET_ALL} {url}\n"
    
    if params:
        log_message += f"{Fore.GREEN}Params:{Style.RESET_ALL}\n"
        for key, value in params.items():
            log_message += f"  {Fore.YELLOW}{key}:{Style.RESET_ALL} {value}\n"
    
    if headers:
        log_message += f"{Fore.GREEN}Headers:{Style.RESET_ALL}\n"
        # Скрываем API ключ в логах
        safe_headers = headers.copy()
        if 'X-API-Key' in safe_headers:
            safe_headers['X-API-Key'] = '***'
        for key, value in safe_headers.items():
            log_message += f"  {Fore.YELLOW}{key}:{Style.RESET_ALL} {value}\n"
    
    logger.info(log_message)

async def log_api_response(status: int, data: str):
    """Логирование ответов API с цветом."""
    color = Fore.GREEN if 200 <= status < 300 else Fore.RED
    log_message = f"\n{Fore.CYAN}API Response:{Style.RESET_ALL}\n"
    log_message += f"{Fore.GREEN}Status:{Style.RESET_ALL} {color}{status}{Style.RESET_ALL}\n"
    log_message += f"{Fore.GREEN}Data:{Style.RESET_ALL}\n{data}\n"
    logger.info(log_message)

async def get_video_info(url: str) -> dict:
    """Get video information from API."""
    async with aiohttp.ClientSession() as session:
        headers = {"X-API-Key": VIDEO_API_KEY}
        params = {"url": url}
        full_url = f"{API_BASE_URL}/combined-info"
        
        await log_api_request("GET", full_url, params, headers)
        
        try:
            async with session.get(full_url, params=params, headers=headers) as response:
                response_text = await response.text()
                await log_api_response(response.status, response_text)
                
                if response.status != 200:
                    raise Exception(f"API error: {response_text}")
                return await response.json()
        except Exception as e:
            logger.error(f"{Fore.RED}Error in get_video_info: {str(e)}{Style.RESET_ALL}")
            raise

async def create_download_task(url: str, format_id: str, is_audio: bool = False) -> dict:
    """Create a download task."""
    async with aiohttp.ClientSession() as session:
        headers = {
            "X-API-Key": VIDEO_API_KEY,
            "accept": "application/json"
        }
        
        if is_audio:
            endpoint = f"{API_BASE_URL}/audio/download"
            params = {
                "url": url,
                "format": "high",  # Используем высокое качество для аудио
                "convert_to_mp3": "true"
            }
        else:
            endpoint = f"{API_BASE_URL}/download"
            # Определяем качество видео на основе format_id
            if format_id in ["SD", "HD", "FullHD"]:
                format_param = format_id
            else:
                format_param = format_id
                
            params = {
                "url": url,
                "format": format_param
            }
        
        await log_api_request("GET", endpoint, params, headers)
        
        async with session.get(endpoint, params=params, headers=headers) as response:
            response_text = await response.text()
            await log_api_response(response.status, response_text)
            
            if response.status == 202:  # API возвращает 202 при успешном создании задачи
                return await response.json()
            else:
                raise Exception(f"API error: {response_text}")

async def check_download_progress(task_id: str, session: aiohttp.ClientSession, headers: dict) -> dict:
    """Check download task progress."""
    url = f"{API_BASE_URL}/download/{task_id}"
    await log_api_request("GET", url, headers=headers)
    
    try:
        async with session.get(url, headers=headers) as response:
            response_text = await response.text()
            await log_api_response(response.status, response_text)
            
            if response.status != 200:
                raise Exception(f"API returned status {response.status}: {response_text}")
            return await response.json()
    except Exception as e:
        logger.error(f"{Fore.RED}Error in check_download_progress: {str(e)}{Style.RESET_ALL}")
        raise

def create_progress_bar(progress: int) -> str:
    """Создает индикатор прогресса."""
    filled = "▓" * int(progress / 8.33)  # 12 блоков всего
    empty = "░" * (12 - int(progress / 8.33))
    return f"{filled}{empty}"

async def update_progress_message(message, task_id: str, video_title: str):
    """Update progress message periodically."""
    headers = {"X-API-Key": VIDEO_API_KEY}
    
    # Используем существующее сообщение с обложкой
    progress_text = (
        "*🟩 Загрузка видео...*\n\n"
        f"🎬 Название: {video_title}\n"
        "⏳ Прогресс: ░░░░░░░░░░░░ 0%\n"
        "📂 Статус: Инициализация...\n"
        "💡 Пожалуйста, подождите."
    )
    
    try:
        await message.edit_caption(caption=progress_text, parse_mode='Markdown')
    except Exception:
        await message.edit_text(progress_text, parse_mode='Markdown')
    
    async with aiohttp.ClientSession() as session:
        retry_count = 0
        max_retries = 3
        
        while True:
            try:
                logger.info(f"Checking progress for task {task_id}")
                task_info = await check_download_progress(task_id, session, headers)
                logger.info(f"Task info received: {task_info}")
                
                status = task_info.get("status", "pending")
                progress = task_info.get("progress", 0)
                
                # Создаем индикатор прогресса
                progress_bar = create_progress_bar(progress)
                
                # Определяем статус на русском
                status_text = {
                    "pending": "Ожидание...",
                    "processing": "Обработка...",
                    "downloading": "Скачивание...",
                    "completed": "Завершено",
                    "error": "Ошибка"
                }.get(status, status)
                
                message_text = (
                    "*🟩 Загрузка видео...*\n\n"
                    f"🎬 Название: {video_title}\n"
                    f"⏳ Прогресс: {progress_bar} {progress:.1f}%\n"
                    f"📂 Статус: {status_text}\n"
                    "💡 Пожалуйста, подождите."
                )
                
                try:
                    await message.edit_caption(caption=message_text, parse_mode='Markdown')
                except Exception:
                    await message.edit_text(message_text, parse_mode='Markdown')
                
                if status == "completed":
                    if task_info.get("download_url"):
                        # Создаем кнопку для скачивания
                        keyboard = [[InlineKeyboardButton("⬇️ Скачать", url=task_info['download_url'])]]
                        reply_markup = InlineKeyboardMarkup(keyboard)
                        
                        completed_text = (
                            "*✅ Загрузка завершена!*\n\n"
                            f"🎬 Название: {video_title}\n\n"
                            "🔗 Ссылка для скачивания:\n\n"
                            "⚠️ Ссылка действительна в течение ограниченного времени."
                        )
                        try:
                            await message.edit_caption(
                                caption=completed_text,
                                parse_mode='Markdown',
                                reply_markup=reply_markup
                            )
                        except Exception:
                            await message.edit_text(
                                completed_text,
                                parse_mode='Markdown',
                                reply_markup=reply_markup
                            )
                    break
                elif status == "error":
                    error_message = task_info.get("error", "Неизвестная ошибка")
                    error_text = (
                        "*❌ Ошибка при скачивании!*\n\n"
                        f"🎬 Название: {video_title}\n"
                        f"❗️ Детали: {error_message}"
                    )
                    try:
                        await message.edit_caption(caption=error_text, parse_mode='Markdown')
                    except Exception:
                        await message.edit_text(error_text, parse_mode='Markdown')
                    break
                elif status == "pending" and retry_count >= max_retries:
                    timeout_text = (
                        "*⚠️ Превышено время ожидания!*\n\n"
                        f"🎬 Название: {video_title}\n"
                        "❗️ Пожалуйста, попробуйте позже."
                    )
                    try:
                        await message.edit_caption(caption=timeout_text, parse_mode='Markdown')
                    except Exception:
                        await message.edit_text(timeout_text, parse_mode='Markdown')
                    break
                
                retry_count = 0  # Сбрасываем счетчик при успешном запросе
                await asyncio.sleep(2)  # Проверяем каждые 2 секунды
                
            except Exception as e:
                logger.error(f"Error checking progress: {str(e)}")
                retry_count += 1
                
                if retry_count >= max_retries:
                    error_text = (
                        "*❌ Ошибка при отслеживании прогресса!*\n\n"
                        f"🎬 Название: {video_title}\n"
                        f"❗️ Детали: {str(e)}\n"
                        "💡 Попробуйте повторить запрос позже."
                    )
                    try:
                        await message.edit_caption(caption=error_text, parse_mode='Markdown')
                    except Exception:
                        await message.edit_text(error_text, parse_mode='Markdown')
                    break
                
                await asyncio.sleep(2 * retry_count)

async def handle_video_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle video URL messages."""
    url = update.message.text
    
    # Проверяем корректность ссылки
    if not is_valid_url(url):
        message = await update.message.reply_text(
            "❌ Некорректная ссылка!\n\n"
            "Поддерживаемые сайты:\n"
            "▫️ YouTube\n"
            "▫️ Vimeo\n"
            "▫️ DailyMotion\n"
            "▫️ Facebook\n"
            "▫️ Instagram\n"
            "▫️ Twitter/X\n"
            "▫️ TikTok\n\n"
            "Пожалуйста, отправьте корректную ссылку на видео."
        )
        await store_message(context, message)
        return
    
    context.user_data["video_url"] = url
    user_message_id = update.message.message_id
    
    # Очищаем предыдущие сообщения и сообщение пользователя
    await cleanup_messages(context, update.message.chat_id, user_message_id)
    
    # Отправляем сообщение о получении информации
    processing_message = await update.message.reply_text("🔍 Получаю информацию о видео...")
    await store_message(context, processing_message)
    
    try:
        video_info = await get_video_info(url)
        context.user_data["current_video"] = video_info
        
        # Удаляем сообщение о получении информации
        await cleanup_messages(context, update.message.chat_id)
        
        # Создаем клавиатуру с кнопками качества и размерами
        keyboard = []
        
        # Получаем все доступные форматы
        formats = video_info.get("video_formats", [])
        
        def format_size(size_bytes: int) -> str:
            for unit in ['B', 'KB', 'MB', 'GB']:
                if size_bytes < 1024:
                    return f"~{size_bytes:.1f} {unit}"
                size_bytes /= 1024
            return f"~{size_bytes:.1f} TB"
        
        # Группируем форматы по качеству
        for format in formats:
            if format.get("resolution") and format.get("filesize_approx"):
                resolution = format.get("resolution", "")
                size = format_size(format.get("filesize_approx"))
                quality_text = ""
                format_id = ""
                
                if "480" in resolution or "360" in resolution:
                    quality_text = "📼 SD"
                    format_id = "SD"
                elif "720" in resolution:
                    quality_text = "📺 HD"
                    format_id = "HD"
                elif "1080" in resolution:
                    quality_text = "🖥 FullHD"
                    format_id = "FullHD"
                elif "1440" in resolution:
                    quality_text = "🎮 2K"
                    format_id = format.get("format_id", "")
                elif "2160" in resolution:
                    quality_text = "📱 4K"
                    format_id = format.get("format_id", "")
                elif "3840" in resolution:
                    quality_text = "🖥 4K UHD"
                    format_id = format.get("format_id", "")
                else:
                    quality_text = "🎥"
                    format_id = format.get("format_id", "")
                
                button_text = f"{quality_text} ({size})"
                keyboard.append([InlineKeyboardButton(button_text, callback_data=f"format_{format_id}")])
        
        # Добавляем кнопку для аудио
        audio_size = "~40.02 MB"  # Примерный размер аудио
        keyboard.append([InlineKeyboardButton(f"🎵 Аудио ({audio_size})", callback_data="format_audio")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Форматируем длительность
        duration = video_info.get('duration', 0)
        minutes = duration // 60
        seconds = duration % 60
        duration_str = f"{minutes}:{seconds:02d}"
        
        # Форматируем статистику
        views = video_info.get('view_count', 0)
        likes = video_info.get('like_count', 0)
        comments = video_info.get('comment_count', 0)
        
        # Обрезаем длинное описание
        description = video_info.get('description', '')
        if len(description) > 300:
            description = description[:297] + "..."
        
        # Формируем текст описания с Markdown
        caption = (
            f"*{video_info.get('title', 'Без названия')}*\n\n"
            f"Автор: *{video_info.get('author', 'Неизвестен')}*\n\n"
            f"Описание:\n_{description}_\n\n"
            f"⏳ {duration_str} | 👍 {likes:,} | 👁 {views:,} | 💬 {comments:,}"
        )
        
        # Проверяем длину подписи и обрезаем при необходимости
        if len(caption) > 1024:
            # Если превышен лимит, отправляем описание отдельным сообщением
            if video_info.get('thumbnail'):
                message = await update.message.reply_photo(
                    photo=video_info['thumbnail'],
                    caption=f"*{video_info.get('title', 'Без названия')}*\n\n"
                           f"⏳ {duration_str} | 👍 {likes:,} | 👁 {views:,} | 💬 {comments:,}",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
                await update.message.reply_text(
                    f"Автор: *{video_info.get('author', 'Неизвестен')}*\n\n"
                    f"Описание:\n_{description}_",
                    parse_mode='Markdown'
                )
            else:
                message = await update.message.reply_text(
                    f"*{video_info.get('title', 'Без названия')}*\n\n"
                    f"⏳ {duration_str} | 👍 {likes:,} | 👁 {views:,} | 💬 {comments:,}",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
                await update.message.reply_text(
                    f"Автор: *{video_info.get('author', 'Неизвестен')}*\n\n"
                    f"Описание:\n_{description}_",
                    parse_mode='Markdown'
                )
        else:
            # Если длина в пределах лимита, отправляем всё вместе
            if video_info.get('thumbnail'):
                message = await update.message.reply_photo(
                    photo=video_info['thumbnail'],
                    caption=caption,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            else:
                message = await update.message.reply_text(
                    caption,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            
        # Сохраняем ID нового сообщения с информацией о видео
        await store_message(context, message)
            
    except Exception as e:
        logger.error(f"Error processing video URL: {str(e)}")
        error_message = await update.message.reply_text(
            "❌ Произошла ошибка при получении информации о видео.\n"
            f"Детали ошибки: {str(e)}"
        )
        await store_message(context, error_message)

async def handle_format_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle format selection."""
    query = update.callback_query
    await query.answer()
    
    format_type = query.data.replace("format_", "")
    video_info = context.user_data.get("current_video")
    
    if not video_info:
        message = await query.message.reply_text("❌ Информация о видео устарела. Пожалуйста, отправьте ссылку снова.")
        await store_message(context, message)
        return
    
    try:
        video_url = context.user_data.get("video_url")
        if not video_url:
            message = await query.message.reply_text("❌ URL видео не найден. Пожалуйста, отправьте ссылку снова.")
            await store_message(context, message)
            return
            
        if format_type == "audio":
            # Создаем задачу на скачивание аудио
            download_task = await create_download_task(video_url, "", is_audio=True)
            
            if "task_id" in download_task:
                await update_progress_message(
                    query.message,
                    download_task["task_id"],
                    f"{video_info.get('title', 'Аудио')} (Аудио)"
                )
            elif "error" in download_task:
                error_message = await query.message.reply_text(
                    f"❌ Ошибка при создании задачи: {download_task['error']}"
                )
                await store_message(context, error_message)
            else:
                # Если получили информацию о формате без task_id, создаем новую задачу
                format_id = download_task.get("format", "")
                if format_id:
                    format_task = await create_download_task(video_url, format_id, is_audio=True)
                    if "task_id" in format_task:
                        await update_progress_message(
                            query.message,
                            format_task["task_id"],
                            f"{video_info.get('title', 'Аудио')} (Аудио)"
                        )
                    else:
                        error_message = await query.message.reply_text(
                            "❌ Не удалось создать задачу на скачивание аудио."
                        )
                        await store_message(context, error_message)
                else:
                    error_message = await query.message.reply_text(
                        "❌ Не удалось получить информацию о формате аудио."
                    )
                    await store_message(context, error_message)
        else:
            # Создаем задачу на скачивание видео
            download_task = await create_download_task(video_url, format_type)
            
            if "task_id" in download_task:
                # Находим информацию о выбранном формате
                selected_format = next(
                    (f for f in video_info.get("video_formats", [])
                     if f["format_id"] == format_type),
                    None
                )
                
                quality_str = ""
                if selected_format and selected_format.get("resolution"):
                    quality_str = f" ({selected_format['resolution']})"
                
                await update_progress_message(
                    query.message,
                    download_task["task_id"],
                    f"{video_info.get('title', 'Видео')}{quality_str}"
                )
            elif "error" in download_task:
                error_message = await query.message.reply_text(
                    f"❌ Ошибка при создании задачи: {download_task['error']}"
                )
                await store_message(context, error_message)
            else:
                # Если получили информацию о формате без task_id, создаем новую задачу
                format_id = download_task.get("format", "")
                if format_id:
                    format_task = await create_download_task(video_url, format_id)
                    if "task_id" in format_task:
                        selected_format = next(
                            (f for f in video_info.get("video_formats", [])
                             if f["format_id"] == format_type),
                            None
                        )
                        
                        quality_str = ""
                        if selected_format and selected_format.get("resolution"):
                            quality_str = f" ({selected_format['resolution']})"
                        
                        await update_progress_message(
                            query.message,
                            format_task["task_id"],
                            f"{video_info.get('title', 'Видео')}{quality_str}"
                        )
                    else:
                        error_message = await query.message.reply_text(
                            "❌ Не удалось создать задачу на скачивание видео."
                        )
                        await store_message(context, error_message)
                else:
                    error_message = await query.message.reply_text(
                        "❌ Не удалось получить информацию о формате видео."
                    )
                    await store_message(context, error_message)
                    
    except Exception as e:
        logger.error(f"Error creating download task: {e}")
        error_message = await query.message.reply_text(
            "❌ Произошла ошибка при создании задачи на скачивание.\n"
            f"Детали ошибки: {str(e)}"
        )
        await store_message(context, error_message)

def main() -> None:
    """Start the bot."""
    if not TELEGRAM_TOKEN:
        logger.error("Telegram token not found!")
        return
    
    if not VIDEO_API_KEY:
        logger.error("Video API key not found!")
        return
    
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_video_url))
    application.add_handler(CallbackQueryHandler(handle_format_selection, pattern="^format_"))

    # Start the bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main() 