import asyncio
import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Optional
import json

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = "8432058073:AAEpfLO6qBUq4jqQIFCnlpcrJxpo6-HavH0"  # ← Вставьте сюда токен от @BotFather
ADMIN_ID = 8338991808  # ← Вставьте ваш Telegram ID (узнать у @userinfobot)
# ===============================

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# ========== БАЗА ДАННЫХ ==========
class Database:
    def __init__(self, db_path='bot.db'):
        self.db_path = db_path
        self.init_db()

    def init_db(self):
        """Инициализация базы данных"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Пользователи
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                full_name TEXT NOT NULL,
                role TEXT DEFAULT 'user',
                total_requests INTEGER DEFAULT 0,
                total_amount REAL DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Тарифы
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tariffs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                price REAL NOT NULL,
                duration_minutes INTEGER NOT NULL,
                description TEXT,
                is_active BOOLEAN DEFAULT 1,
                sort_order INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Заявки
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                tariff_id INTEGER NOT NULL,
                phone_number TEXT NOT NULL,
                status TEXT DEFAULT 'pending',  -- pending, accepted, rejected, archived
                admin_comment TEXT,
                rejection_reason TEXT,
                photo_file_id TEXT,
                processed_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                processed_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (tariff_id) REFERENCES tariffs(id)
            )
        ''')

        # Логи действий
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT NOT NULL,
                details TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Добавляем тестовые тарифы если их нет
        cursor.execute("SELECT COUNT(*) FROM tariffs")
        if cursor.fetchone()[0] == 0:
            test_tariffs = [
                ('Стандарт', 5.0, 25, 'Стандартный тариф', 1, 0),
                ('Премиум', 7.0, 25, 'Премиум тариф', 1, 1),
                ('VIP', 10.0, 50, 'VIP тариф', 1, 2),
                ('Бизнес', 15.0, 100, 'Бизнес тариф', 1, 3)
            ]
            cursor.executemany(
                "INSERT INTO tariffs (name, price, duration_minutes, description, is_active, sort_order) VALUES (?, ?, ?, ?, ?, ?)",
                test_tariffs
            )

        # Добавляем администратора если его нет
        cursor.execute("SELECT id FROM users WHERE telegram_id = ?", (ADMIN_ID,))
        if not cursor.fetchone():
            cursor.execute(
                "INSERT INTO users (telegram_id, username, full_name, role) VALUES (?, ?, ?, 'owner')",
                (ADMIN_ID, 'admin', 'Администратор')
            )

        conn.commit()
        conn.close()
        logger.info("База данных инициализирована")

    def get_connection(self):
        """Получить соединение с БД"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def add_log(self, user_id: int, action: str, details: str = None):
        """Добавить запись в лог"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO logs (user_id, action, details) VALUES (?, ?, ?)",
            (user_id, action, details)
        )
        conn.commit()
        conn.close()

    def get_user(self, telegram_id: int):
        """Получить пользователя"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
        user = cursor.fetchone()
        conn.close()
        return user

    def create_user(self, telegram_id: int, username: str, full_name: str):
        """Создать пользователя"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (telegram_id, username, full_name) VALUES (?, ?, ?)",
            (telegram_id, username, full_name)
        )
        user_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return user_id

    def get_active_tariffs(self):
        """Получить активные тарифы"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM tariffs WHERE is_active = 1 ORDER BY sort_order, price"
        )
        tariffs = cursor.fetchall()
        conn.close()
        return tariffs

    def get_all_tariffs(self):
        """Получить все тарифы"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tariffs ORDER BY sort_order, price")
        tariffs = cursor.fetchall()
        conn.close()
        return tariffs

    def get_tariff(self, tariff_id: int):
        """Получить тариф по ID"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tariffs WHERE id = ?", (tariff_id,))
        tariff = cursor.fetchone()
        conn.close()
        return tariff

    def create_request(self, user_id: int, tariff_id: int, phone_number: str):
        """Создать заявку"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO requests 
               (user_id, tariff_id, phone_number, status) 
               VALUES (?, ?, ?, 'pending')""",
            (user_id, tariff_id, phone_number)
        )
        request_id = cursor.lastrowid

        # Обновляем статистику пользователя
        cursor.execute(
            "UPDATE users SET total_requests = total_requests + 1 WHERE id = ?",
            (user_id,)
        )

        conn.commit()
        conn.close()
        return request_id

    def get_pending_requests(self, limit: int = 50):
        """Получить заявки в очереди"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT r.*, u.telegram_id, u.full_name, t.name as tariff_name, t.price
            FROM requests r
            JOIN users u ON r.user_id = u.id
            JOIN tariffs t ON r.tariff_id = t.id
            WHERE r.status = 'pending'
            ORDER BY r.created_at ASC
            LIMIT ?
        ''', (limit,))
        requests = cursor.fetchall()
        conn.close()
        return requests

    def get_accepted_requests(self, limit: int = 50):
        """Получить принятые заявки"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT r.*, u.telegram_id, u.full_name, t.name as tariff_name, t.price
            FROM requests r
            JOIN users u ON r.user_id = u.id
            JOIN tariffs t ON r.tariff_id = t.id
            WHERE r.status = 'accepted'
            ORDER BY r.created_at DESC
            LIMIT ?
        ''', (limit,))
        requests = cursor.fetchall()
        conn.close()
        return requests

    def get_rejected_requests(self, limit: int = 50):
        """Получить отклоненные заявки"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT r.*, u.telegram_id, u.full_name, t.name as tariff_name, t.price, r.rejection_reason
            FROM requests r
            JOIN users u ON r.user_id = u.id
            JOIN tariffs t ON r.tariff_id = t.id
            WHERE r.status = 'rejected'
            ORDER BY r.created_at DESC
            LIMIT ?
        ''', (limit,))
        requests = cursor.fetchall()
        conn.close()
        return requests

    def update_request_status(self, request_id: int, status: str, admin_id: int,
                              comment: str = None, reason: str = None, photo: str = None):
        """Обновить статус заявки"""
        conn = self.get_connection()
        cursor = conn.cursor()

        # Получаем данные заявки для обновления статистики
        cursor.execute(
            "SELECT user_id, tariff_id FROM requests WHERE id = ?",
            (request_id,)
        )
        request_data = cursor.fetchone()

        if status == 'accepted' and request_data:
            # Обновляем статистику пользователя
            tariff = self.get_tariff(request_data['tariff_id'])
            if tariff:
                cursor.execute('''
                    UPDATE users 
                    SET total_amount = total_amount + ? 
                    WHERE id = ?
                ''', (tariff['price'], request_data['user_id']))

        # Обновляем заявку
        cursor.execute('''
            UPDATE requests 
            SET status = ?, 
                processed_by = ?, 
                admin_comment = ?, 
                rejection_reason = ?,
                photo_file_id = ?,
                processed_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (status, admin_id, comment, reason, photo, request_id))

        conn.commit()
        conn.close()

    def get_request(self, request_id: int):
        """Получить заявку по ID"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT r.*, u.telegram_id, u.full_name, t.name as tariff_name, t.price, t.duration_minutes
            FROM requests r
            JOIN users u ON r.user_id = u.id
            JOIN tariffs t ON r.tariff_id = t.id
            WHERE r.id = ?
        ''', (request_id,))
        request = cursor.fetchone()
        conn.close()
        return request

    def get_user_requests(self, telegram_id: int, status: str = None, limit: int = 20):
        """Получить заявки пользователя"""
        conn = self.get_connection()
        cursor = conn.cursor()

        if status:
            cursor.execute('''
                SELECT r.*, t.name as tariff_name, t.price
                FROM requests r
                JOIN users u ON r.user_id = u.id
                JOIN tariffs t ON r.tariff_id = t.id
                WHERE u.telegram_id = ? AND r.status = ?
                ORDER BY r.created_at DESC
                LIMIT ?
            ''', (telegram_id, status, limit))
        else:
            cursor.execute('''
                SELECT r.*, t.name as tariff_name, t.price
                FROM requests r
                JOIN users u ON r.user_id = u.id
                JOIN tariffs t ON r.tariff_id = t.id
                WHERE u.telegram_id = ?
                ORDER BY r.created_at DESC
                LIMIT ?
            ''', (telegram_id, limit))

        requests = cursor.fetchall()
        conn.close()
        return requests

    def get_statistics(self, days: int = 1):
        """Получить статистику за указанное количество дней"""
        conn = self.get_connection()
        cursor = conn.cursor()

        # Общая статистика
        cursor.execute('''
            SELECT 
                COUNT(*) as total_requests,
                SUM(CASE WHEN status = 'accepted' THEN 1 ELSE 0 END) as accepted,
                SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) as rejected,
                SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
                SUM(CASE WHEN status = 'accepted' THEN t.price ELSE 0 END) as total_amount
            FROM requests r
            JOIN tariffs t ON r.tariff_id = t.id
            WHERE date(r.created_at) >= date('now', ?)
        ''', (f'-{days} days',))

        stats = cursor.fetchone()

        # Статистика по тарифам
        cursor.execute('''
            SELECT t.name, COUNT(r.id) as count
            FROM requests r
            JOIN tariffs t ON r.tariff_id = t.id
            WHERE date(r.created_at) >= date('now', ?)
            GROUP BY t.id
            ORDER BY count DESC
            LIMIT 5
        ''', (f'-{days} days',))

        tariff_stats = cursor.fetchall()

        # Статистика по времени
        cursor.execute('''
            SELECT strftime('%H', created_at) as hour, COUNT(*) as count
            FROM requests
            WHERE date(created_at) >= date('now', ?)
            GROUP BY strftime('%H', created_at)
            ORDER BY hour
        ''', (f'-{days} days',))

        time_stats = cursor.fetchall()

        conn.close()

        return {
            'total_requests': stats['total_requests'] or 0,
            'accepted': stats['accepted'] or 0,
            'rejected': stats['rejected'] or 0,
            'pending': stats['pending'] or 0,
            'total_amount': stats['total_amount'] or 0.0,
            'tariff_stats': [dict(row) for row in tariff_stats],
            'time_stats': [dict(row) for row in time_stats]
        }

    def add_tariff(self, name: str, price: float, minutes: int, description: str = ''):
        """Добавить новый тариф"""
        conn = self.get_connection()
        cursor = conn.cursor()

        # Получаем максимальный порядок
        cursor.execute("SELECT MAX(sort_order) as max_order FROM tariffs")
        max_order = cursor.fetchone()['max_order'] or 0

        cursor.execute('''
            INSERT INTO tariffs (name, price, duration_minutes, description, is_active, sort_order)
            VALUES (?, ?, ?, ?, 1, ?)
        ''', (name, price, minutes, description, max_order + 1))

        tariff_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return tariff_id

    def update_tariff(self, tariff_id: int, name: str = None, price: float = None,
                      minutes: int = None, description: str = None, is_active: bool = None):
        """Обновить тариф"""
        conn = self.get_connection()
        cursor = conn.cursor()

        updates = []
        params = []

        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if price is not None:
            updates.append("price = ?")
            params.append(price)
        if minutes is not None:
            updates.append("duration_minutes = ?")
            params.append(minutes)
        if description is not None:
            updates.append("description = ?")
            params.append(description)
        if is_active is not None:
            updates.append("is_active = ?")
            params.append(1 if is_active else 0)

        if updates:
            params.append(tariff_id)
            query = f"UPDATE tariffs SET {', '.join(updates)} WHERE id = ?"
            cursor.execute(query, params)

        conn.commit()
        conn.close()

    def delete_tariff(self, tariff_id: int):
        """Удалить тариф"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM tariffs WHERE id = ?", (tariff_id,))
        conn.commit()
        conn.close()

    def get_logs(self, days: int = 1, limit: int = 100):
        """Получить логи за указанное количество дней"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT l.*, u.full_name, u.telegram_id
            FROM logs l
            LEFT JOIN users u ON l.user_id = u.id
            WHERE date(l.created_at) >= date('now', ?)
            ORDER BY l.created_at DESC
            LIMIT ?
        ''', (f'-{days} days', limit))
        logs = cursor.fetchall()
        conn.close()
        return logs


# ========== СОЗДАЕМ БАЗУ ДАННЫХ ==========
db = Database()

# ========== БОТ ==========
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder


class UserStates(StatesGroup):
    """Состояния пользователя"""
    waiting_phone = State()
    waiting_tariff_choice = State()


class AdminStates(StatesGroup):
    """Состояния администратора"""
    waiting_photo = State()
    editing_tariff = State()
    adding_tariff_name = State()
    adding_tariff_price = State()
    adding_tariff_minutes = State()


# Глобальные переменные для хранения состояния
user_data = {}
pending_requests = {}


async def main():
    """Основная функция"""
    # Проверяем токен
    if not BOT_TOKEN or "ВАШ_ТОКЕН" in BOT_TOKEN:
        print("\n" + "=" * 60)
        print("❌ ТОКЕН БОТА НЕ УСТАНОВЛЕН!")
        print("=" * 60)
        print("\n1. Откройте файл и найдите строку:")
        print("   BOT_TOKEN = \"ВАШ_ТОКЕН\"")
        print("\n2. Замените на свой токен от @BotFather")
        print("\nПример токена: 6123456789:AAHjrR9jX8fR5g8fJkLmNoPqRsTuvWxyZab")
        print("\n3. Также установите свой Telegram ID:")
        print("   ADMIN_ID = 123456789")
        print("\nКак узнать ID: напишите @userinfobot в Telegram")
        print("=" * 60)
        return

    try:
        # Создаем бота
        bot = Bot(token=BOT_TOKEN)
        storage = MemoryStorage()
        dp = Dispatcher(storage=storage)

        logger.info(f"Бот запущен! Администратор: {ADMIN_ID}")

        # ========== КОМАНДА /start ==========
        @dp.message(CommandStart())
        async def start_command(message: types.Message):
            """Команда /start"""
            user = db.get_user(message.from_user.id)

            if not user:
                user_id = db.create_user(
                    message.from_user.id,
                    message.from_user.username,
                    message.from_user.full_name or "Пользователь"
                )
                db.add_log(user_id, "user_registered", f"Новый пользователь: {message.from_user.full_name}")

            # Главное меню
            keyboard = ReplyKeyboardBuilder()
            keyboard.button(text="📱 Сдать номер")
            keyboard.button(text="📊 Очередь")
            keyboard.button(text="🗃️ Архив")
            keyboard.button(text="🍽️ Обеды")
            keyboard.button(text="👤 Профиль")

            if message.from_user.id == ADMIN_ID:
                keyboard.button(text="⚙️ Админ-панель")

            keyboard.adjust(2, 2, 1)

            await message.answer(
                f"👋 <b>Добро пожаловать, {message.from_user.first_name}!</b>\n\n"
                "Я бот для работы с WhatsApp номерами.\n"
                "Выберите действие в меню ниже:",
                reply_markup=keyboard.as_markup(resize_keyboard=True),
                parse_mode=ParseMode.HTML
            )

        # ========== СДАТЬ НОМЕР ==========
        @dp.message(F.text == "📱 Сдать номер")
        async def submit_number(message: types.Message, state: FSMContext):
            """Начать процесс сдачи номера"""
            tariffs = db.get_active_tariffs()

            if not tariffs:
                await message.answer("❌ На данный момент нет доступных тарифов.")
                return

            builder = InlineKeyboardBuilder()

            for tariff in tariffs:
                builder.button(
                    text=f"{tariff['name']} - {tariff['price']}$/{tariff['duration_minutes']}мин",
                    callback_data=f"tariff_{tariff['id']}"
                )

            builder.button(text="❌ Отмена", callback_data="cancel")
            builder.adjust(1)

            # Форматируем список тарифов
            tariffs_text = "\n".join([
                f"• <b>{t['name']}</b> - {t['price']}$/{t['duration_minutes']} мин"
                + (f"\n  <i>{t['description']}</i>" if t['description'] else "")
                for t in tariffs
            ])

            await message.answer(
                f"📋 <b>Выберите тариф:</b>\n\n{tariffs_text}",
                reply_markup=builder.as_markup(),
                parse_mode=ParseMode.HTML
            )

            await state.set_state(UserStates.waiting_tariff_choice)

        # ========== ВЫБОР ТАРИФА ==========
        @dp.callback_query(F.data.startswith("tariff_"))
        async def process_tariff(callback: types.CallbackQuery, state: FSMContext):
            """Обработка выбора тарифа"""
            tariff_id = int(callback.data.split("_")[1])
            tariff = db.get_tariff(tariff_id)

            if not tariff:
                await callback.message.edit_text("❌ Тариф не найден.")
                await callback.answer()
                return

            # Сохраняем выбор тарифа
            await state.update_data(tariff_id=tariff_id, tariff_name=tariff['name'])

            await callback.message.edit_text(
                f"✅ Выбран тариф: <b>{tariff['name']}</b>\n"
                f"💰 Цена: <b>{tariff['price']}$</b>\n"
                f"⏱ Время: <b>{tariff['duration_minutes']} минут</b>\n\n"
                f"📱 Теперь отправьте номер телефона в формате:\n"
                f"<code>+79991234567</code> или <code>89991234567</code>",
                parse_mode=ParseMode.HTML
            )

            await state.set_state(UserStates.waiting_phone)
            await callback.answer()

        # ========== ОБРАБОТКА НОМЕРА ТЕЛЕФОНА ==========
        @dp.message(UserStates.waiting_phone)
        async def process_phone_number(message: types.Message, state: FSMContext):
            """Обработка номера телефона"""
            phone = message.text.strip()

            # Валидация номера
            clean_phone = phone.replace('+7', '8').replace(' ', '').replace('-', '')
            if not clean_phone.isdigit() or len(clean_phone) != 11 or not clean_phone.startswith('8'):
                await message.answer(
                    "❌ Неверный формат номера!\n\n"
                    "Номер должен быть в формате:\n"
                    "<code>+79991234567</code> или <code>89991234567</code>\n\n"
                    "Попробуйте еще раз:"
                )
                return

            # Получаем данные из состояния
            data = await state.get_data()
            tariff_id = data['tariff_id']

            # Получаем пользователя
            user = db.get_user(message.from_user.id)
            if not user:
                await message.answer("❌ Ошибка. Напишите /start")
                await state.clear()
                return

            # Создаем заявку
            request_id = db.create_request(user['id'], tariff_id, phone)

            # Форматируем номер
            formatted_phone = f"+7{clean_phone[1:]}"

            # Получаем информацию о тарифе
            tariff = db.get_tariff(tariff_id)

            # Логируем
            db.add_log(user['id'], "request_created", f"Заявка #{request_id} создана")

            # Отправляем уведомление администратору
            admin_keyboard = InlineKeyboardBuilder()
            admin_keyboard.button(text="✅ Принять", callback_data=f"accept_{request_id}")
            admin_keyboard.button(text="❌ Ошибка", callback_data=f"reject_{request_id}")
            admin_keyboard.adjust(2)

            try:
                await bot.send_message(
                    ADMIN_ID,
                    f"🆕 <b>НОВАЯ ЗАЯВКА #{request_id}</b>\n\n"
                    f"👤 <b>Пользователь:</b> {message.from_user.full_name}\n"
                    f"📱 <b>Номер:</b> <code>{formatted_phone}</code>\n"
                    f"💰 <b>Тариф:</b> {tariff['name']} - {tariff['price']}$/{tariff['duration_minutes']}мин\n"
                    f"🆔 <b>ID:</b> <code>{message.from_user.id}</code>\n"
                    f"⏰ <b>Время:</b> {datetime.now().strftime('%H:%M %d.%m.%Y')}",
                    reply_markup=admin_keyboard.as_markup(),
                    parse_mode=ParseMode.HTML
                )
            except Exception as e:
                logger.error(f"Не удалось отправить уведомление админу: {e}")

            await message.answer(
                f"✅ <b>Заявка #{request_id} отправлена!</b>\n\n"
                f"📱 Номер: <code>{formatted_phone}</code>\n"
                f"💰 Тариф: {tariff['name']} - {tariff['price']}$\n"
                f"⏱ Время: {tariff['duration_minutes']} минут\n\n"
                f"Ожидайте обработки. Статус можно отслеживать в «📊 Очередь».",
                parse_mode=ParseMode.HTML
            )

            await state.clear()

        # ========== ОЧЕРЕДЬ ==========
        @dp.message(F.text == "📊 Очередь")
        async def show_queue(message: types.Message):
            """Показать очередь заявок пользователя"""
            requests = db.get_user_requests(message.from_user.id, 'pending')

            if not requests:
                await message.answer("📭 У вас нет заявок в очереди.")
                return

            text = "📊 <b>Ваши заявки в очереди:</b>\n\n"
            for req in requests[:10]:  # Показываем первые 10
                created_time = datetime.strptime(req['created_at'], '%Y-%m-%d %H:%M:%S')
                wait_time = datetime.now() - created_time
                wait_minutes = int(wait_time.total_seconds() / 60)

                text += f"🔸 <b>Заявка #{req['id']}</b>\n"
                text += f"   📱: <code>{req['phone_number']}</code>\n"
                text += f"   💰: {req['tariff_name']} - {req['price']}$\n"
                text += f"   ⏰: {created_time.strftime('%H:%M %d.%m')}\n"
                text += f"   ⏳: {wait_minutes} мин. назад\n\n"

            if len(requests) > 10:
                text += f"\n... и еще {len(requests) - 10} заявок"

            await message.answer(text, parse_mode=ParseMode.HTML)

        # ========== АРХИВ ==========
        @dp.message(F.text == "🗃️ Архив")
        async def show_archive(message: types.Message):
            """Показать архив заявок"""
            requests = db.get_user_requests(message.from_user.id)

            if not requests:
                await message.answer("🗃️ Архив пуст.")
                return

            text = "🗃️ <b>Архив заявок:</b>\n\n"

            for req in requests[:15]:  # Показываем первые 15
                status_icon = {
                    'accepted': '✅',
                    'rejected': '❌',
                    'pending': '⏳',
                    'archived': '📁'
                }.get(req['status'], '❓')

                created_time = datetime.strptime(req['created_at'], '%Y-%m-%d %H:%M:%S')

                text += f"{status_icon} <b>Заявка #{req['id']}</b>\n"
                text += f"   📱: <code>{req['phone_number']}</code>\n"
                text += f"   💰: {req['tariff_name']} - {req['price']}$\n"
                text += f"   ⏰: {created_time.strftime('%H:%M %d.%m')}\n"

                if req['status'] == 'rejected' and req['rejection_reason']:
                    text += f"   ❌ Причина: {req['rejection_reason']}\n"

                text += "\n"

            if len(requests) > 15:
                text += f"\n... всего {len(requests)} заявок"

            await message.answer(text, parse_mode=ParseMode.HTML)

        # ========== ПРОФИЛЬ ==========
        @dp.message(F.text == "👤 Профиль")
        async def show_profile(message: types.Message):
            """Показать профиль пользователя"""
            user = db.get_user(message.from_user.id)

            if not user:
                await message.answer("❌ Пользователь не найден. Напишите /start")
                return

            # Получаем статистику
            requests = db.get_user_requests(message.from_user.id)
            total = len(requests)
            accepted = sum(1 for r in requests if r['status'] == 'accepted')

            role_names = {
                'user': '👤 Пользователь',
                'moderator': '🛡 Модератор',
                'admin': '⚙️ Администратор',
                'owner': '👑 Владелец'
            }

            await message.answer(
                f"👤 <b>Ваш профиль</b>\n\n"
                f"🆔 ID: <code>{user['telegram_id']}</code>\n"
                f"📛 Имя: {user['full_name']}\n"
                f"👤 Username: @{user['username'] or 'не установлен'}\n"
                f"🎖️ Роль: {role_names.get(user['role'], user['role'])}\n\n"
                f"📊 <b>Статистика:</b>\n"
                f"• Всего заявок: {user['total_requests']}\n"
                f"• Принято: {accepted}\n"
                f"• Сумма: {user['total_amount']:.2f}$\n\n"
                f"📅 Регистрация: {user['created_at'][:10]}",
                parse_mode=ParseMode.HTML
            )

        # ========== ОБЕДЫ ==========
        @dp.message(F.text == "🍽️ Обеды")
        async def show_schedule(message: types.Message):
            """Показать расписание"""
            await message.answer(
                "🍽️ <b>Расписание обедов и перерывов</b>\n\n"
                "🕐 <b>Обед:</b> 13:00 - 14:00\n"
                "☕ <b>Перерывы:</b> каждый час по 5 минут\n"
                "🔄 <b>Технические перерывы:</b> по необходимости\n\n"
                "<i>Во время обедов и перерывов обработка заявок приостанавливается.</i>",
                parse_mode=ParseMode.HTML
            )

        # ========== АДМИН ПАНЕЛЬ ==========
        @dp.message(F.text == "⚙️ Админ-панель")
        @dp.message(Command("admin"))
        async def admin_panel(message: types.Message):
            """Админ-панель"""
            if message.from_user.id != ADMIN_ID:
                await message.answer("❌ У вас нет доступа к админ-панели.")
                return

            # Создаем клавиатуру админ-панели
            builder = ReplyKeyboardBuilder()
            builder.button(text="📋 Заявки в очереди")
            builder.button(text="✅ Принятые заявки")
            builder.button(text="❌ Отклоненные заявки")
            builder.button(text="💰 Управление тарифами")
            builder.button(text="📊 Статистика")
            builder.button(text="📝 Логи системы")
            builder.button(text="◀️ Главное меню")
            builder.adjust(2, 2, 2, 1)

            await message.answer(
                "⚙️ <b>Админ-панель</b>\n\n"
                "Выберите раздел:",
                reply_markup=builder.as_markup(resize_keyboard=True),
                parse_mode=ParseMode.HTML
            )

            db.add_log(ADMIN_ID, "admin_panel_opened")

        # ========== НАЗАД В ГЛАВНОЕ МЕНЮ ==========
        @dp.message(F.text == "◀️ Главное меню")
        async def back_to_main(message: types.Message):
            """Вернуться в главное меню"""
            await start_command(message)

        # ========== ОБРАБОТКА ЗАЯВОК АДМИНОМ ==========
        @dp.callback_query(F.data.startswith("accept_"))
        async def accept_request(callback: types.CallbackQuery, state: FSMContext):
            """Принять заявку"""
            if callback.from_user.id != ADMIN_ID:
                await callback.answer("❌ Нет доступа!")
                return

            request_id = int(callback.data.split("_")[1])
            request = db.get_request(request_id)

            if not request:
                await callback.message.edit_text("❌ Заявка не найдена.")
                await callback.answer()
                return

            # Сохраняем ID заявки для следующего шага
            await state.update_data(request_id=request_id)

            await callback.message.edit_text(
                f"✅ Заявка #{request_id} принята!\n\n"
                f"Теперь отправьте фото для этого номера:"
            )

            await state.set_state(AdminStates.waiting_photo)
            await callback.answer()

            db.add_log(ADMIN_ID, "request_accepted", f"Заявка #{request_id} принята")

        @dp.callback_query(F.data.startswith("reject_"))
        async def reject_request(callback: types.CallbackQuery):
            """Отклонить заявку"""
            if callback.from_user.id != ADMIN_ID:
                await callback.answer("❌ Нет доступа!")
                return

            request_id = int(callback.data.split("_")[1])
            request = db.get_request(request_id)

            if not request:
                await callback.message.edit_text("❌ Заявка не найдена.")
                await callback.answer()
                return

            # Создаем клавиатуру с причинами
            builder = InlineKeyboardBuilder()
            reasons = [
                ("Неверный формат номера", "wrong_format"),
                ("Номер уже использован", "number_used"),
                ("Тариф недоступен", "tariff_unavailable"),
                ("Другая причина", "other")
            ]

            for reason_text, reason_code in reasons:
                builder.button(text=reason_text, callback_data=f"reason_{request_id}_{reason_code}")

            builder.button(text="◀️ Назад", callback_data=f"back_{request_id}")
            builder.adjust(1)

            await callback.message.edit_text(
                f"❌ Отклонение заявки #{request_id}\n\n"
                f"📱 Номер: <code>{request['phone_number']}</code>\n"
                f"👤 Пользователь: {request['full_name']}\n\n"
                f"Выберите причину отклонения:",
                reply_markup=builder.as_markup(),
                parse_mode=ParseMode.HTML
            )

            await callback.answer()

        @dp.callback_query(F.data.startswith("reason_"))
        async def process_rejection_reason(callback: types.CallbackQuery):
            """Обработка выбора причины"""
            if callback.from_user.id != ADMIN_ID:
                await callback.answer("❌ Нет доступа!")
                return

            _, request_id, reason_code = callback.data.split("_")
            request_id = int(request_id)
            request = db.get_request(request_id)

            if not request:
                await callback.message.edit_text("❌ Заявка не найдена.")
                await callback.answer()
                return

            if reason_code == "other":
                # Запрашиваем текст причины
                await callback.message.edit_text(
                    "✍️ Введите причину отклонения заявки:"
                )
                pending_requests[callback.from_user.id] = {
                    'request_id': request_id,
                    'action': 'reject'
                }
            else:
                # Используем стандартную причину
                reason_texts = {
                    'wrong_format': "❌ Неверный формат номера",
                    'number_used': "📵 Номер уже использован",
                    'tariff_unavailable': "💰 Тариф недоступен"
                }
                reason = reason_texts.get(reason_code, reason_code)

                # Обновляем статус заявки
                db.update_request_status(
                    request_id, 'rejected', callback.from_user.id,
                    reason=reason
                )

                # Уведомляем пользователя
                try:
                    user = db.get_user(request['telegram_id'])
                    if user:
                        await bot.send_message(
                            user['telegram_id'],
                            f"❌ <b>Ваша заявка #{request_id} отклонена</b>\n\n"
                            f"📱 Номер: <code>{request['phone_number']}</code>\n"
                            f"💰 Тариф: {request['tariff_name']}\n\n"
                            f"<b>Причина:</b> {reason}\n\n"
                            f"Проверьте данные и попробуйте снова.",
                            parse_mode=ParseMode.HTML
                        )
                except Exception as e:
                    logger.error(f"Не удалось уведомить пользователя: {e}")

                await callback.message.edit_text(
                    f"❌ Заявка #{request_id} отклонена!\n\n"
                    f"Причина: {reason}"
                )

                db.add_log(ADMIN_ID, "request_rejected", f"Заявка #{request_id} отклонена: {reason}")

            await callback.answer()

        @dp.message(AdminStates.waiting_photo)
        async def process_photo_for_request(message: types.Message, state: FSMContext):
            """Обработка фото для принятой заявки"""
            if message.from_user.id != ADMIN_ID:
                await message.answer("❌ Нет доступа!")
                return

            if not message.photo:
                await message.answer("❌ Пожалуйста, отправьте фото.")
                return

            data = await state.get_data()
            request_id = data['request_id']
            request = db.get_request(request_id)

            if not request:
                await message.answer("❌ Заявка не найдена!")
                await state.clear()
                return

            # Сохраняем фото и обновляем статус
            photo_id = message.photo[-1].file_id
            db.update_request_status(
                request_id, 'accepted', message.from_user.id,
                photo=photo_id
            )

            # Отправляем фото пользователю
            try:
                user = db.get_user(request['telegram_id'])
                if user:
                    await bot.send_photo(
                        user['telegram_id'],
                        photo=photo_id,
                        caption=(
                            f"✅ <b>Ваша заявка #{request_id} принята!</b>\n\n"
                            f"📱 Номер: <code>{request['phone_number']}</code>\n"
                            f"💰 Тариф: {request['tariff_name']} - {request['price']}$\n"
                            f"⏱ Время: {request['duration_minutes']} минут\n\n"
                            f"Фото прикреплено выше."
                        ),
                        parse_mode=ParseMode.HTML
                    )
            except Exception as e:
                logger.error(f"Не удалось отправить фото пользователю: {e}")
                await message.answer(f"✅ Заявка принята, но не удалось отправить фото пользователю: {e}")
            else:
                await message.answer(f"✅ Фото отправлено пользователю!")

            await state.clear()
            db.add_log(ADMIN_ID, "photo_sent", f"Фото отправлено для заявки #{request_id}")

        # ========== ПРОСМОТР ОЧЕРЕДИ АДМИНОМ ==========
        @dp.message(F.text == "📋 Заявки в очереди")
        async def admin_view_queue(message: types.Message):
            """Просмотр очереди заявок админом"""
            if message.from_user.id != ADMIN_ID:
                await message.answer("❌ Нет доступа!")
                return

            requests = db.get_pending_requests(limit=20)

            if not requests:
                await message.answer("📭 Очередь пуста.")
                return

            text = "📋 <b>Заявки в очереди:</b>\n\n"

            for req in requests:
                created_time = datetime.strptime(req['created_at'], '%Y-%m-%d %H:%M:%S')
                wait_time = datetime.now() - created_time
                wait_minutes = int(wait_time.total_seconds() / 60)

                text += f"🔸 <b>Заявка #{req['id']}</b>\n"
                text += f"   👤: {req['full_name']}\n"
                text += f"   📱: <code>{req['phone_number']}</code>\n"
                text += f"   💰: {req['tariff_name']} - {req['price']}$\n"
                text += f"   ⏰: {created_time.strftime('%H:%M %d.%m')}\n"
                text += f"   ⏳: {wait_minutes} мин. назад\n\n"

            await message.answer(text, parse_mode=ParseMode.HTML)
            db.add_log(ADMIN_ID, "viewed_queue", f"Просмотрено {len(requests)} заявок")

        # ========== ПРИНЯТЫЕ ЗАЯВКИ АДМИНОМ ==========
        @dp.message(F.text == "✅ Принятые заявки")
        async def admin_view_accepted(message: types.Message):
            """Просмотр принятых заявок админом"""
            if message.from_user.id != ADMIN_ID:
                await message.answer("❌ Нет доступа!")
                return

            requests = db.get_accepted_requests(limit=20)

            if not requests:
                await message.answer("📭 Нет принятых заявок.")
                return

            text = "✅ <b>Принятые заявки:</b>\n\n"
            total_amount = 0

            for req in requests:
                created_time = datetime.strptime(req['created_at'], '%Y-%m-%d %H:%M:%S')
                text += f"🔸 <b>Заявка #{req['id']}</b>\n"
                text += f"   👤: {req['full_name']}\n"
                text += f"   📱: <code>{req['phone_number']}</code>\n"
                text += f"   💰: {req['tariff_name']} - {req['price']}$\n"
                text += f"   ⏰: {created_time.strftime('%H:%M %d.%m')}\n\n"
                total_amount += req['price']

            text += f"💰 <b>Общая сумма:</b> {total_amount:.2f}$"

            await message.answer(text, parse_mode=ParseMode.HTML)
            db.add_log(ADMIN_ID, "viewed_accepted", f"Просмотрено {len(requests)} принятых заявок")

        # ========== ОТКЛОНЕННЫЕ ЗАЯВКИ АДМИНОМ ==========
        @dp.message(F.text == "❌ Отклоненные заявки")
        async def admin_view_rejected(message: types.Message):
            """Просмотр отклоненных заявок админом"""
            if message.from_user.id != ADMIN_ID:
                await message.answer("❌ Нет доступа!")
                return

            requests = db.get_rejected_requests(limit=20)

            if not requests:
                await message.answer("📭 Нет отклоненных заявок.")
                return

            text = "❌ <b>Отклоненные заявки:</b>\n\n"

            for req in requests:
                created_time = datetime.strptime(req['created_at'], '%Y-%m-%d %H:%M:%S')
                text += f"🔸 <b>Заявка #{req['id']}</b>\n"
                text += f"   👤: {req['full_name']}\n"
                text += f"   📱: <code>{req['phone_number']}</code>\n"
                text += f"   💰: {req['tariff_name']} - {req['price']}$\n"
                if req['rejection_reason']:
                    text += f"   ❌ Причина: {req['rejection_reason']}\n"
                text += f"   ⏰: {created_time.strftime('%H:%M %d.%m')}\n\n"

            await message.answer(text, parse_mode=ParseMode.HTML)
            db.add_log(ADMIN_ID, "viewed_rejected", f"Просмотрено {len(requests)} отклоненных заявок")

        # ========== УПРАВЛЕНИЕ ТАРИФАМИ (УЛУЧШЕННОЕ) ==========
        @dp.message(F.text == "💰 Управление тарифами")
        async def manage_tariffs(message: types.Message):
            """Управление тарифами"""
            if message.from_user.id != ADMIN_ID:
                await message.answer("❌ Нет доступа!")
                return

            tariffs = db.get_all_tariffs()

            if not tariffs:
                text = "📋 <b>Управление тарифами</b>\n\nНет тарифов."
            else:
                text = "📋 <b>Управление тарифами</b>\n\n"
                for tariff in tariffs:
                    status = "✅ ВКЛ" if tariff['is_active'] else "❌ ВЫКЛ"
                    text += f"🔸 <b>{tariff['name']}</b>\n"
                    text += f"   💰 {tariff['price']}$ | ⏱ {tariff['duration_minutes']} мин\n"
                    text += f"   Статус: {status}\n"
                    text += f"   ID: {tariff['id']}\n\n"

            # Клавиатура для управления тарифами
            builder = InlineKeyboardBuilder()
            builder.button(text="➕ Добавить тариф", callback_data="add_tariff")

            if tariffs:
                builder.button(text="⚙️ Управление тарифом", callback_data="select_tariff")
                builder.button(text="🗑️ Удалить тариф", callback_data="delete_tariff_select")

            builder.adjust(1)

            await message.answer(
                text,
                reply_markup=builder.as_markup(),
                parse_mode=ParseMode.HTML
            )

        @dp.callback_query(F.data == "add_tariff")
        async def start_add_tariff(callback: types.CallbackQuery, state: FSMContext):
            """Начать добавление тарифа"""
            await callback.message.edit_text(
                "📝 <b>Добавление нового тарифа</b>\n\n"
                "Введите название тарифа:"
            )
            await state.set_state(AdminStates.adding_tariff_name)
            await callback.answer()

        @dp.message(AdminStates.adding_tariff_name)
        async def process_tariff_name(message: types.Message, state: FSMContext):
            """Обработка названия тарифа"""
            await state.update_data(name=message.text)
            await message.answer(
                "💰 Введите цену тарифа (в долларах):\n"
                "Пример: 5.0"
            )
            await state.set_state(AdminStates.adding_tariff_price)

        @dp.message(AdminStates.adding_tariff_price)
        async def process_tariff_price(message: types.Message, state: FSMContext):
            """Обработка цены тарифа"""
            try:
                price = float(message.text)
                await state.update_data(price=price)
                await message.answer(
                    "⏱ Введите количество минут:\n"
                    "Пример: 25"
                )
                await state.set_state(AdminStates.adding_tariff_minutes)
            except ValueError:
                await message.answer("❌ Неверный формат цены. Введите число:")

        @dp.message(AdminStates.adding_tariff_minutes)
        async def process_tariff_minutes(message: types.Message, state: FSMContext):
            """Обработка минут тарифа"""
            try:
                minutes = int(message.text)
                data = await state.get_data()

                # Создаем тариф
                tariff_id = db.add_tariff(
                    data['name'],
                    data['price'],
                    minutes,
                    ""
                )

                await message.answer(
                    f"✅ Тариф добавлен!\n\n"
                    f"Название: <b>{data['name']}</b>\n"
                    f"Цена: <b>{data['price']}$</b>\n"
                    f"Минуты: <b>{minutes}</b>\n"
                    f"ID: {tariff_id}",
                    parse_mode=ParseMode.HTML
                )

                await state.clear()
                db.add_log(message.from_user.id, "tariff_added", f"Добавлен тариф: {data['name']}")

            except ValueError:
                await message.answer("❌ Неверный формат. Введите целое число:")

        @dp.callback_query(F.data == "select_tariff")
        async def select_tariff_for_edit(callback: types.CallbackQuery):
            """Выбор тарифа для редактирования"""
            tariffs = db.get_all_tariffs()

            if not tariffs:
                await callback.message.edit_text("❌ Нет тарифов.")
                await callback.answer()
                return

            builder = InlineKeyboardBuilder()
            for tariff in tariffs:
                status = "✅" if tariff['is_active'] else "❌"
                builder.button(
                    text=f"{status} {tariff['name']} - {tariff['price']}$",
                    callback_data=f"edit_tariff_{tariff['id']}"
                )

            builder.button(text="◀️ Назад", callback_data="back_to_tariffs")
            builder.adjust(1)

            await callback.message.edit_text(
                "⚙️ <b>Выберите тариф для редактирования:</b>",
                reply_markup=builder.as_markup(),
                parse_mode=ParseMode.HTML
            )
            await callback.answer()

        @dp.callback_query(F.data.startswith("edit_tariff_"))
        async def edit_tariff(callback: types.CallbackQuery):
            """Редактирование тарифа"""
            tariff_id = int(callback.data.split("_")[2])
            tariff = db.get_tariff(tariff_id)

            if not tariff:
                await callback.message.edit_text("❌ Тариф не найден.")
                await callback.answer()
                return

            builder = InlineKeyboardBuilder()

            # Кнопки для управления конкретным тарифом
            if tariff['is_active']:
                builder.button(text="❌ Выключить тариф", callback_data=f"toggle_tariff_{tariff_id}")
            else:
                builder.button(text="✅ Включить тариф", callback_data=f"toggle_tariff_{tariff_id}")

            builder.button(text="✏️ Изменить название", callback_data=f"change_name_{tariff_id}")
            builder.button(text="💰 Изменить цену", callback_data=f"change_price_{tariff_id}")
            builder.button(text="⏱ Изменить минуты", callback_data=f"change_minutes_{tariff_id}")
            builder.button(text="◀️ Назад", callback_data="select_tariff")
            builder.adjust(1)

            status = "✅ ВКЛЮЧЕН" if tariff['is_active'] else "❌ ВЫКЛЮЧЕН"

            await callback.message.edit_text(
                f"⚙️ <b>Управление тарифом:</b>\n\n"
                f"Название: <b>{tariff['name']}</b>\n"
                f"Цена: <b>{tariff['price']}$</b>\n"
                f"Минуты: <b>{tariff['duration_minutes']}</b>\n"
                f"Статус: {status}\n"
                f"ID: {tariff_id}",
                reply_markup=builder.as_markup(),
                parse_mode=ParseMode.HTML
            )
            await callback.answer()

        @dp.callback_query(F.data.startswith("toggle_tariff_"))
        async def toggle_tariff(callback: types.CallbackQuery):
            """Включить/выключить тариф"""
            tariff_id = int(callback.data.split("_")[2])
            tariff = db.get_tariff(tariff_id)

            if not tariff:
                await callback.message.edit_text("❌ Тариф не найден.")
                await callback.answer()
                return

            new_status = not tariff['is_active']
            db.update_tariff(tariff_id, is_active=new_status)

            status_text = "включен ✅" if new_status else "выключен ❌"
            await callback.message.edit_text(
                f"✅ Тариф <b>{tariff['name']}</b> {status_text}!"
            )
            await callback.answer()

            db.add_log(callback.from_user.id, "tariff_toggled",
                       f"Тариф {tariff['name']} {'включен' if new_status else 'выключен'}")

        @dp.callback_query(F.data == "delete_tariff_select")
        async def select_tariff_for_delete(callback: types.CallbackQuery):
            """Выбор тарифа для удаления"""
            tariffs = db.get_all_tariffs()

            if not tariffs:
                await callback.message.edit_text("❌ Нет тарифов.")
                await callback.answer()
                return

            builder = InlineKeyboardBuilder()
            for tariff in tariffs:
                builder.button(
                    text=f"{tariff['name']} - {tariff['price']}$",
                    callback_data=f"delete_tariff_{tariff['id']}"
                )

            builder.button(text="◀️ Назад", callback_data="back_to_tariffs")
            builder.adjust(1)

            await callback.message.edit_text(
                "🗑️ <b>Выберите тариф для удаления:</b>",
                reply_markup=builder.as_markup(),
                parse_mode=ParseMode.HTML
            )
            await callback.answer()

        @dp.callback_query(F.data.startswith("delete_tariff_"))
        async def delete_tariff(callback: types.CallbackQuery):
            """Удаление тарифа"""
            tariff_id = int(callback.data.split("_")[2])
            tariff = db.get_tariff(tariff_id)

            if not tariff:
                await callback.message.edit_text("❌ Тариф не найден.")
                await callback.answer()
                return

            # Создаем клавиатуру подтверждения
            builder = InlineKeyboardBuilder()
            builder.button(text="✅ Да, удалить", callback_data=f"confirm_delete_{tariff_id}")
            builder.button(text="❌ Нет, отменить", callback_data="select_tariff")
            builder.adjust(2)

            await callback.message.edit_text(
                f"⚠️ <b>Вы уверены, что хотите удалить тариф?</b>\n\n"
                f"Название: <b>{tariff['name']}</b>\n"
                f"Цена: <b>{tariff['price']}$</b>\n"
                f"Минуты: <b>{tariff['duration_minutes']}</b>\n\n"
                f"Это действие нельзя отменить!",
                reply_markup=builder.as_markup(),
                parse_mode=ParseMode.HTML
            )
            await callback.answer()

        @dp.callback_query(F.data.startswith("confirm_delete_"))
        async def confirm_delete_tariff(callback: types.CallbackQuery):
            """Подтверждение удаления тарифа"""
            tariff_id = int(callback.data.split("_")[2])
            tariff = db.get_tariff(tariff_id)

            if not tariff:
                await callback.message.edit_text("❌ Тариф не найден.")
                await callback.answer()
                return

            db.delete_tariff(tariff_id)

            await callback.message.edit_text(
                f"🗑️ Тариф <b>{tariff['name']}</b> удален!"
            )
            await callback.answer()

            db.add_log(callback.from_user.id, "tariff_deleted", f"Удален тариф: {tariff['name']}")

        @dp.callback_query(F.data == "back_to_tariffs")
        async def back_to_tariffs_menu(callback: types.CallbackQuery):
            """Вернуться к меню управления тарифами"""
            await manage_tariffs(callback.message)
            await callback.answer()

        # ========== СТАТИСТИКА (УЛУЧШЕННАЯ) ==========
        @dp.message(F.text == "📊 Статистика")
        async def show_statistics(message: types.Message):
            """Показать статистику"""
            if message.from_user.id != ADMIN_ID:
                await message.answer("❌ Нет доступа!")
                return

            # Клавиатура выбора периода
            builder = InlineKeyboardBuilder()
            builder.button(text="📅 Сегодня", callback_data="stats_today")
            builder.button(text="📆 Неделя", callback_data="stats_week")
            builder.button(text="📊 Месяц", callback_data="stats_month")
            builder.button(text="📈 Все время", callback_data="stats_all")
            builder.adjust(2, 2)

            await message.answer(
                "📊 <b>Выберите период для статистики:</b>",
                reply_markup=builder.as_markup(),
                parse_mode=ParseMode.HTML
            )

        @dp.callback_query(F.data.startswith("stats_"))
        async def process_statistics(callback: types.CallbackQuery):
            """Обработка статистики"""
            if callback.from_user.id != ADMIN_ID:
                await callback.answer("❌ Нет доступа!")
                return

            period = callback.data.split("_")[1]

            if period == "today":
                days = 1
                period_text = "сегодня"
            elif period == "week":
                days = 7
                period_text = "за неделю"
            elif period == "month":
                days = 30
                period_text = "за месяц"
            else:  # all
                days = 3650  # 10 лет
                period_text = "за все время"

            stats = db.get_statistics(days)

            # Форматируем статистику
            text = f"📊 <b>Статистика {period_text}</b>\n\n"
            text += f"📈 <b>Всего заявок:</b> {stats['total_requests']}\n"
            text += f"✅ <b>Принято:</b> {stats['accepted']}\n"
            text += f"❌ <b>Отклонено:</b> {stats['rejected']}\n"
            text += f"⏳ <b>В очереди:</b> {stats['pending']}\n"
            text += f"💰 <b>Общая сумма:</b> {stats['total_amount']:.2f}$\n\n"

            if stats['tariff_stats']:
                text += "<b>🏆 Популярные тарифы:</b>\n"
                for tariff in stats['tariff_stats']:
                    text += f"• {tariff['name']}: {tariff['count']} заявок\n"

            # Добавляем статистику по времени (только за день)
            if days <= 1 and stats['time_stats']:
                text += "\n<b>⏰ Активность по часам:</b>\n"
                for time_stat in stats['time_stats']:
                    hour = time_stat['hour']
                    count = time_stat['count']
                    text += f"• {hour}:00 - {count} заявок\n"

            await callback.message.edit_text(text, parse_mode=ParseMode.HTML)
            await callback.answer()

            db.add_log(ADMIN_ID, "viewed_stats", f"Просмотр статистики за {period_text}")

        # ========== ЛОГИ СИСТЕМЫ ==========
        @dp.message(F.text == "📝 Логи системы")
        async def show_logs(message: types.Message):
            """Показать логи системы"""
            if message.from_user.id != ADMIN_ID:
                await message.answer("❌ Нет доступа!")
                return

            # Клавиатура выбора периода
            builder = InlineKeyboardBuilder()
            builder.button(text="📅 Сегодня", callback_data="logs_today")
            builder.button(text="📆 Неделя", callback_data="logs_week")
            builder.button(text="📊 Месяц", callback_data="logs_month")
            builder.adjust(2, 1)

            await message.answer(
                "📝 <b>Выберите период для просмотра логов:</b>",
                reply_markup=builder.as_markup(),
                parse_mode=ParseMode.HTML
            )

        @dp.callback_query(F.data.startswith("logs_"))
        async def process_logs(callback: types.CallbackQuery):
            """Обработка логов"""
            if callback.from_user.id != ADMIN_ID:
                await callback.answer("❌ Нет доступа!")
                return

            period = callback.data.split("_")[1]

            if period == "today":
                days = 1
                period_text = "сегодня"
            elif period == "week":
                days = 7
                period_text = "за неделю"
            else:  # month
                days = 30
                period_text = "за месяц"

            logs = db.get_logs(days, limit=50)

            if not logs:
                await callback.message.edit_text(f"📝 Нет логов {period_text}.")
                await callback.answer()
                return

            text = f"📝 <b>Логи системы ({period_text}):</b>\n\n"

            for log in logs[:15]:  # Показываем первые 15
                time = datetime.strptime(log['created_at'], '%Y-%m-%d %H:%M:%S')
                user_info = f"{log['full_name'] or 'Система'}"

                text += f"🕒 {time.strftime('%H:%M %d.%m')}\n"
                text += f"👤 {user_info}\n"
                text += f"📋 {log['action']}\n"
                if log['details']:
                    text += f"📝 {log['details'][:50]}"
                    if len(log['details']) > 50:
                        text += "..."
                text += "\n\n"

            if len(logs) > 15:
                text += f"\n... всего {len(logs)} записей"

            await callback.message.edit_text(text, parse_mode=ParseMode.HTML)
            await callback.answer()

        # ========== ОБРАБОТКА ТЕКСТОВЫХ ПРИЧИН ОТКЛОНЕНИЯ ==========
        @dp.message(lambda m: m.from_user.id == ADMIN_ID and m.from_user.id in pending_requests)
        async def process_custom_rejection(message: types.Message):
            """Обработка кастомной причины отклонения"""
            if message.from_user.id not in pending_requests:
                return

            data = pending_requests[message.from_user.id]
            request_id = data['request_id']

            # Обновляем статус заявки
            db.update_request_status(
                request_id, 'rejected', message.from_user.id,
                reason=message.text
            )

            # Уведомляем пользователя
            request = db.get_request(request_id)
            if request:
                try:
                    user = db.get_user(request['telegram_id'])
                    if user:
                        await bot.send_message(
                            user['telegram_id'],
                            f"❌ <b>Ваша заявка #{request_id} отклонена</b>\n\n"
                            f"<b>Причина:</b> {message.text}",
                            parse_mode=ParseMode.HTML
                        )
                except Exception as e:
                    logger.error(f"Не удалось уведомить пользователя: {e}")

            await message.answer(f"✅ Заявка #{request_id} отклонена с причиной: {message.text}")

            # Удаляем из pending
            del pending_requests[message.from_user.id]

            db.add_log(message.from_user.id, "request_rejected_custom",
                       f"Заявка #{request_id} отклонена: {message.text}")

        # ========== ОТМЕНА ==========
        @dp.callback_query(F.data == "cancel")
        async def cancel_action(callback: types.CallbackQuery, state: FSMContext):
            """Отмена действия"""
            await callback.message.edit_text("❌ Действие отменено.")
            await state.clear()
            await callback.answer()

        @dp.callback_query(F.data.startswith("back_"))
        async def back_to_request(callback: types.CallbackQuery):
            """Вернуться к заявке"""
            request_id = int(callback.data.split("_")[1])
            request = db.get_request(request_id)

            if not request:
                await callback.message.edit_text("❌ Заявка не найдена.")
                await callback.answer()
                return

            admin_keyboard = InlineKeyboardBuilder()
            admin_keyboard.button(text="✅ Принять", callback_data=f"accept_{request_id}")
            admin_keyboard.button(text="❌ Ошибка", callback_data=f"reject_{request_id}")
            admin_keyboard.adjust(2)

            await callback.message.edit_text(
                f"🆕 <b>ЗАЯВКА #{request_id}</b>\n\n"
                f"👤 <b>Пользователь:</b> {request['full_name']}\n"
                f"📱 <b>Номер:</b> <code>{request['phone_number']}</code>\n"
                f"💰 <b>Тариф:</b> {request['tariff_name']} - {request['price']}$\n"
                f"🆔 <b>ID:</b> <code>{request['telegram_id']}</code>",
                reply_markup=admin_keyboard.as_markup(),
                parse_mode=ParseMode.HTML
            )
            await callback.answer()

        # ========== ЗАПУСК БОТА ==========
        print("=" * 60)
        print("🤖 АХУЕННЫЙ БОТ ЗАПУЩЕН УСПЕШНО!")
        print("=" * 60)
        print(f"Администратор: {ADMIN_ID}")
        print("=" * 60)
        print("\n✅ ВСЕ ЛУЧШИЕ ФИЧИ ОБЪЕДИНЕНЫ:")
        print("📱 Полное главное меню с кнопкой админ-панели")
        print("⚙️ Админ-панель по команде /admin И по кнопке")
        print("✅ Работает просмотр принятых заявок")
        print("❌ Работает просмотр отклоненных заявок")
        print("💰 ПОЛНОЕ управление тарифами (вкл/выкл, удаление, редактирование)")
        print("⚙️ Детальные кнопки управления для каждого тарифа")
        print("📊 УЛУЧШЕННАЯ статистика с графиком активности")
        print("📝 Логи системы")
        print("✅ Кнопки принятия/отклонения заявок")
        print("📱 Удобный процесс сдачи номера")
        print("👤 Подробный профиль пользователя")
        print("🗃️ Архив заявок")
        print("🍽️ Расписание обедов")
        print("=" * 60)
        print("\n🚀 Бот готов к работе!")

        await dp.start_polling(bot)

    except Exception as e:
        logger.error(f"Ошибка запуска бота: {e}")
        print(f"\n❌ Ошибка: {e}")
        print("\n🔧 Возможные решения:")
        print("1. Проверьте токен бота")
        print("2. Установите библиотеки: pip install aiogram")
        print("3. Проверьте интернет-соединение")


if __name__ == "__main__":
    asyncio.run(main())