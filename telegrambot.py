import asyncio
import logging
import random
import aiohttp
from bs4 import BeautifulSoup
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.types import CallbackQuery
import json
from collections import defaultdict
import re
from config import BOT_TOKEN

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Список для хранения анекдотов
jokes_list = []

# Словари для хранения рейтингов и истории просмотров
joke_ratings = defaultdict(lambda: {'likes': 0, 'dislikes': 0})
user_history = defaultdict(list)

# URLs для парсинга
URLS = {
    'litres': "https://www.litres.ru/book/raznoe-47672/samye-smeshnye-anekdoty-23556560/chitat-onlayn/",
    'kartaslov': "https://kartaslov.ru/книги/Самые_убойные_анекдоты"
}

# Функция для сохранения рейтингов
async def save_ratings():
    try:
        with open('joke_ratings.json', 'w', encoding='utf-8') as f:
            json.dump(dict(joke_ratings), f, ensure_ascii=False, indent=2)
        logger.info("Рейтинги успешно сохранены")
    except Exception as e:
        logger.error(f"Ошибка при сохранении рейтингов: {str(e)}")

# Функция для загрузки рейтингов
async def load_ratings():
    try:
        with open('joke_ratings.json', 'r', encoding='utf-8') as f:
            loaded_ratings = json.load(f)
            joke_ratings.update(loaded_ratings)
        logger.info("Рейтинги успешно загружены")
    except FileNotFoundError:
        logger.info("Файл с рейтингами не найден, начинаем с пустого списка")
    except Exception as e:
        logger.error(f"Ошибка при загрузке рейтингов: {str(e)}")

