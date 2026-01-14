import asyncio
import sqlite3
import logging
import os
from datetime import datetime
from typing import Optional

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = "8541361359:AAFXcBFKHBGJ8ScWcydPK5EF2xwuiGvkk1E"
ADMIN_ID = 8500766185
# ===============================

# Настройка красивого логирования
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
        # Удаляем старую базу если есть проблемы
        if os.path.exists(db_path):
            try:
                conn = sqlite3.connect(db_path)
                conn.execute("SELECT 1 FROM users LIMIT 1")
                conn.close()
            except:
                os.remove(db_path)
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
                status TEXT DEFAULT 'pending',
                admin_comment TEXT,
                rejection_reason TEXT,
                photo_file_id TEXT,
                processed_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                processed_at TIMESTAMP,
                number_status TEXT DEFAULT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (tariff_id) REFERENCES tariffs(id)
            )
        ''')

        # Логи
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT NOT NULL,
                details TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Отчеты
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                phone_number TEXT NOT NULL,
                amount REAL NOT NULL,
                status TEXT DEFAULT 'pending',
                payment_date TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Добавляем тестовые тарифы
        cursor.execute("SELECT COUNT(*) FROM tariffs")
        if cursor.fetchone()[0] == 0:
            tariffs = [
                ('🎯 Стандарт', 5.0, 25, 'Базовый тариф для начала работы', 1, 0),
                ('🚀 Премиум', 7.0, 25, 'Расширенный функционал', 1, 1),
                ('👑 VIP', 10.0, 50, 'Максимальные возможности', 1, 2),
                ('💼 Бизнес', 15.0, 100, 'Для корпоративных клиентов', 1, 3)
            ]
            for tariff in tariffs:
                cursor.execute(
                    "INSERT INTO tariffs (name, price, duration_minutes, description, is_active, sort_order) VALUES (?, ?, ?, ?, ?, ?)",
                    tariff
                )

        # Добавляем администратора
        cursor.execute("SELECT COUNT(*) FROM users WHERE telegram_id = ?", (ADMIN_ID,))
        if cursor.fetchone()[0] == 0:
            cursor.execute(
                "INSERT INTO users (telegram_id, username, full_name, role) VALUES (?, ?, ?, 'owner')",
                (ADMIN_ID, 'admin', 'Администратор')
            )

        conn.commit()
        conn.close()
        logger.info("✅ База данных инициализирована")

    def get_connection(self):
        """Получить соединение с БД"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ========== ПОЛЬЗОВАТЕЛИ ==========
    def get_user(self, telegram_id: int):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
        user = cursor.fetchone()
        conn.close()
        return user

    def create_user(self, telegram_id: int, username: str, full_name: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO users (telegram_id, username, full_name) VALUES (?, ?, ?)",
                (telegram_id, username, full_name)
            )
            user_id = cursor.lastrowid
            conn.commit()
        except sqlite3.IntegrityError:
            cursor.execute("SELECT id FROM users WHERE telegram_id = ?", (telegram_id,))
            user = cursor.fetchone()
            user_id = user[0] if user else None
        conn.close()
        return user_id

    def update_user_role(self, telegram_id: int, role: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET role = ? WHERE telegram_id = ?", (role, telegram_id))
        conn.commit()
        conn.close()

    def get_all_users(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT telegram_id, full_name, username, role FROM users ORDER BY created_at DESC")
        users = cursor.fetchall()
        conn.close()
        return users

    def get_users_with_role(self, role: str = None):
        conn = self.get_connection()
        cursor = conn.cursor()
        if role:
            cursor.execute("SELECT telegram_id, full_name, username, role FROM users WHERE role = ?", (role,))
        else:
            cursor.execute("SELECT telegram_id, full_name, username, role FROM users")
        users = cursor.fetchall()
        conn.close()
        return users

    # ========== ТАРИФЫ ==========
    def get_active_tariffs(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tariffs WHERE is_active = 1 ORDER BY sort_order")
        tariffs = cursor.fetchall()
        conn.close()
        return tariffs

    def get_all_tariffs(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tariffs ORDER BY sort_order")
        tariffs = cursor.fetchall()
        conn.close()
        return tariffs

    def get_tariff(self, tariff_id: int):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tariffs WHERE id = ?", (tariff_id,))
        tariff = cursor.fetchone()
        conn.close()
        return tariff

    def add_tariff(self, name: str, price: float, minutes: int, description: str = ''):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(sort_order) FROM tariffs")
        max_order = cursor.fetchone()[0] or 0
        cursor.execute(
            "INSERT INTO tariffs (name, price, duration_minutes, description, is_active, sort_order) VALUES (?, ?, ?, ?, 1, ?)",
            (name, price, minutes, description, max_order + 1)
        )
        tariff_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return tariff_id

    def update_tariff(self, tariff_id: int, **kwargs):
        if not kwargs:
            return
        conn = self.get_connection()
        cursor = conn.cursor()
        updates = []
        params = []
        for key, value in kwargs.items():
            if key == 'is_active':
                updates.append(f"{key} = ?")
                params.append(1 if value else 0)
            elif value is not None:
                updates.append(f"{key} = ?")
                params.append(value)
        params.append(tariff_id)
        query = f"UPDATE tariffs SET {', '.join(updates)} WHERE id = ?"
        cursor.execute(query, params)
        conn.commit()
        conn.close()

    def delete_tariff(self, tariff_id: int):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM tariffs WHERE id = ?", (tariff_id,))
        conn.commit()
        conn.close()

    # ========== ЗАЯВКИ ==========
    def create_request(self, user_id: int, tariff_id: int, phone_number: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO requests (user_id, tariff_id, phone_number, status) VALUES (?, ?, ?, 'pending')",
            (user_id, tariff_id, phone_number)
        )
        request_id = cursor.lastrowid
        cursor.execute("UPDATE users SET total_requests = total_requests + 1 WHERE id = ?", (user_id,))
        conn.commit()
        conn.close()
        return request_id

    def update_request_status(self, request_id: int, status: str, admin_id: int, reason: str = None, photo: str = None):
        conn = self.get_connection()
        cursor = conn.cursor()

        if status == 'accepted':
            cursor.execute("SELECT user_id, tariff_id FROM requests WHERE id = ?", (request_id,))
            req = cursor.fetchone()
            if req:
                tariff = self.get_tariff(req['tariff_id'])
                if tariff:
                    cursor.execute(
                        "UPDATE users SET total_amount = total_amount + ? WHERE id = ?",
                        (tariff['price'], req['user_id'])
                    )

        cursor.execute('''
            UPDATE requests SET status = ?, processed_by = ?, rejection_reason = ?, photo_file_id = ?, 
            processed_at = CURRENT_TIMESTAMP WHERE id = ?
        ''', (status, admin_id, reason, photo, request_id))

        conn.commit()
        conn.close()

    def get_request(self, request_id: int):
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

    def get_user_requests(self, telegram_id: int, status: str = None):
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
            ''', (telegram_id, status))
        else:
            cursor.execute('''
                SELECT r.*, t.name as tariff_name, t.price
                FROM requests r
                JOIN users u ON r.user_id = u.id
                JOIN tariffs t ON r.tariff_id = t.id
                WHERE u.telegram_id = ?
                ORDER BY r.created_at DESC
            ''', (telegram_id,))

        requests = cursor.fetchall()
        conn.close()
        return requests

    def get_today_numbers(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT r.*, u.telegram_id, u.full_name, t.name as tariff_name, t.price
            FROM requests r
            JOIN users u ON r.user_id = u.id
            JOIN tariffs t ON r.tariff_id = t.id
            WHERE date(r.created_at) = date('now')
            AND r.status = 'accepted'
            ORDER BY r.created_at DESC
        ''')
        numbers = cursor.fetchall()
        conn.close()
        return numbers

    def update_number_status(self, request_id: int, status: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE requests SET number_status = ? WHERE id = ?", (status, request_id))
        conn.commit()
        conn.close()

    # ========== ОТЧЕТЫ ==========
    def add_report(self, request_id: int, user_id: int, phone_number: str, amount: float):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO reports (request_id, user_id, phone_number, amount) VALUES (?, ?, ?, ?)",
            (request_id, user_id, phone_number, amount)
        )
        report_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return report_id

    def get_reports_by_date(self, date_str: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT r.*, u.full_name
            FROM reports r
            JOIN users u ON r.user_id = u.id
            WHERE date(r.created_at) = ?
            ORDER BY r.created_at DESC
        ''', (date_str,))
        reports = cursor.fetchall()
        conn.close()
        return reports

    # ========== ЛОГИ ==========
    def add_log(self, user_id: int, action: str, details: str = None):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO logs (user_id, action, details) VALUES (?, ?, ?)",
            (user_id, action, details)
        )
        conn.commit()
        conn.close()

    def get_logs(self, days=1, limit=100):
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

    # ========== СТАТИСТИКА ==========
    def get_pending_requests(self, limit=50):
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

    def get_accepted_requests(self, limit=50):
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

    def get_rejected_requests(self, limit=50):
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

    def get_statistics(self, days=1):
        conn = self.get_connection()
        cursor = conn.cursor()
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
        conn.close()
        return {
            'total_requests': stats['total_requests'] or 0,
            'accepted': stats['accepted'] or 0,
            'rejected': stats['rejected'] or 0,
            'pending': stats['pending'] or 0,
            'total_amount': stats['total_amount'] or 0.0
        }


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
    waiting_phone = State()
    waiting_tariff_choice = State()


class AdminStates(StatesGroup):
    waiting_photo_code = State()
    waiting_report_date = State()
    waiting_message_for_user = State()
    broadcast_all = State()
    adding_tariff_name = State()
    adding_tariff_price = State()
    adding_tariff_minutes = State()
    editing_tariff_name = State()
    editing_tariff_price = State()
    editing_tariff_minutes = State()


# Глобальные переменные
pending_requests = {}


async def main():
    """Основная функция"""
    if not BOT_TOKEN:
        print("❌ ТОКЕН БОТА НЕ УСТАНОВЛЕН!")
        return

    try:
        bot = Bot(token=BOT_TOKEN)
        storage = MemoryStorage()
        dp = Dispatcher(storage=storage)

        # ========== КРАСИВЫЕ ФУНКЦИИ ФОРМАТИРОВАНИЯ ==========
        def format_tariff(tariff):
            """Форматирование информации о тарифе"""
            status = "🟢" if tariff['is_active'] else "🔴"
            return f"""
{status} <b>{tariff['name']}</b>
💰 Цена: <b>{tariff['price']}$</b>
⏱ Время: <b>{tariff['duration_minutes']} минут</b>
📝 Описание: {tariff['description'] or 'Нет описания'}
🆔 ID: {tariff['id']}
        """.strip()

        def format_user(user):
            """Форматирование информации о пользователе"""
            role_icons = {
                'user': '👤',
                'moderator': '🛡️',
                'admin': '⚙️',
                'owner': '👑'
            }
            role_names = {
                'user': 'Пользователь',
                'moderator': 'Модератор',
                'admin': 'Администратор',
                'owner': 'Владелец'
            }
            icon = role_icons.get(user['role'], '❓')
            role = role_names.get(user['role'], user['role'])

            return f"""
{icon} <b>{user['full_name']}</b>
👤 @{user['username'] or 'без username'}
🆔 ID: <code>{user['telegram_id']}</code>
🎖️ Роль: {role}
📅 Регистрация: {user['created_at'][:10]}
📊 Заявок: {user['total_requests']}
💰 Сумма: {user['total_amount']:.2f}$
            """.strip()

        def format_request(request):
            """Форматирование информации о заявке"""
            status_icons = {
                'pending': '🟡',
                'accepted': '🟢',
                'rejected': '🔴'
            }
            status_names = {
                'pending': '⏳ В ожидании',
                'accepted': '✅ Принята',
                'rejected': '❌ Отклонена'
            }

            icon = status_icons.get(request['status'], '❓')
            status = status_names.get(request['status'], request['status'])

            return f"""
{icon} <b>Заявка #{request['id']}</b>
📱 Номер: <code>{request['phone_number']}</code>
💰 Тариф: {request['tariff_name']} - {request['price']}$
📊 Статус: {status}
📅 Дата: {request['created_at'][:16]}
            """.strip()

        # ========== ПРОВЕРКА ПРАВ ==========
        def is_admin(user_id):
            user = db.get_user(user_id)
            return user and user['role'] in ['admin', 'owner']

        def is_owner(user_id):
            user = db.get_user(user_id)
            return user and user['role'] == 'owner'

        def is_moderator(user_id):
            user = db.get_user(user_id)
            return user and user['role'] in ['moderator', 'admin', 'owner']

        # ========== КОМАНДА /start ==========
        @dp.message(CommandStart())
        async def start_command(message: types.Message):
            user = db.get_user(message.from_user.id)
            if not user:
                db.create_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
                db.add_log(message.from_user.id, "user_registered",
                           f"Новый пользователь: {message.from_user.full_name}")

            # Красивая главная клавиатура
            keyboard = ReplyKeyboardBuilder()
            keyboard.button(text="📱 Сдать номер")
            keyboard.button(text="📊 Мои заявки")
            keyboard.button(text="🗂️ Архив заявок")
            keyboard.button(text="👤 Мой профиль")
            keyboard.button(text="ℹ️ Информация")

            if is_moderator(message.from_user.id):
                keyboard.button(text="⚙️ Админ-панель")

            keyboard.adjust(2, 2, 1)

            welcome_text = f"""
✨ <b>Добро пожаловать, {message.from_user.first_name}!</b> ✨

🤖 Я - ваш помощник по работе с WhatsApp номерами.

📋 <b>Доступные действия:</b>
• 📱 <b>Сдать номер</b> - отправить номер для работы
• 📊 <b>Мои заявки</b> - отслеживать статус заявок
• 🗂️ <b>Архив заявок</b> - просмотр истории
• 👤 <b>Мой профиль</b> - информация о вас
• ℹ️ <b>Информация</b> - правила и условия

🚀 <b>Начните с выбора действия ниже:</b>
            """.strip()

            await message.answer(
                welcome_text,
                reply_markup=keyboard.as_markup(resize_keyboard=True),
                parse_mode=ParseMode.HTML
            )

        # ========== ИНФОРМАЦИЯ ==========
        @dp.message(F.text == "ℹ️ Информация")
        async def info_command(message: types.Message):
            info_text = """
📋 <b>Информация о боте</b>

🤖 <b>Назначение:</b>
Я помогаю организовать работу с WhatsApp номерами. Через меня вы можете сдавать номера для работы и отслеживать их статус.

🔄 <b>Как это работает:</b>
1️⃣ Выбираете тариф
2️⃣ Отправляете номер телефона
3️⃣ Ожидаете обработки оператором
4️⃣ Получаете уведомления о статусе

⏰ <b>Время работы:</b>
• 📅 Понедельник - Пятница: 9:00 - 19:00

📞 <b>Поддержка:</b>
Если возникли вопросы или проблемы - обратитесь к администратору.

🚀 <b>Приятной работы!</b>
            """.strip()

            await message.answer(info_text, parse_mode=ParseMode.HTML)

        # ========== СДАТЬ НОМЕР ==========
        @dp.message(F.text == "📱 Сдать номер")
        async def submit_number(message: types.Message, state: FSMContext):
            tariffs = db.get_active_tariffs()
            if not tariffs:
                await message.answer(
                    "😔 <b>На данный момент нет доступных тарифов.</b>\n\nОбратитесь к администратору для уточнения информации.",
                    parse_mode=ParseMode.HTML)
                return

            builder = InlineKeyboardBuilder()
            for tariff in tariffs:
                status = "🟢" if tariff['is_active'] else "🔴"
                builder.button(
                    text=f"{status} {tariff['name']} - {tariff['price']}$",
                    callback_data=f"tariff_{tariff['id']}"
                )
            builder.button(text="❌ Отмена", callback_data="cancel")
            builder.adjust(1)

            tariffs_text = "\n\n".join([format_tariff(tariff) for tariff in tariffs])

            await message.answer(
                f"""
📋 <b>Выберите тариф для работы:</b>

{tariffs_text}

👇 <b>Нажмите на кнопку с выбранным тарифом:</b>
                """.strip(),
                reply_markup=builder.as_markup(),
                parse_mode=ParseMode.HTML
            )
            await state.set_state(UserStates.waiting_tariff_choice)

        # ========== ВЫБОР ТАРИФА ==========
        @dp.callback_query(F.data.startswith("tariff_"))
        async def process_tariff(callback: types.CallbackQuery, state: FSMContext):
            tariff_id = int(callback.data.split("_")[1])
            tariff = db.get_tariff(tariff_id)

            if not tariff:
                await callback.message.edit_text("❌ <b>Тариф не найден!</b>", parse_mode=ParseMode.HTML)
                await callback.answer()
                return

            await state.update_data(tariff_id=tariff_id, tariff_name=tariff['name'])

            await callback.message.edit_text(
                f"""
🎯 <b>Отличный выбор!</b>

📋 <b>Выбран тариф:</b> {tariff['name']}
💰 <b>Цена:</b> {tariff['price']}$
⏱ <b>Время:</b> {tariff['duration_minutes']} минут
📝 <b>Описание:</b> {tariff['description'] or 'Нет описания'}

📱 <b>Теперь отправьте номер телефона:</b>
• Формат: <code>+7XXXXXXXXXX</code> или <code>8XXXXXXXXXX</code>
• Только Казахстанские номера
• Номер должен быть активен
                """.strip(),
                parse_mode=ParseMode.HTML
            )
            await state.set_state(UserStates.waiting_phone)
            await callback.answer()

        # ========== ОБРАБОТКА НОМЕРА ==========
        @dp.message(UserStates.waiting_phone)
        async def process_phone(message: types.Message, state: FSMContext):
            phone = message.text.strip()
            clean_phone = phone.replace('+7', '8').replace(' ', '').replace('-', '')

            if not clean_phone.isdigit() or len(clean_phone) != 11 or not clean_phone.startswith('8'):
                await message.answer(
                    """
❌ <b>Неверный формат номера!</b>

📱 <b>Правильный формат:</b>
• <code>+79991234567</code>
• <code>89991234567</code>

🔍 <b>Проверьте номер и попробуйте снова:</b>
                    """.strip(),
                    parse_mode=ParseMode.HTML
                )
                return

            data = await state.get_data()
            tariff_id = data['tariff_id']
            user = db.get_user(message.from_user.id)

            if not user:
                await message.answer("❌ <b>Ошибка доступа!</b>\n\nНапишите /start для начала работы.",
                                     parse_mode=ParseMode.HTML)
                await state.clear()
                return

            request_id = db.create_request(user['id'], tariff_id, clean_phone)
            db.add_log(user['id'], "request_created", f"Заявка #{request_id}")

            # Уведомляем администраторов и модераторов
            admins = db.get_users_with_role()
            for admin in admins:
                if admin['role'] in ['admin', 'owner', 'moderator']:
                    try:
                        builder = InlineKeyboardBuilder()
                        builder.button(text="✅ Взять номер", callback_data=f"take_{request_id}")
                        builder.button(text="❌ Отклонить", callback_data=f"reject_{request_id}")
                        builder.adjust(2)

                        admin_text = f"""
🆕 <b>НОВАЯ ЗАЯВКА #{request_id}</b>

👤 <b>Клиент:</b> {message.from_user.full_name}
📱 <b>Номер:</b> <code>{clean_phone}</code>
💰 <b>Тариф:</b> {data['tariff_name']}
🆔 <b>ID клиента:</b> <code>{message.from_user.id}</code>
⏰ <b>Время:</b> {datetime.now().strftime('%H:%M %d.%m.%Y')}

👇 <b>Выберите действие:</b>
                        """.strip()

                        await bot.send_message(
                            admin['telegram_id'],
                            admin_text,
                            reply_markup=builder.as_markup(),
                            parse_mode=ParseMode.HTML
                        )
                    except Exception as e:
                        logger.error(f"Не удалось отправить уведомление админу: {e}")

            success_text = f"""
🎉 <b>Заявка создана успешно!</b>

📋 <b>Детали заявки:</b>
🆔 <b>Номер заявки:</b> #{request_id}
📱 <b>Телефон:</b> <code>{clean_phone}</code>
💰 <b>Тариф:</b> {data['tariff_name']}
⏰ <b>Время отправки:</b> {datetime.now().strftime('%H:%M %d.%m.%Y')}

📊 <b>Что дальше?</b>
• Ваша заявка добавлена в очередь
• Оператор скоро её обработает
• Вы получите уведомление о статусе

🔔 <b>Следите за статусом в разделе «📊 Мои заявки»</b>
            """.strip()

            await message.answer(success_text, parse_mode=ParseMode.HTML)
            await state.clear()

        # ========== МОИ ЗАЯВКИ ==========
        @dp.message(F.text == "📊 Мои заявки")
        async def my_requests(message: types.Message):
            requests = db.get_user_requests(message.from_user.id, 'pending')

            if not requests:
                await message.answer(
                    """
📭 <b>У вас нет активных заявок</b>

✨ <b>Хотите создать первую заявку?</b>
Нажмите «📱 Сдать номер» в главном меню!
                    """.strip(),
                    parse_mode=ParseMode.HTML
                )
                return

            text = """
📊 <b>Ваши активные заявки:</b>

            """.strip()

            for req in requests[:10]:
                text += f"\n{format_request(req)}\n"
                text += "─" * 30

            if len(requests) > 10:
                text += f"\n\n... и ещё {len(requests) - 10} заявок"

            await message.answer(text, parse_mode=ParseMode.HTML)

        # ========== АРХИВ ЗАЯВОК ==========
        @dp.message(F.text == "🗂️ Архив заявок")
        async def archive_requests(message: types.Message):
            requests = db.get_user_requests(message.from_user.id)

            if not requests:
                await message.answer(
                    """
🗃️ <b>Архив заявок пуст</b>

📋 <b>Здесь будут отображаться все ваши заявки:</b>
• ✅ Принятые
• ❌ Отклоненные
• ⏳ Ожидающие
• 📁 Завершенные

✨ <b>Создайте первую заявку в разделе «📱 Сдать номер»</b>
                    """.strip(),
                    parse_mode=ParseMode.HTML
                )
                return

            text = """
🗂️ <b>Архив ваших заявок:</b>

            """.strip()

            for req in requests[:15]:
                text += f"\n{format_request(req)}\n"
                if req['status'] == 'rejected' and req['rejection_reason']:
                    text += f"📝 <b>Причина отказа:</b> {req['rejection_reason']}\n"
                text += "─" * 30

            if len(requests) > 15:
                text += f"\n\n📊 <b>Всего заявок:</b> {len(requests)}"

            await message.answer(text, parse_mode=ParseMode.HTML)

        # ========== МОЙ ПРОФИЛЬ ==========
        @dp.message(F.text == "👤 Мой профиль")
        async def my_profile(message: types.Message):
            user = db.get_user(message.from_user.id)

            if not user:
                await message.answer("❌ <b>Пользователь не найден!</b>\n\nНапишите /start для регистрации.",
                                     parse_mode=ParseMode.HTML)
                return

            text = format_user(user)

            builder = InlineKeyboardBuilder()
            builder.button(text="📊 Моя статистика", callback_data="my_stats")
            builder.adjust(1)

            await message.answer(text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)

        @dp.callback_query(F.data == "my_stats")
        async def my_statistics(callback: types.CallbackQuery):
            user = db.get_user(callback.from_user.id)
            requests = db.get_user_requests(callback.from_user.id)

            total = len(requests)
            accepted = sum(1 for r in requests if r['status'] == 'accepted')
            rejected = sum(1 for r in requests if r['status'] == 'rejected')
            pending = sum(1 for r in requests if r['status'] == 'pending')

            text = f"""
📊 <b>Ваша статистика:</b>

📈 <b>Общая статистика:</b>
• 📋 Всего заявок: <b>{total}</b>
• ✅ Принято: <b>{accepted}</b>
• ❌ Отклонено: <b>{rejected}</b>
• ⏳ В ожидании: <b>{pending}</b>

💰 <b>Финансовая статистика:</b>
• 💵 Общая сумма: <b>{user['total_amount']:.2f}$</b>
• 📅 Средний чек: <b>{(user['total_amount'] / accepted if accepted else 0):.2f}$</b>

🎯 <b>Рекомендации:</b>
• Старайтесь указывать корректные номера
• Следите за статусом заявок
• Обращайтесь к администратору при вопросах
            """.strip()

            await callback.message.answer(text, parse_mode=ParseMode.HTML)
            await callback.answer()

        # ========== АДМИН ПАНЕЛЬ ==========
        @dp.message(F.text == "⚙️ Админ-панель")
        async def admin_panel(message: types.Message):
            if not is_moderator(message.from_user.id):
                await message.answer(
                    """
🔒 <b>Доступ запрещен!</b>

⛔ У вас нет прав для доступа к админ-панели.

👨‍💼 <b>Если вы администратор:</b>
1. Убедитесь, что вы авторизованы
2. Обратитесь к владельцу бота
3. Проверьте свои права доступа

📞 <b>Контакт поддержки:</b> @galactika_work_support
                    """.strip(),
                    parse_mode=ParseMode.HTML
                )
                return

            # Красивая админ-панель
            keyboard = ReplyKeyboardBuilder()

            # Основные функции
            keyboard.button(text="📊 Статистика")
            keyboard.button(text="📋 Заявки в работе")
            keyboard.button(text="✅ Принятые заявки")
            keyboard.button(text="❌ Отклоненные заявки")
            keyboard.button(text="📱 Номера сегодня")

            # Управление
            keyboard.button(text="💰 Управление тарифами")
            keyboard.button(text="📝 Системные логи")

            # Функции владельца
            if is_owner(message.from_user.id):
                keyboard.button(text="👥 Управление пользователями")
                keyboard.button(text="📢 Массовая рассылка")
                keyboard.button(text="📄 Финансовые отчеты")

            keyboard.button(text="🏠 Главное меню")
            keyboard.adjust(2, 2, 2, 2, 2, 1)

            admin_text = f"""
⚙️ <b>Административная панель</b>

👋 <b>Добро пожаловать, {message.from_user.first_name}!</b>

📊 <b>Быстрый доступ:</b>
• 📋 Заявки в работе
• 📱 Сегодняшние номера
• 📊 Общая статистика

⚙️ <b>Управление системой:</b>
• 💰 Тарифы и цены
• 👥 Пользователи и права
• 📢 Уведомления

👇 <b>Выберите раздел:</b>
            """.strip()

            await message.answer(
                admin_text,
                reply_markup=keyboard.as_markup(resize_keyboard=True),
                parse_mode=ParseMode.HTML
            )
            db.add_log(message.from_user.id, "admin_panel_opened")

        # ========== ГЛАВНОЕ МЕНЮ ==========
        @dp.message(F.text == "🏠 Главное меню")
        async def back_to_main(message: types.Message):
            await start_command(message)

        # ========== СТАТИСТИКА ==========
        @dp.message(F.text == "📊 Статистика")
        async def show_stats(message: types.Message):
            if not is_moderator(message.from_user.id):
                return

            stats = db.get_statistics(1)

            text = f"""
📊 <b>Статистика за сегодня</b>

📈 <b>Общая активность:</b>
• 📋 Всего заявок: <b>{stats['total_requests']}</b>
• ✅ Принято: <b>{stats['accepted']}</b>
• ❌ Отклонено: <b>{stats['rejected']}</b>
• ⏳ В работе: <b>{stats['pending']}</b>

💰 <b>Финансовые показатели:</b>
• 💵 Общий доход: <b>{stats['total_amount']:.2f}$</b>
• 📊 Средний чек: <b>{(stats['total_amount'] / stats['accepted'] if stats['accepted'] else 0):.2f}$</b>

🎯 <b>Эффективность:</b>
• 📈 Конверсия: <b>{(stats['accepted'] / stats['total_requests'] * 100 if stats['total_requests'] else 0):.1f}%</b>
• ⏱ Среднее время обработки: <b>~15 минут</b>
            """.strip()

            builder = InlineKeyboardBuilder()
            builder.button(text="📅 За неделю", callback_data="stats_week")
            builder.button(text="📅 За месяц", callback_data="stats_month")
            builder.adjust(2)

            await message.answer(text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)

        # ========== ЗАЯВКИ В РАБОТЕ ==========
        @dp.message(F.text == "📋 Заявки в работе")
        async def pending_admin(message: types.Message):
            if not is_moderator(message.from_user.id):
                return

            requests = db.get_pending_requests()

            if not requests:
                await message.answer(
                    """
📭 <b>Нет заявок в работе</b>

✅ Все заявки обработаны!
Отличная работа, команда! 🎉

🔄 <b>Что делать дальше?</b>
• Дождитесь новых заявок
• Проверьте работу системы
• Подготовьтесь к следующей смене
                    """.strip(),
                    parse_mode=ParseMode.HTML
                )
                return

            text = """
📋 <b>Заявки в работе (ожидают обработки):</b>

            """.strip()

            for req in requests[:15]:
                text += f"\n{format_request(req)}\n"
                text += "─" * 30

            if len(requests) > 15:
                text += f"\n\n📊 <b>Всего в работе:</b> {len(requests)} заявок"

            await message.answer(text, parse_mode=ParseMode.HTML)

        # ========== ПРИНЯТЫЕ ЗАЯВКИ ==========
        @dp.message(F.text == "✅ Принятые заявки")
        async def accepted_admin(message: types.Message):
            if not is_moderator(message.from_user.id):
                return

            requests = db.get_accepted_requests()

            if not requests:
                await message.answer(
                    """
📭 <b>Нет принятых заявок</b>

🔄 <b>Начните обработку заявок:</b>
1. Перейдите в «📋 Заявки в работе»
2. Выберите заявку для обработки
3. Отправьте код клиенту
                    """.strip(),
                    parse_mode=ParseMode.HTML
                )
                return

            total_amount = sum(req['price'] for req in requests)

            text = f"""
✅ <b>Принятые заявки (история):</b>

💰 <b>Общая сумма:</b> {total_amount:.2f}$
📊 <b>Количество:</b> {len(requests)} заявок

            """.strip()

            for req in requests[:10]:
                text += f"\n{format_request(req)}\n"
                text += "─" * 30

            if len(requests) > 10:
                text += f"\n\n📊 <b>Всего принято:</b> {len(requests)} заявок"

            await message.answer(text, parse_mode=ParseMode.HTML)

        # ========== ОТКЛОНЕННЫЕ ЗАЯВКИ ==========
        @dp.message(F.text == "❌ Отклоненные заявки")
        async def rejected_admin(message: types.Message):
            if not is_moderator(message.from_user.id):
                return

            requests = db.get_rejected_requests()

            if not requests:
                await message.answer(
                    """
✅ <b>Нет отклоненных заявок</b>

🎉 Отличная новость!
Все заявки были успешно обработаны.

📊 <b>Качество работы:</b> 100% успешных обработок
                    """.strip(),
                    parse_mode=ParseMode.HTML
                )
                return

            text = """
❌ <b>Отклоненные заявки (история):</b>

📝 <b>Анализ причин отказов поможет улучшить работу</b>

            """.strip()

            for req in requests[:10]:
                text += f"\n{format_request(req)}\n"
                if req['rejection_reason']:
                    text += f"📝 <b>Причина:</b> {req['rejection_reason']}\n"
                text += "─" * 30

            if len(requests) > 10:
                text += f"\n\n📊 <b>Всего отклонено:</b> {len(requests)} заявок"

            await message.answer(text, parse_mode=ParseMode.HTML)

        # ========== НОМЕРА СЕГОДНЯ ==========
        @dp.message(F.text == "📱 Номера сегодня")
        async def today_numbers(message: types.Message):
            if not is_moderator(message.from_user.id):
                return

            numbers = db.get_today_numbers()

            if not numbers:
                await message.answer(
                    """
📭 <b>Нет номеров за сегодня</b>

🔄 <b>Ожидайте новых заявок:</b>
• Клиенты могут сдавать номера круглосуточно
• Пиковая активность: 10:00-12:00 и 15:00-18:00
• Проверьте уведомления
                    """.strip(),
                    parse_mode=ParseMode.HTML
                )
                return

            builder = InlineKeyboardBuilder()
            for num in numbers[:20]:
                builder.button(
                    text=f"📱 {num['phone_number']} - {num['tariff_name']}",
                    callback_data=f"today_{num['id']}"
                )
            builder.adjust(1)

            text = f"""
📱 <b>Номера за сегодня</b>

📊 <b>Статистика дня:</b>
• 📋 Всего номеров: {len(numbers)}
• 💰 Общий оборот: {sum(n['price'] for n in numbers):.2f}$
• 📈 Средний чек: {(sum(n['price'] for n in numbers) / len(numbers) if numbers else 0):.2f}$

👇 <b>Выберите номер для управления:</b>
            """.strip()

            await message.answer(text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)

        # ========== УПРАВЛЕНИЕ НОМЕРОМ ==========
        @dp.callback_query(F.data.startswith("today_"))
        async def manage_number(callback: types.CallbackQuery):
            if not is_moderator(callback.from_user.id):
                await callback.answer("🔒 Доступ запрещен!")
                return

            request_id = int(callback.data.split("_")[1])
            request = db.get_request(request_id)

            if not request:
                await callback.answer("❌ Заявка не найдена!")
                return

            builder = InlineKeyboardBuilder()
            builder.button(text="✅ ВСТАЛ", callback_data=f"stood_{request_id}")
            builder.button(text="❌ СЛЕТЕЛ", callback_data=f"fell_{request_id}")
            builder.button(text="📄 ОТСТОЯЛ", callback_data=f"archived_{request_id}")
            builder.button(text="✉️ Написать клиенту", callback_data=f"message_{request_id}")
            builder.button(text="🔙 Назад к списку", callback_data="back_to_today")
            builder.adjust(2, 2, 1)

            text = f"""
🎯 <b>Управление номером</b>

📱 <b>Информация о номере:</b>
• 🔢 Номер: <code>{request['phone_number']}</code>
• 👤 Клиент: {request['full_name']}
• 💰 Тариф: {request['tariff_name']} - {request['price']}$
• 📅 Дата: {request['created_at'][:16]}

👇 <b>Выберите действие:</b>
            """.strip()

            await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)
            await callback.answer()

        @dp.callback_query(F.data.startswith("stood_"))
        async def number_stood(callback: types.CallbackQuery):
            request_id = int(callback.data.split("_")[1])
            request = db.get_request(request_id)

            db.update_number_status(request_id, 'stood')

            try:
                await bot.send_message(
                    request['telegram_id'],
                    f"""
✅ <b>Отличные новости!</b>

📱 <b>Ваш номер:</b> <code>{request['phone_number']}</code>
🎯 <b>Статус:</b> ВСТАЛ успешно!

🚀 <b>Номер активен и готов к работе!</b>

💡 <b>Рекомендации:</b>
• Следите за уведомлениями
• Будьте готовы к работе
• Сообщите оператору о проблемах
                    """.strip(),
                    parse_mode=ParseMode.HTML
                )
            except:
                pass

            await callback.message.edit_text(
                """
✅ <b>Сообщение отправлено клиенту!</b>

📱 <b>Статус:</b> Номер встал
👤 <b>Клиент уведомлен</b>
                """.strip(),
                parse_mode=ParseMode.HTML
            )
            await callback.answer()

        @dp.callback_query(F.data.startswith("fell_"))
        async def number_fell(callback: types.CallbackQuery):
            request_id = int(callback.data.split("_")[1])
            request = db.get_request(request_id)

            db.update_number_status(request_id, 'fell')

            try:
                await bot.send_message(
                    request['telegram_id'],
                    f"""
⚠️ <b>Важное уведомление</b>

📱 <b>Ваш номер:</b> <code>{request['phone_number']}</code>
🎯 <b>Статус:</b> СЛЕТЕЛ

😔 <b>К сожалению, номер перестал работать.</b>

🔄 <b>Что делать?</b>
• Проверьте подключение
• Обратитесь к оператору
• Создайте новую заявку при необходимости

📞 <b>Техническая поддержка:</b> @galactika_work_support
                    """.strip(),
                    parse_mode=ParseMode.HTML
                )
            except:
                pass

            await callback.message.edit_text(
                """
✅ <b>Сообщение отправлено клиенту!</b>

📱 <b>Статус:</b> Номер слетел
👤 <b>Клиент уведомлен</b>
                """.strip(),
                parse_mode=ParseMode.HTML
            )
            await callback.answer()

        @dp.callback_query(F.data.startswith("archived_"))
        async def number_archived(callback: types.CallbackQuery):
            request_id = int(callback.data.split("_")[1])
            request = db.get_request(request_id)

            db.update_number_status(request_id, 'archived')
            db.add_report(request_id, request['user_id'], request['phone_number'], request['price'])

            await callback.message.edit_text(
                f"""
📄 <b>Номер добавлен в отчеты!</b>

✅ <b>Успешно завершена работа с номером:</b>

📱 <b>Номер:</b> <code>{request['phone_number']}</code>
👤 <b>Клиент:</b> {request['full_name']}
💰 <b>Сумма к выплате:</b> {request['price']}$
📊 <b>Статус:</b> Отстоял успешно

📋 <b>Что дальше?</b>
• Клиент получит выплату
• Номер добавлен в архив
• Финансовый отчет обновлен
                """.strip(),
                parse_mode=ParseMode.HTML
            )
            await callback.answer()

        @dp.callback_query(F.data == "back_to_today")
        async def back_to_today_list(callback: types.CallbackQuery):
            await today_numbers(callback.message)
            await callback.answer()

        # ========== УПРАВЛЕНИЕ ТАРИФАМИ ==========
        @dp.message(F.text == "💰 Управление тарифами")
        async def manage_tariffs(message: types.Message):
            if not is_moderator(message.from_user.id):
                return

            tariffs = db.get_all_tariffs()

            text = """
💰 <b>Управление тарифами</b>

📋 <b>Доступные тарифы:</b>

            """.strip()

            for tariff in tariffs:
                status = "🟢 АКТИВЕН" if tariff['is_active'] else "🔴 НЕАКТИВЕН"
                text += f"\n{format_tariff(tariff)}\n"
                text += f"📊 Статус: {status}\n"
                text += "─" * 40 + "\n"

            builder = InlineKeyboardBuilder()
            builder.button(text="➕ Добавить тариф", callback_data="add_tariff_menu")
            builder.button(text="⚙️ Редактировать тариф", callback_data="edit_tariff_menu")
            builder.button(text="🔍 Просмотр тарифов", callback_data="view_tariffs")
            builder.adjust(1)

            await message.answer(text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)

        @dp.callback_query(F.data == "add_tariff_menu")
        async def add_tariff_start(callback: types.CallbackQuery, state: FSMContext):
            await callback.message.edit_text(
                """
➕ <b>Добавление нового тарифа</b>

📝 <b>Введите название тарифа:</b>
• Например: «🎯 Стандарт Плюс»
• Используйте эмодзи для наглядности
• Название должно быть уникальным
                """.strip(),
                parse_mode=ParseMode.HTML
            )
            await state.set_state(AdminStates.adding_tariff_name)
            await callback.answer()

        @dp.message(AdminStates.adding_tariff_name)
        async def add_tariff_name(message: types.Message, state: FSMContext):
            await state.update_data(name=message.text)
            await message.answer(
                """
💰 <b>Введите цену тарифа:</b>
• Формат: число с точкой
• Пример: 5.0 или 7.5
• Цена в долларах ($)
                """.strip(),
                parse_mode=ParseMode.HTML
            )
            await state.set_state(AdminStates.adding_tariff_price)

        @dp.message(AdminStates.adding_tariff_price)
        async def add_tariff_price(message: types.Message, state: FSMContext):
            try:
                price = float(message.text)
                await state.update_data(price=price)
                await message.answer(
                    """
⏱ <b>Введите количество минут:</b>
• Формат: целое число
• Пример: 25 или 60
• Минимально: 15 минут
                    """.strip(),
                    parse_mode=ParseMode.HTML
                )
                await state.set_state(AdminStates.adding_tariff_minutes)
            except:
                await message.answer(
                    """
❌ <b>Неверный формат цены!</b>

💰 <b>Правильный формат:</b>
• Только числа
• Точка для десятичных
• Пример: 5.0

🔄 <b>Попробуйте снова:</b>
                    """.strip(),
                    parse_mode=ParseMode.HTML
                )

        @dp.message(AdminStates.adding_tariff_minutes)
        async def add_tariff_minutes(message: types.Message, state: FSMContext):
            try:
                minutes = int(message.text)
                data = await state.get_data()

                tariff_id = db.add_tariff(data['name'], data['price'], minutes)
                db.add_log(message.from_user.id, "tariff_added", f"Тариф: {data['name']}")

                await message.answer(
                    f"""
✅ <b>Тариф успешно добавлен!</b>

🎉 <b>Детали нового тарифа:</b>
📋 <b>Название:</b> {data['name']}
💰 <b>Цена:</b> {data['price']}$
⏱ <b>Время:</b> {minutes} минут
🆔 <b>ID тарифа:</b> {tariff_id}
📊 <b>Статус:</b> 🟢 АКТИВЕН

✨ <b>Тариф теперь доступен для клиентов!</b>
                    """.strip(),
                    parse_mode=ParseMode.HTML
                )
                await state.clear()
            except:
                await message.answer(
                    """
❌ <b>Ошибка добавления тарифа!</b>

🔄 <b>Попробуйте снова:</b>
1. Проверьте корректность данных
2. Убедитесь в уникальности названия
3. Обратитесь к технической поддержке
                    """.strip(),
                    parse_mode=ParseMode.HTML
                )

        @dp.callback_query(F.data == "edit_tariff_menu")
        async def edit_tariff_menu(callback: types.CallbackQuery):
            tariffs = db.get_all_tariffs()

            builder = InlineKeyboardBuilder()
            for tariff in tariffs:
                status = "🟢" if tariff['is_active'] else "🔴"
                builder.button(
                    text=f"{status} {tariff['name']} - {tariff['price']}$",
                    callback_data=f"select_tariff_{tariff['id']}"
                )
            builder.button(text="🔙 Назад", callback_data="back_to_tariffs")
            builder.adjust(1)

            await callback.message.edit_text(
                """
⚙️ <b>Редактирование тарифа</b>

👇 <b>Выберите тариф для редактирования:</b>
                """.strip(),
                reply_markup=builder.as_markup(),
                parse_mode=ParseMode.HTML
            )
            await callback.answer()

        @dp.callback_query(F.data.startswith("select_tariff_"))
        async def select_tariff(callback: types.CallbackQuery):
            tariff_id = int(callback.data.split("_")[2])
            tariff = db.get_tariff(tariff_id)

            builder = InlineKeyboardBuilder()

            # Кнопки управления статусом
            if tariff['is_active']:
                builder.button(text="🔴 Выключить тариф", callback_data=f"toggle_tariff_{tariff_id}")
            else:
                builder.button(text="🟢 Включить тариф", callback_data=f"toggle_tariff_{tariff_id}")

            # Кнопки редактирования
            builder.button(text="✏️ Изменить название", callback_data=f"change_name_{tariff_id}")
            builder.button(text="💰 Изменить цену", callback_data=f"change_price_{tariff_id}")
            builder.button(text="⏱ Изменить время", callback_data=f"change_minutes_{tariff_id}")
            builder.button(text="🗑️ Удалить тариф", callback_data=f"delete_tariff_{tariff_id}")
            builder.button(text="🔙 Назад", callback_data="edit_tariff_menu")
            builder.adjust(2, 2, 1)

            status = "🟢 АКТИВЕН" if tariff['is_active'] else "🔴 ВЫКЛЮЧЕН"

            await callback.message.edit_text(
                f"""
⚙️ <b>Управление тарифом</b>

{format_tariff(tariff)}

📊 <b>Статус:</b> {status}

👇 <b>Выберите действие:</b>
                """.strip(),
                reply_markup=builder.as_markup(),
                parse_mode=ParseMode.HTML
            )
            await callback.answer()

        @dp.callback_query(F.data.startswith("toggle_tariff_"))
        async def toggle_tariff(callback: types.CallbackQuery):
            tariff_id = int(callback.data.split("_")[2])
            tariff = db.get_tariff(tariff_id)

            new_status = not tariff['is_active']
            db.update_tariff(tariff_id, is_active=new_status)

            status_text = "🟢 ВКЛЮЧЕН" if new_status else "🔴 ВЫКЛЮЧЕН"
            action_text = "включен" if new_status else "выключен"

            db.add_log(callback.from_user.id, "tariff_toggled", f"Тариф {tariff['name']} {action_text}")

            await callback.message.edit_text(
                f"""
✅ <b>Статус тарифа изменен!</b>

📋 <b>Тариф:</b> {tariff['name']}
🔄 <b>Новый статус:</b> {status_text}

{'✨ Теперь тариф доступен для клиентов!' if new_status else '⏸️ Тариф временно недоступен для клиентов.'}
                """.strip(),
                parse_mode=ParseMode.HTML
            )
            await callback.answer()

        @dp.callback_query(F.data.startswith("delete_tariff_"))
        async def delete_tariff_confirm(callback: types.CallbackQuery):
            tariff_id = int(callback.data.split("_")[2])
            tariff = db.get_tariff(tariff_id)

            builder = InlineKeyboardBuilder()
            builder.button(text="✅ Да, удалить", callback_data=f"confirm_delete_{tariff_id}")
            builder.button(text="❌ Нет, отменить", callback_data=f"select_tariff_{tariff_id}")
            builder.adjust(2)

            await callback.message.edit_text(
                f"""
⚠️ <b>Подтверждение удаления</b>

❗ <b>Внимание!</b> Это действие нельзя отменить!

📋 <b>Тариф для удаления:</b>
{format_tariff(tariff)}

❓ <b>Вы уверены, что хотите удалить этот тариф?</b>
                """.strip(),
                reply_markup=builder.as_markup(),
                parse_mode=ParseMode.HTML
            )
            await callback.answer()

        @dp.callback_query(F.data.startswith("confirm_delete_"))
        async def confirm_delete_tariff(callback: types.CallbackQuery):
            tariff_id = int(callback.data.split("_")[2])
            tariff = db.get_tariff(tariff_id)

            db.delete_tariff(tariff_id)
            db.add_log(callback.from_user.id, "tariff_deleted", f"Тариф: {tariff['name']}")

            await callback.message.edit_text(
                f"""
🗑️ <b>Тариф успешно удален!</b>

📋 <b>Удаленный тариф:</b> {tariff['name']}
💰 <b>Цена:</b> {tariff['price']}$
⏱ <b>Время:</b> {tariff['duration_minutes']} минут

✅ <b>Тариф больше не доступен для выбора.</b>
                """.strip(),
                parse_mode=ParseMode.HTML
            )
            await callback.answer()

        @dp.callback_query(F.data.startswith("change_name_"))
        async def change_tariff_name(callback: types.CallbackQuery, state: FSMContext):
            tariff_id = int(callback.data.split("_")[2])
            await state.update_data(tariff_id=tariff_id, action="change_name")

            await callback.message.edit_text(
                """
✏️ <b>Изменение названия тарифа</b>

📝 <b>Введите новое название:</b>
• Используйте эмодзи для наглядности
• Название должно быть уникальным
• Пример: «🚀 Премиум Плюс»
                """.strip(),
                parse_mode=ParseMode.HTML
            )
            await state.set_state(AdminStates.editing_tariff_name)
            await callback.answer()

        @dp.message(AdminStates.editing_tariff_name)
        async def process_new_name(message: types.Message, state: FSMContext):
            data = await state.get_data()
            tariff_id = data['tariff_id']

            db.update_tariff(tariff_id, name=message.text)
            db.add_log(message.from_user.id, "tariff_updated", f"Изменено название тарифа #{tariff_id}")

            await message.answer(
                f"""
✅ <b>Название тарифа изменено!</b>

📋 <b>Новое название:</b> {message.text}

✨ <b>Изменения применены успешно!</b>
                """.strip(),
                parse_mode=ParseMode.HTML
            )
            await state.clear()

        @dp.callback_query(F.data.startswith("change_price_"))
        async def change_tariff_price(callback: types.CallbackQuery, state: FSMContext):
            tariff_id = int(callback.data.split("_")[2])
            await state.update_data(tariff_id=tariff_id, action="change_price")

            await callback.message.edit_text(
                """
💰 <b>Изменение цены тарифа</b>

💵 <b>Введите новую цену:</b>
• Формат: число с точкой
• Пример: 5.0 или 7.5
• Цена в долларах ($)
                """.strip(),
                parse_mode=ParseMode.HTML
            )
            await state.set_state(AdminStates.editing_tariff_price)
            await callback.answer()

        @dp.message(AdminStates.editing_tariff_price)
        async def process_new_price(message: types.Message, state: FSMContext):
            try:
                price = float(message.text)
                data = await state.get_data()
                tariff_id = data['tariff_id']

                db.update_tariff(tariff_id, price=price)
                db.add_log(message.from_user.id, "tariff_updated", f"Изменена цена тарифа #{tariff_id}")

                await message.answer(
                    f"""
✅ <b>Цена тарифа изменена!</b>

💰 <b>Новая цена:</b> {price}$

✨ <b>Изменения применены успешно!</b>
                    """.strip(),
                    parse_mode=ParseMode.HTML
                )
                await state.clear()
            except:
                await message.answer(
                    """
❌ <b>Неверный формат цены!</b>

🔄 <b>Попробуйте снова:</b>
1. Используйте только числа
2. Точка для десятичных
3. Пример: 5.0
                    """.strip(),
                    parse_mode=ParseMode.HTML
                )

        @dp.callback_query(F.data.startswith("change_minutes_"))
        async def change_tariff_minutes(callback: types.CallbackQuery, state: FSMContext):
            tariff_id = int(callback.data.split("_")[2])
            await state.update_data(tariff_id=tariff_id, action="change_minutes")

            await callback.message.edit_text(
                """
⏱ <b>Изменение времени тарифа</b>

⏰ <b>Введите новое количество минут:</b>
• Формат: целое число
• Пример: 25 или 60
• Минимально: 15 минут
                """.strip(),
                parse_mode=ParseMode.HTML
            )
            await state.set_state(AdminStates.editing_tariff_minutes)
            await callback.answer()

        @dp.message(AdminStates.editing_tariff_minutes)
        async def process_new_minutes(message: types.Message, state: FSMContext):
            try:
                minutes = int(message.text)
                data = await state.get_data()
                tariff_id = data['tariff_id']

                db.update_tariff(tariff_id, duration_minutes=minutes)
                db.add_log(message.from_user.id, "tariff_updated", f"Изменено время тарифа #{tariff_id}")

                await message.answer(
                    f"""
✅ <b>Время тарифа изменено!</b>

⏱ <b>Новое время:</b> {minutes} минут

✨ <b>Изменения применены успешно!</b>
                    """.strip(),
                    parse_mode=ParseMode.HTML
                )
                await state.clear()
            except:
                await message.answer(
                    """
❌ <b>Неверный формат времени!</b>

🔄 <b>Попробуйте снова:</b>
1. Используйте только целые числа
2. Пример: 25
3. Минимум 15 минут
                    """.strip(),
                    parse_mode=ParseMode.HTML
                )

        @dp.callback_query(F.data == "view_tariffs")
        async def view_tariffs_list(callback: types.CallbackQuery):
            tariffs = db.get_all_tariffs()

            text = """
📋 <b>Список всех тарифов</b>

            """.strip()

            for tariff in tariffs:
                status = "🟢 АКТИВЕН" if tariff['is_active'] else "🔴 ВЫКЛЮЧЕН"
                text += f"\n{format_tariff(tariff)}\n"
                text += f"📊 Статус: {status}\n"
                text += "─" * 40 + "\n"

            builder = InlineKeyboardBuilder()
            builder.button(text="⚙️ Управление тарифами", callback_data="back_to_tariffs")
            builder.adjust(1)

            await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)
            await callback.answer()

        @dp.callback_query(F.data == "back_to_tariffs")
        async def back_to_tariffs_management(callback: types.CallbackQuery):
            await manage_tariffs(callback.message)
            await callback.answer()

        # ========== СИСТЕМНЫЕ ЛОГИ ==========
        @dp.message(F.text == "📝 Системные логи")
        async def show_logs(message: types.Message):
            if not is_moderator(message.from_user.id):
                return

            logs = db.get_logs(1, 20)

            if not logs:
                await message.answer(
                    """
📭 <b>Нет логов за сегодня</b>

✅ <b>Система работает стабильно!</b>

🔄 <b>Последние действия будут отображены здесь.</b>
                    """.strip(),
                    parse_mode=ParseMode.HTML
                )
                return

            text = """
📝 <b>Системные логи (за сегодня)</b>

🔄 <b>Последние действия в системе:</b>

            """.strip()

            for log in logs:
                time = log['created_at'][11:16]
                user = log['full_name'] or "Система"
                text += f"\n🕒 <b>{time}</b>\n👤 {user}\n📋 {log['action']}\n"
                if log['details']:
                    text += f"📝 {log['details'][:50]}\n"
                text += "─" * 30 + "\n"

            builder = InlineKeyboardBuilder()
            builder.button(text="📅 За неделю", callback_data="logs_week")
            builder.button(text="📅 За месяц", callback_data="logs_month")
            builder.adjust(2)

            await message.answer(text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)

        # ========== УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ ==========
        @dp.message(F.text == "👥 Управление пользователями")
        async def manage_users(message: types.Message):
            if not is_owner(message.from_user.id):
                await message.answer("🔒 <b>Доступ только для владельца!</b>", parse_mode=ParseMode.HTML)
                return

            users = db.get_all_users()

            text = """
👥 <b>Управление пользователями</b>

📋 <b>Список всех пользователей:</b>

            """.strip()

            for user in users[:15]:
                role_icons = {
                    'user': '👤',
                    'moderator': '🛡️',
                    'admin': '⚙️',
                    'owner': '👑'
                }
                icon = role_icons.get(user['role'], '❓')
                text += f"\n{icon} <b>{user['full_name']}</b>\n"
                text += f"👤 @{user['username'] or 'без username'}\n"
                text += f"🆔 ID: <code>{user['telegram_id']}</code>\n"
                text += f"🎖️ Роль: {user['role']}\n"
                text += "─" * 30 + "\n"

            if len(users) > 15:
                text += f"\n📊 <b>Всего пользователей:</b> {len(users)}"

            text += "\n\n🔧 <b>Для изменения роли пользователя:</b>\n"
            text += "Используйте команду /role ID_пользователя новая_роль\n\n"
            text += "🎖️ <b>Доступные роли:</b>\n"
            text += "• user - обычный пользователь\n"
            text += "• moderator - модератор (может обрабатывать заявки)\n"
            text += "• admin - администратор (полные права)\n"
            text += "• owner - владелец (нельзя изменить)"

            await message.answer(text, parse_mode=ParseMode.HTML)

        # ========== КОМАНДА /role ==========
        @dp.message(Command("role"))
        async def change_user_role(message: types.Message):
            if not is_owner(message.from_user.id):
                return

            try:
                parts = message.text.split()
                if len(parts) != 3:
                    await message.answer(
                        """
❌ <b>Неверный формат команды!</b>

📝 <b>Правильный формат:</b>
/role ID_пользователя новая_роль

🎖️ <b>Доступные роли:</b>
• user - обычный пользователь
• moderator - модератор
• admin - администратор

📌 <b>Пример:</b>
/role 123456789 moderator
                        """.strip(),
                        parse_mode=ParseMode.HTML
                    )
                    return

                user_id = int(parts[1])
                role = parts[2].lower()

                if role not in ['user', 'moderator', 'admin']:
                    await message.answer(
                        """
❌ <b>Неверная роль!</b>

🎖️ <b>Доступные роли:</b>
• user - обычный пользователь
• moderator - модератор
• admin - администратор

⚠️ <b>Роль "owner" нельзя назначить через команду!</b>
                        """.strip(),
                        parse_mode=ParseMode.HTML
                    )
                    return

                db.update_user_role(user_id, role)
                db.add_log(message.from_user.id, "role_changed", f"ID {user_id} -> {role}")

                await message.answer(
                    f"""
✅ <b>Роль пользователя изменена!</b>

🆔 <b>ID пользователя:</b> {user_id}
🎖️ <b>Новая роль:</b> {role}

✨ <b>Изменения применены успешно!</b>
                    """.strip(),
                    parse_mode=ParseMode.HTML
                )
            except ValueError:
                await message.answer("❌ <b>Неверный ID пользователя!</b>", parse_mode=ParseMode.HTML)
            except Exception as e:
                await message.answer(f"❌ <b>Ошибка:</b> {str(e)}", parse_mode=ParseMode.HTML)

        # ========== МАССОВАЯ РАССЫЛКА ==========
        @dp.message(F.text == "📢 Массовая рассылка")
        async def broadcast_menu(message: types.Message, state: FSMContext):
            if not is_owner(message.from_user.id):
                await message.answer("🔒 <b>Доступ только для владельца!</b>", parse_mode=ParseMode.HTML)
                return

            await message.answer(
                """
📢 <b>Массовая рассылка сообщений</b>

✉️ <b>Введите сообщение для рассылки:</b>
• Сообщение будет отправлено всем пользователям
• Используйте форматирование HTML
• Будьте внимательны с содержанием

👇 <b>Отправьте текст сообщения:</b>
                """.strip(),
                parse_mode=ParseMode.HTML
            )
            await state.set_state(AdminStates.broadcast_all)

        @dp.message(AdminStates.broadcast_all)
        async def send_broadcast(message: types.Message, state: FSMContext):
            users = db.get_all_users()
            success = 0
            failed = 0

            await message.answer(
                f"""
🔄 <b>Начинаю рассылку...</b>

📊 <b>Статистика:</b>
• 👥 Получателей: {len(users)}
• 📱 Отправка сообщений...
• ⏳ Ожидайте завершения
                """.strip(),
                parse_mode=ParseMode.HTML
            )

            for user in users:
                try:
                    await bot.send_message(
                        user['telegram_id'],
                        f"""
📢 <b>Сообщение от администратора</b>

{message.text}

---
🤖 <b>Автоматическое уведомление</b>
                        """.strip(),
                        parse_mode=ParseMode.HTML
                    )
                    success += 1
                    await asyncio.sleep(0.1)  # Задержка чтобы не попасть в лимиты
                except:
                    failed += 1

            db.add_log(message.from_user.id, "broadcast_sent", f"Успешно: {success}, Неудачно: {failed}")

            await message.answer(
                f"""
✅ <b>Рассылка завершена!</b>

📊 <b>Результаты рассылки:</b>
• ✅ Успешно отправлено: {success}
• ❌ Не удалось отправить: {failed}
• 📈 Эффективность: {(success / len(users) * 100 if users else 0):.1f}%

✨ <b>Работа завершена успешно!</b>
                """.strip(),
                parse_mode=ParseMode.HTML
            )
            await state.clear()

        # ========== ФИНАНСОВЫЕ ОТЧЕТЫ ==========
        @dp.message(F.text == "📄 Финансовые отчеты")
        async def financial_reports(message: types.Message, state: FSMContext):
            if not is_owner(message.from_user.id):
                await message.answer("🔒 <b>Доступ только для владельца!</b>", parse_mode=ParseMode.HTML)
                return

            await message.answer(
                """
📄 <b>Финансовые отчеты</b>

📅 <b>Введите дату для просмотра отчета:</b>
• Формат: ДД.ММ.ГГГГ
• Пример: 15.01.2024
• Можно выбрать любую дату

👇 <b>Отправьте дату:</b>
                """.strip(),
                parse_mode=ParseMode.HTML
            )
            await state.set_state(AdminStates.waiting_report_date)

        @dp.message(AdminStates.waiting_report_date)
        async def show_financial_report(message: types.Message, state: FSMContext):
            try:
                date_obj = datetime.strptime(message.text, '%d.%m.%Y')
                date_str = date_obj.strftime('%Y-%m-%d')
            except:
                await message.answer(
                    """
❌ <b>Неверный формат даты!</b>

📅 <b>Правильный формат:</b>
ДД.ММ.ГГГГ

📌 <b>Примеры:</b>
• 15.01.2024
• 01.12.2023
• 25.06.2024

🔄 <b>Попробуйте снова:</b>
                    """.strip(),
                    parse_mode=ParseMode.HTML
                )
                return

            reports = db.get_reports_by_date(date_str)

            if not reports:
                await message.answer(
                    f"""
📭 <b>Нет отчетов за указанную дату</b>

📅 <b>Дата:</b> {message.text}

🔄 <b>Попробуйте другую дату или убедитесь в корректности данных.</b>
                    """.strip(),
                    parse_mode=ParseMode.HTML
                )
                await state.clear()
                return

            total_amount = sum(report['amount'] for report in reports)
            paid_count = sum(1 for report in reports if report['status'] == 'paid')
            pending_count = len(reports) - paid_count

            text = f"""
📄 <b>Финансовый отчет</b>

📅 <b>Дата:</b> {message.text}
📊 <b>Общая статистика:</b>
• 📋 Всего отчетов: {len(reports)}
• ✅ Выплачено: {paid_count}
• ⏳ Ожидают выплаты: {pending_count}
• 💰 Общая сумма: {total_amount:.2f}$

📋 <b>Детали отчетов:</b>

            """.strip()

            for report in reports[:10]:
                status = "✅ Выплачено" if report['status'] == 'paid' else "⏳ Ожидает"
                text += f"\n🔹 <b>Отчет #{report['id']}</b>\n"
                text += f"📱 Номер: <code>{report['phone_number']}</code>\n"
                text += f"👤 Клиент: {report['full_name']}\n"
                text += f"💰 Сумма: {report['amount']}$\n"
                text += f"📊 Статус: {status}\n"
                text += f"📅 Дата: {report['created_at'][:16]}\n"
                text += "─" * 30 + "\n"

            if len(reports) > 10:
                text += f"\n📊 <b>И ещё {len(reports) - 10} отчетов...</b>"

            builder = InlineKeyboardBuilder()
            builder.button(text="💾 Экспорт в CSV", callback_data=f"export_report_{date_str}")
            builder.adjust(1)

            await message.answer(text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)
            await state.clear()

        # ========== ОБРАБОТКА ВЗЯТИЯ НОМЕРА ==========
        @dp.callback_query(F.data.startswith("take_"))
        async def take_number(callback: types.CallbackQuery, state: FSMContext):
            if not is_moderator(callback.from_user.id):
                await callback.answer("🔒 Доступ запрещен!")
                return

            request_id = int(callback.data.split("_")[1])
            request = db.get_request(request_id)

            if not request:
                await callback.answer("❌ Заявка не найдена!")
                return

            # НЕ обновляем статус здесь - только после отправки фото
            db.add_log(callback.from_user.id, "request_taken", f"Заявка #{request_id}")

            try:
                await bot.send_message(
                    request['telegram_id'],
                    f"""
✅ <b>Ваш номер взят в работу!</b>

🎉 <b>Отличные новости!</b>
Ваша заявка #{request_id} принята оператором.

📱 <b>Номер:</b> <code>{request['phone_number']}</code>
💰 <b>Тариф:</b> {request['tariff_name']}
⏰ <b>Время принятия:</b> {datetime.now().strftime('%H:%M %d.%m.%Y')}

🔄 <b>Что дальше?</b>
• Ожидайте код от оператора
• Проверяйте уведомления
• Будьте на связи

⏳ <b>Код будет отправлен в течение 5-15 минут.</b>
                    """.strip(),
                    parse_mode=ParseMode.HTML
                )
            except:
                pass

            await callback.message.edit_text(
                f"""
✅ <b>Номер взят в работу!</b>

🎯 <b>Детали заявки:</b>
🆔 <b>Номер заявки:</b> #{request_id}
📱 <b>Телефон:</b> <code>{request['phone_number']}</code>
👤 <b>Клиент:</b> {request['full_name']}

👇 <b>Теперь отправьте фото с кодом для этого номера:</b>
                """.strip(),
                parse_mode=ParseMode.HTML
            )
            await state.update_data(request_id=request_id)
            await state.set_state(AdminStates.waiting_photo_code)
            await callback.answer()

        # ========== ОТПРАВКА ФОТО С КОДОМ ==========
        @dp.message(AdminStates.waiting_photo_code, F.photo)
        async def send_photo_code(message: types.Message, state: FSMContext):
            if not is_moderator(message.from_user.id):
                return

            data = await state.get_data()
            request_id = data['request_id']
            request = db.get_request(request_id)

            if not request:
                await message.answer("❌ <b>Заявка не найдена!</b>", parse_mode=ParseMode.HTML)
                await state.clear()
                return

            # Получаем file_id фото
            photo_id = message.photo[-1].file_id

            try:
                # Отправляем фото клиенту напрямую по file_id
                await bot.send_photo(
                    request['telegram_id'],
                    photo=photo_id,
                    caption=f"""
✅ <b>Код для вашего номера готов!</b>

🎉 <b>Поздравляем!</b>
Ваш номер успешно активирован.

📱 <b>Номер:</b> <code>{request['phone_number']}</code>
💰 <b>Тариф:</b> {request['tariff_name']} - {request['price']}$
⏱ <b>Время:</b> {request['duration_minutes']} минут
🆔 <b>Номер заявки:</b> #{request_id}

🚀 <b>Номер готов к работе!</b>
💡 <b>Рекомендации:</b>
• Следите за уведомлениями
• Сообщайте о проблемах оператору
• Будьте на связи

📞 <b>Техническая поддержка:</b> @galactika_work_support
                    """.strip(),
                    parse_mode=ParseMode.HTML
                )

                # Обновляем статус в базе
                db.update_request_status(request_id, 'accepted', message.from_user.id, photo=photo_id)
                db.add_log(message.from_user.id, "photo_sent", f"Фото отправлено для заявки #{request_id}")

                await message.answer(
                    """
✅ <b>Фото с кодом успешно отправлено!</b>

🎯 <b>Клиент получил:</b>
• Фото с кодом активации
• Инструкцию по использованию
• Контакт поддержки

✨ <b>Работа с заявкой завершена успешно!</b>
                    """.strip(),
                    parse_mode=ParseMode.HTML
                )
            except Exception as e:
                logger.error(f"Ошибка отправки фото: {e}")
                await message.answer(
                    f"""
⚠️ <b>Ошибка отправки фото!</b>

❌ <b>Не удалось отправить фото клиенту:</b>
{str(e)}

🔄 <b>Попробуйте:</b>
1. Проверить подключение
2. Отправить фото ещё раз
3. Обратиться к технической поддержке
                    """.strip(),
                    parse_mode=ParseMode.HTML
                )
            finally:
                await state.clear()

        # ========== ОТКЛОНЕНИЕ ЗАЯВКИ ==========
        @dp.callback_query(F.data.startswith("reject_"))
        async def reject_number_menu(callback: types.CallbackQuery):
            if not is_moderator(callback.from_user.id):
                await callback.answer("🔒 Доступ запрещен!")
                return

            request_id = int(callback.data.split("_")[1])

            builder = InlineKeyboardBuilder()
            builder.button(text="❌ Неверный формат номера", callback_data=f"reason_{request_id}_format")
            builder.button(text="📵 Номер уже использован", callback_data=f"reason_{request_id}_used")
            builder.button(text="💰 Тариф недоступен", callback_data=f"reason_{request_id}_tariff")
            builder.button(text="⏱ Превышено время", callback_data=f"reason_{request_id}_time")
            builder.button(text="✍️ Другая причина", callback_data=f"reason_{request_id}_other")
            builder.button(text="🔙 Назад", callback_data=f"back_{request_id}")
            builder.adjust(2, 2, 1, 1)

            await callback.message.edit_text(
                """
❌ <b>Отклонение заявки</b>

📝 <b>Выберите причину отклонения:</b>
• ❌ Неверный формат - номер не соответствует требованиям
• 📵 Номер использован - номер уже в работе
• 💰 Тариф недоступен - выбранный тариф временно недоступен
• ⏱ Превышено время - клиент не успел обработать
• ✍️ Другая причина - укажите свою причину

👇 <b>Выберите причину:</b>
                """.strip(),
                reply_markup=builder.as_markup(),
                parse_mode=ParseMode.HTML
            )
            await callback.answer()

        @dp.callback_query(F.data.startswith("reason_"))
        async def process_rejection(callback: types.CallbackQuery):
            _, request_id, reason_type = callback.data.split("_")
            request_id = int(request_id)
            request = db.get_request(request_id)

            if reason_type == 'other':
                await callback.message.edit_text(
                    """
✍️ <b>Укажите причину отклонения:</b>

📝 <b>Введите текст причины:</b>
• Будет отправлено клиенту
• Будьте вежливы и конкретны
• Укажите рекомендации

👇 <b>Отправьте текст причины:</b>
                    """.strip(),
                    parse_mode=ParseMode.HTML
                )
                pending_requests[callback.from_user.id] = {'request_id': request_id, 'action': 'reject'}
                await callback.answer()
                return

            reason_text = {
                'format': "❌ Неверный формат номера. Пожалуйста, проверьте номер и попробуйте снова.",
                'used': "📵 Этот номер уже используется в системе. Пожалуйста, укажите другой номер.",
                'tariff': "💰 Выбранный тариф временно недоступен. Пожалуйста, выберите другой тариф.",
                'time': "⏱ Превышено время обработки. Пожалуйста, создайте новую заявку."
            }.get(reason_type, "Заявка отклонена по техническим причинам.")

            db.update_request_status(request_id, 'rejected', callback.from_user.id, reason=reason_text)
            db.add_log(callback.from_user.id, "request_rejected", f"Заявка #{request_id}, причина: {reason_type}")

            try:
                await bot.send_message(
                    request['telegram_id'],
                    f"""
❌ <b>Заявка отклонена</b>

😔 <b>К сожалению, ваша заявка #{request_id} была отклонена.</b>

📱 <b>Номер:</b> <code>{request['phone_number']}</code>
💰 <b>Тариф:</b> {request['tariff_name']}

📝 <b>Причина отклонения:</b>
{reason_text}

🔄 <b>Что делать?</b>
• Проверьте правильность данных
• Создайте новую заявку при необходимости
• Обратитесь к поддержке при вопросах

📞 <b>Техническая поддержка:</b> @galactika_work_support
                    """.strip(),
                    parse_mode=ParseMode.HTML
                )
            except:
                pass

            await callback.message.edit_text(
                f"""
✅ <b>Заявка отклонена!</b>

🆔 <b>Номер заявки:</b> #{request_id}
👤 <b>Клиент:</b> {request['full_name']}
📝 <b>Причина:</b> {reason_text[:50]}...

✨ <b>Клиент уведомлен об отказе.</b>
                """.strip(),
                parse_mode=ParseMode.HTML
            )
            await callback.answer()

        @dp.message(
            lambda m: m.from_user.id in pending_requests and pending_requests[m.from_user.id].get('action') == 'reject')
        async def process_custom_rejection(message: types.Message):
            if message.from_user.id not in pending_requests:
                return

            data = pending_requests[message.from_user.id]
            request_id = data['request_id']
            request = db.get_request(request_id)

            db.update_request_status(request_id, 'rejected', message.from_user.id, reason=message.text)
            db.add_log(message.from_user.id, "request_rejected_custom", f"Заявка #{request_id}")

            try:
                await bot.send_message(
                    request['telegram_id'],
                    f"""
❌ <b>Заявка отклонена</b>

😔 <b>К сожалению, ваша заявка #{request_id} была отклонена.</b>

📱 <b>Номер:</b> <code>{request['phone_number']}</code>
💰 <b>Тариф:</b> {request['tariff_name']}

📝 <b>Причина отклонения:</b>
{message.text}

🔄 <b>Что делать?</b>
• Проверьте правильность данных
• Создайте новую заявку при необходимости
• Обратитесь к поддержке при вопросах

📞 <b>Техническая поддержка:</b> @galactika_work_support
                    """.strip(),
                    parse_mode=ParseMode.HTML
                )
            except:
                pass

            await message.answer(
                f"""
✅ <b>Заявка отклонена с вашей причиной!</b>

🆔 <b>Номер заявки:</b> #{request_id}
👤 <b>Клиент:</b> {request['full_name']}
📝 <b>Причина:</b> {message.text[:50]}...

✨ <b>Клиент уведомлен об отказе.</b>
                """.strip(),
                parse_mode=ParseMode.HTML
            )
            del pending_requests[message.from_user.id]

        # ========== НАПИСАТЬ КЛИЕНТУ ==========
        @dp.callback_query(F.data.startswith("message_"))
        async def message_user_menu(callback: types.CallbackQuery, state: FSMContext):
            request_id = int(callback.data.split("_")[1])
            request = db.get_request(request_id)

            await state.update_data(
                target_user_id=request['telegram_id'],
                request_id=request_id
            )

            await callback.message.edit_text(
                f"""
✉️ <b>Отправка сообщения клиенту</b>

👤 <b>Клиент:</b> {request['full_name']}
📱 <b>Номер:</b> <code>{request['phone_number']}</code>
💰 <b>Тариф:</b> {request['tariff_name']}
🆔 <b>Номер заявки:</b> #{request_id}

📝 <b>Введите сообщение для клиента:</b>
• Сообщение будет отправлено от имени администратора
• Используйте вежливый тон
• Указывайте конкретную информацию

👇 <b>Отправьте текст сообщения:</b>
                """.strip(),
                parse_mode=ParseMode.HTML
            )
            await state.set_state(AdminStates.waiting_message_for_user)
            await callback.answer()

        @dp.message(AdminStates.waiting_message_for_user)
        async def send_user_message(message: types.Message, state: FSMContext):
            data = await state.get_data()
            target_id = data['target_user_id']
            request_id = data['request_id']
            request = db.get_request(request_id)

            try:
                await bot.send_message(
                    target_id,
                    f"""
📱 <b>Сообщение от администратора</b>

👋 <b>Уважаемый клиент!</b>

📋 <b>По вашей заявке #{request_id}</b>
📱 <b>Номер:</b> <code>{request['phone_number']}</code>

💬 <b>Сообщение:</b>
{message.text}

---
🤖 <b>Автоматическое уведомление</b>
📞 <b>Поддержка:</b> @galactika_work_support
                    """.strip(),
                    parse_mode=ParseMode.HTML
                )

                await message.answer(
                    """
✅ <b>Сообщение успешно отправлено!</b>

👤 <b>Клиент получил ваше сообщение.</b>

✨ <b>Коммуникация установлена успешно!</b>
                    """.strip(),
                    parse_mode=ParseMode.HTML
                )
                db.add_log(message.from_user.id, "message_sent", f"Клиенту {target_id}")
            except:
                await message.answer(
                    """
❌ <b>Не удалось отправить сообщение!</b>

⚠️ <b>Возможные причины:</b>
• Клиент заблокировал бота
• Технические проблемы
• Ошибка подключения

🔄 <b>Попробуйте:</b>
1. Проверить подключение
2. Отправить позже
3. Связаться другим способом
                    """.strip(),
                    parse_mode=ParseMode.HTML
                )

            await state.clear()

        # ========== ОТМЕНА ДЕЙСТВИЙ ==========
        @dp.callback_query(F.data == "cancel")
        async def cancel_action(callback: types.CallbackQuery, state: FSMContext):
            await callback.message.edit_text(
                """
❌ <b>Действие отменено</b>

🔄 <b>Возвращаюсь в главное меню...</b>
                """.strip(),
                parse_mode=ParseMode.HTML
            )
            await state.clear()
            await callback.answer()

        @dp.callback_query(F.data.startswith("back_"))
        async def back_to_request(callback: types.CallbackQuery):
            request_id = int(callback.data.split("_")[1])
            request = db.get_request(request_id)

            if not request:
                await callback.message.edit_text("❌ Заявка не найдена!")
                await callback.answer()
                return

            builder = InlineKeyboardBuilder()
            builder.button(text="✅ Взять номер", callback_data=f"take_{request_id}")
            builder.button(text="❌ Отклонить", callback_data=f"reject_{request_id}")
            builder.adjust(2)

            await callback.message.edit_text(
                f"""
🔄 <b>Возврат к заявке</b>

{format_request(request)}

👇 <b>Выберите действие:</b>
                """.strip(),
                reply_markup=builder.as_markup(),
                parse_mode=ParseMode.HTML
            )
            await callback.answer()

        # ========== ЗАПУСК БОТА ==========
        print("=" * 70)
        print("✨" + " " * 30 + "🤖" + " " * 30 + "✨")
        print("🎉" + " " * 28 + "БОТ ЗАПУЩЕН" + " " * 28 + "🎉")
        print("✨" + " " * 30 + "🤖" + " " * 30 + "✨")
        print("=" * 70)
        print("\n✅ ВСЕ ФУНКЦИИ АКТИВНЫ:")
        print("📱 1. Сдача номера с красивым интерфейсом")
        print("💰 2. Полное управление тарифами (вкл/выкл/редактирование)")
        print("✅ 3. Взятие номера с отправкой кода (ИСПРАВЛЕНО!)")
        print("❌ 4. Отклонение заявок с причинами")
        print("📊 5. Детальная статистика и аналитика")
        print("👥 6. Управление пользователями и правами")
        print("📢 7. Массовая рассылка сообщений")
        print("📄 8. Финансовые отчеты по датам")
        print("📝 9. Системные логи и мониторинг")
        print("📱 10. Управление номерами за сегодня")
        print("✅ 11. Статусы: ВСТАЛ/СЛЕТЕЛ/ОТСТОЯЛ")
        print("✉️ 12. Личные сообщения клиентам")
        print("=" * 70)
        print(f"\n👑 Администратор: {ADMIN_ID}")
        print("🚀 Бот готов к работе! Все системы функционируют нормально.")
        print("=" * 70)

        await dp.start_polling(bot)

    except Exception as e:
        logger.error(f"Ошибка запуска: {e}")
        print(f"\n❌ Критическая ошибка: {e}")
        print("\n🔧 Решения:")
        print("1. Проверьте токен бота в настройках")
        print("2. Установите библиотеки: pip install aiogram")
        print("3. Убедитесь в наличии интернет-соединения")
        print("4. Перезапустите бота")


if __name__ == "__main__":
    asyncio.run(main())