# Создаем клавиатуру с инлайн кнопками
def get_main_keyboard():
    keyboard = [
        [
            InlineKeyboardButton(text="👋 Приветствие", callback_data="greeting"),
            InlineKeyboardButton(text="❓ Помощь", callback_data="help")
        ],
        [
            InlineKeyboardButton(text="😄 Случайный анекдот", callback_data="joke"),
            InlineKeyboardButton(text="🏆 Топ анекдотов", callback_data="top_jokes")
        ],
        [
            InlineKeyboardButton(text="ℹ️ О боте", callback_data="about"),
            InlineKeyboardButton(text="📊 Статистика", callback_data="stats")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_rating_keyboard(joke_id):
    keyboard = [
        [
            InlineKeyboardButton(text="👍", callback_data=f"like_{joke_id}"),
            InlineKeyboardButton(text="👎", callback_data=f"dislike_{joke_id}")
        ],
        [
            InlineKeyboardButton(text="🔙 Вернуться в меню", callback_data="back_to_menu")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

async def parse_kartaslov(session, headers):
    """Парсинг анекдотов с сайта kartaslov.ru"""
    try:
        logger.info(f"Начинаем загрузку анекдотов с kartaslov.ru")
        async with session.get(URLS['kartaslov']) as response:
            if response.status == 200:
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                logger.info("HTML с kartaslov.ru успешно получен")

                # Ищем все текстовые блоки
                content = soup.get_text()
                
                # Разделяем текст по маркеру '* * *'
                jokes = re.split(r'\*\s*\*\s*\*', content)
                
                # Фильтруем и очищаем анекдоты
                parsed_jokes = []
                for joke in jokes:
                    joke = joke.strip()
                    if len(joke) > 20 and not any(skip in joke.lower() 
                        for skip in ['меню', 'контакты', 'поиск', 'читать', 'подписка', 'каталог', 
                                   'купить', 'скачать', 'оглавление', 'автор:', 'жанры и теги']):
                        parsed_jokes.append(joke)
                
                logger.info(f"Найдено {len(parsed_jokes)} анекдотов на kartaslov.ru")
                return parsed_jokes
            else:
                logger.error(f"Ошибка при получении страницы kartaslov.ru: {response.status}")
                return []
    except Exception as e:
        logger.error(f"Ошибка при парсинге kartaslov.ru: {str(e)}", exc_info=True)
        return []

async def parse_litres(session, headers):
    """Парсинг анекдотов с сайта litres.ru"""
    try:
        logger.info(f"Начинаем загрузку анекдотов с litres.ru")
        async with session.get(URLS['litres']) as response:
            if response.status == 200:
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                logger.info("HTML с litres.ru успешно получен")
                
                content_elements = soup.find_all(['p', 'img'])
                current_joke = []
                parsed_jokes = []
                
                for element in content_elements:
                    if element.name == 'img':
                        if current_joke:
                            joke_text = '\n'.join(current_joke)
                            if len(joke_text) > 20 and not any(skip in joke_text.lower() 
                                for skip in ['меню', 'контакты', 'поиск', 'читать', 'подписка', 'каталог']):
                                parsed_jokes.append(joke_text)
                            current_joke = []
                    else:
                        text = element.get_text().strip()
                        if text:
                            current_joke.append(text)
                
                if current_joke:
                    joke_text = '\n'.join(current_joke)
                    if len(joke_text) > 20 and not any(skip in joke_text.lower() 
                        for skip in ['меню', 'контакты', 'поиск', 'читать', 'подписка', 'каталог']):
                        parsed_jokes.append(joke_text)
                
                logger.info(f"Найдено {len(parsed_jokes)} анекдотов на litres.ru")
                return parsed_jokes
            else:
                logger.error(f"Ошибка при получении страницы litres.ru: {response.status}")
                return []
    except Exception as e:
        logger.error(f"Ошибка при парсинге litres.ru: {str(e)}", exc_info=True)
        return []

async def get_random_joke():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3',
    }
    
    try:
        # Если список анекдотов пуст, загружаем их с обоих сайтов
        if not jokes_list:
            async with aiohttp.ClientSession(headers=headers) as session:
                # Параллельно загружаем анекдоты с обоих сайтов
                kartaslov_jokes, litres_jokes = await asyncio.gather(
                    parse_kartaslov(session, headers),
                    parse_litres(session, headers)
                )
                
                # Объединяем анекдоты из обоих источников
                jokes_list.extend(kartaslov_jokes)
                jokes_list.extend(litres_jokes)
                
                logger.info(f"Всего загружено анекдотов: {len(jokes_list)}")
                
                if not jokes_list:
                    logger.error("Не удалось загрузить анекдоты ни с одного источника")
                    return "Извините, не удалось найти анекдоты. Попробуйте позже.", None
        
        # Выбираем случайный анекдот из списка
        if jokes_list:
            selected_joke = random.choice(jokes_list)
            joke_id = str(hash(selected_joke))
            logger.info(f"Выбран случайный анекдот длиной {len(selected_joke)} символов")
            return selected_joke, joke_id
        else:
            logger.error("Список анекдотов пуст")
            return "Извините, не удалось загрузить анекдоты. Попробуйте позже.", None
            
    except Exception as e:
        logger.error(f"Ошибка при получении анекдота: {str(e)}", exc_info=True)
        return "Извините, произошла ошибка при получении анекдота. Попробуйте позже.", None

# Обработчик команды /start
@dp.message(Command("start"))
async def cmd_start(message: Message):
    logger.info(f"Пользователь {message.from_user.id} запустил бота")
    await message.answer(
        'Привет! Я бот с анекдотами. Выберите действие:',
        reply_markup=get_main_keyboard()
    )

# Обработчик команды /help
@dp.message(Command("help"))
async def cmd_help(message: Message):
    logger.info(f"Пользователь {message.from_user.id} запросил помощь")
    help_text = """
    Доступные команды:
    /start - Начать работу с ботом
    /help - Показать это сообщение
    /joke - Получить случайный анекдот
    
    Используйте кнопки для:
    👍/👎 - Оценить анекдот
    🏆 - Посмотреть топ анекдотов
    📊 - Посмотреть статистику
    """
    await message.answer(help_text, reply_markup=get_main_keyboard())

# Обработчик команды /joke
@dp.message(Command("joke"))
async def cmd_joke(message: Message):
    logger.info(f"Пользователь {message.from_user.id} запросил анекдот")
    await message.answer("Получаю анекдот...")
    joke, joke_id = await get_random_joke()
    if joke_id:
        user_history[message.from_user.id].append(joke_id)
        await message.answer(joke, reply_markup=get_rating_keyboard(joke_id))
    else:
        await message.answer(joke, reply_markup=get_main_keyboard())

# Обработчики callback-запросов от инлайн кнопок
@dp.callback_query()
async def process_callback(callback: CallbackQuery):
    logger.info(f"Пользователь {callback.from_user.id} нажал кнопку {callback.data}")
    
    if callback.data.startswith("like_") or callback.data.startswith("dislike_"):
        joke_id = callback.data.split("_")[1]
        action = "like" if callback.data.startswith("like_") else "dislike"
        
        if action == "like":
            joke_ratings[joke_id]['likes'] += 1
            message = "👍 Спасибо за оценку!"
        else:
            joke_ratings[joke_id]['dislikes'] += 1
            message = "👎 Спасибо за оценку!"
        
        await save_ratings()
        await callback.answer(message)
        
        # Автоматически показываем следующий анекдот
        joke, new_joke_id = await get_random_joke()
        if new_joke_id:
            user_history[callback.from_user.id].append(new_joke_id)
            await callback.message.answer(joke, reply_markup=get_rating_keyboard(new_joke_id))
        return

    if callback.data == "back_to_menu":
        await callback.message.answer("Вы вернулись в главное меню!", reply_markup=get_main_keyboard())
        return

    if callback.data == "top_jokes":
        # Получаем топ-5 анекдотов по рейтингу
        sorted_jokes = sorted(
            [(joke_id, data['likes'] - data['dislikes']) 
             for joke_id, data in joke_ratings.items()],
            key=lambda x: x[1],
            reverse=True
        )[:5]
        
        if sorted_jokes:
            response = "🏆 Топ-5 анекдотов по рейтингу:\n\n"
            for i, (joke_id, rating) in enumerate(sorted_jokes, 1):
                for joke in jokes_list:
                    if str(hash(joke)) == joke_id:
                        response += f"{i}. {joke}\n"
                        response += f"Рейтинг: {rating} (👍 {joke_ratings[joke_id]['likes']} | 👎 {joke_ratings[joke_id]['dislikes']})\n\n"
                        break
        else:
            response = "Пока нет оцененных анекдотов!"
        
        await callback.message.answer(response, reply_markup=get_main_keyboard())
        return

    if callback.data == "stats":
        total_jokes = len(jokes_list)
        total_ratings = sum(len(ratings) for ratings in joke_ratings.values())
        user_rated = len(set(user_id for user_id in user_history.keys()))
        
        stats = (
            "📊 Статистика бота:\n\n"
            f"Всего анекдотов: {total_jokes}\n"
            f"Всего оценок: {total_ratings}\n"
            f"Пользователей оценило: {user_rated}\n"
        )
        await callback.message.answer(stats, reply_markup=get_main_keyboard())
        return

    # Остальные обработчики
    if callback.data == "greeting":
        await callback.message.answer("Привет! Рад вас видеть! 👋", reply_markup=get_main_keyboard())
    elif callback.data == "help":
        help_text = """
        Доступные команды:
        /start - Начать работу с ботом
        /help - Показать это сообщение
        /joke - Получить случайный анекдот
        
        Используйте кнопки для:
        👍/👎 - Оценить анекдот
        🏆 - Посмотреть топ анекдотов
        📊 - Посмотреть статистику
        """
        await callback.message.answer(help_text, reply_markup=get_main_keyboard())
    elif callback.data == "joke":
        await callback.message.answer("Получаю анекдот...")
        joke, joke_id = await get_random_joke()
        if joke_id:
            user_history[callback.from_user.id].append(joke_id)
            await callback.message.answer(joke, reply_markup=get_rating_keyboard(joke_id))
        else:
            await callback.message.answer(joke, reply_markup=get_main_keyboard())
    elif callback.data == "about":
        await callback.message.answer(
            "🤖 Я бот с анекдотами, созданный с помощью библиотеки aiogram.\n"
            "Мой код написан на Python и использует современные практики асинхронного программирования.\n\n"
            "Функции:\n"
            "- Случайные анекдоты\n"
            "- Система оценок\n"
            "- Топ анекдотов\n"
            "- Статистика использования",
            reply_markup=get_main_keyboard()
        )
    
    await callback.answer()

async def main():
    logger.info("Запуск бота...")
    await load_ratings()
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
