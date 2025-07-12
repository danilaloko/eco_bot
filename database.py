import sqlite3
from datetime import datetime, timedelta
from typing import List, Tuple, Optional, Dict, Any
import pytz
import json
import logging

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_path: str = "eco_bot.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Инициализация базы данных с необходимыми таблицами"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Таблица пользователей с расширенной информацией
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    telegram_first_name TEXT,
                    telegram_last_name TEXT,
                    first_name TEXT,    
                    last_name TEXT,
                    participation_type TEXT DEFAULT 'individual',
                    family_members_count INTEGER DEFAULT 1,
                    children_info TEXT,
                    registration_completed BOOLEAN DEFAULT FALSE,
                    registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Таблица состояний пользователей для сохранения позиции в боте
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_states (
                    user_id INTEGER PRIMARY KEY,
                    current_state INTEGER DEFAULT 0,
                    context_data TEXT DEFAULT '{}',
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
            
            # Таблица заданий с временными рамками
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT,
                    link TEXT,
                    is_open BOOLEAN DEFAULT TRUE,
                    week_number INTEGER,
                    publication_date TIMESTAMP,
                    deadline TIMESTAMP,
                    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Таблица отправленных отчетов с типом отчета и локальными файлами
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS submissions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    task_id INTEGER,
                    submission_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    submission_type TEXT DEFAULT 'text',
                    content TEXT,
                    file_id TEXT,
                    file_path TEXT,
                    status TEXT DEFAULT 'pending',
                    is_on_time BOOLEAN DEFAULT TRUE,
                    FOREIGN KEY (user_id) REFERENCES users (user_id),
                    FOREIGN KEY (task_id) REFERENCES tasks (id)
                )
            ''')
            
            # Миграция: добавляем поле file_path если его нет
            try:
                cursor.execute('SELECT file_path FROM submissions LIMIT 1')
            except sqlite3.OperationalError:
                # Поле не существует, добавляем его
                cursor.execute('ALTER TABLE submissions ADD COLUMN file_path TEXT')
                logger.info("Добавлено поле file_path в таблицу submissions")
            
            # Миграция: добавляем поле open_date если его нет
            try:
                cursor.execute('SELECT open_date FROM tasks LIMIT 1')
            except sqlite3.OperationalError:
                # Поле не существует, добавляем его
                cursor.execute('ALTER TABLE tasks ADD COLUMN open_date TIMESTAMP')
                logger.info("Добавлено поле open_date в таблицу tasks")
            
            # Таблица обращений в поддержку
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS support_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    message TEXT,
                    request_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'open',
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
            
            # Таблица для сохранения необработанных сообщений (офлайн сообщения)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS offline_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    message_data TEXT,
                    message_type TEXT DEFAULT 'text',
                    received_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    processed BOOLEAN DEFAULT FALSE,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
            
            conn.commit()
    
    def save_user_state(self, user_id: int, state: int, context_data: Dict[str, Any] = None):
        """Сохраняет текущее состояние пользователя"""
        if context_data is None:
            context_data = {}
        
        context_json = json.dumps(context_data, ensure_ascii=False)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO user_states (user_id, current_state, context_data, last_updated)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ''', (user_id, state, context_json))
            conn.commit()
    
    def get_user_state(self, user_id: int) -> Tuple[int, Dict[str, Any]]:
        """Получает состояние пользователя"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT current_state, context_data FROM user_states WHERE user_id = ?
            ''', (user_id,))
            result = cursor.fetchone()
            
            if result:
                state, context_json = result
                try:
                    context_data = json.loads(context_json) if context_json else {}
                except json.JSONDecodeError:
                    context_data = {}
                return state, context_data
            else:
                return 0, {}
    
    def clear_user_state(self, user_id: int):
        """Очищает состояние пользователя (возвращает в главное меню)"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE user_states SET current_state = 0, context_data = '{}', last_updated = CURRENT_TIMESTAMP
                WHERE user_id = ?
            ''', (user_id,))
            if cursor.rowcount == 0:
                # Если записи нет, создаем новую
                cursor.execute('''
                    INSERT INTO user_states (user_id, current_state, context_data)
                    VALUES (?, 0, '{}')
                ''', (user_id,))
            conn.commit()
    
    def save_offline_message(self, user_id: int, message_data: str, message_type: str = 'text'):
        """Сохраняет сообщение, полученное в офлайн режиме"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO offline_messages (user_id, message_data, message_type)
                VALUES (?, ?, ?)
            ''', (user_id, message_data, message_type))
            conn.commit()
    
    def get_offline_messages(self, user_id: int) -> List[Tuple]:
        """Получает необработанные офлайн сообщения для пользователя"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, message_data, message_type, received_date
                FROM offline_messages 
                WHERE user_id = ? AND processed = FALSE
                ORDER BY received_date ASC
            ''', (user_id,))
            return cursor.fetchall()
    
    def mark_offline_message_processed(self, message_id: int):
        """Помечает офлайн сообщение как обработанное"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE offline_messages SET processed = TRUE WHERE id = ?
            ''', (message_id,))
            conn.commit()
    
    def add_user(self, user_id: int, username: str = None, telegram_first_name: str = None, telegram_last_name: str = None):
        """Добавляет нового пользователя или обновляет только telegram-данные существующего"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Проверяем, существует ли пользователь
            cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
            exists = cursor.fetchone()
            
            if exists:
                # Пользователь существует - обновляем только telegram-данные, не трогая регистрационные поля
                cursor.execute('''
                    UPDATE users 
                    SET username = ?, telegram_first_name = ?, telegram_last_name = ?
                    WHERE user_id = ?
                ''', (username, telegram_first_name, telegram_last_name, user_id))
            else:
                # Новый пользователь - создаем запись
                cursor.execute('''
                    INSERT INTO users (user_id, username, telegram_first_name, telegram_last_name)
                    VALUES (?, ?, ?, ?)
                ''', (user_id, username, telegram_first_name, telegram_last_name))
            
            conn.commit()
    
    def update_user_registration(self, user_id: int, first_name: str, last_name: str, 
                               participation_type: str, family_members_count: int = 1, 
                               children_info: str = None):
        """Обновляет информацию о регистрации пользователя"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users 
                SET first_name = ?, last_name = ?, participation_type = ?, 
                    family_members_count = ?, children_info = ?, registration_completed = 1 
                WHERE user_id = ?
            ''', (first_name, last_name, participation_type, family_members_count, children_info, user_id))
            conn.commit()
    
    def update_user_name(self, user_id: int, first_name: str, last_name: str):
        """Обновляет имя и фамилию пользователя"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users 
                SET first_name = ?, last_name = ? 
                WHERE user_id = ?
            ''', (first_name, last_name, user_id))
            conn.commit()
            logger.info(f"Обновлены имя и фамилия пользователя {user_id}: {first_name} {last_name}")
    
    def get_user(self, user_id: int) -> Optional[Tuple]:
        """Получает информацию о пользователе"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
            return cursor.fetchone()
    
    def is_user_registered(self, user_id: int) -> bool:
        """Проверяет, завершил ли пользователь регистрацию"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT registration_completed FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            return result and result[0]
    
    def get_current_week_tasks(self) -> List[Tuple]:
        """Возвращает задания текущей недели"""
        moscow_tz = pytz.timezone('Europe/Moscow')
        now = datetime.now(moscow_tz)
        
        # Вычисляем номер недели (для простоты используем номер недели в году)
        week_number = now.isocalendar()[1]
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, title, description, link, deadline FROM tasks 
                WHERE week_number = ? AND is_open = TRUE
            ''', (week_number,))
            return cursor.fetchall()
    
    def get_open_tasks(self) -> List[Tuple]:
        """Возвращает список открытых заданий текущей недели"""
        moscow_tz = pytz.timezone('Europe/Moscow')
        now = datetime.now(moscow_tz)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Получаем задания, которые еще не истекли
            cursor.execute('''
                SELECT id, title, description, link FROM tasks 
                WHERE is_open = TRUE AND (deadline IS NULL OR deadline > ?)
            ''', (now.isoformat(),))
            return cursor.fetchall()
    
    def get_all_tasks(self) -> List[Tuple]:
        """Возвращает все задания (открытые и архивные)"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT id, title, description, link, is_open FROM tasks')
            return cursor.fetchall()
    
    def add_task(self, title: str, description: str = None, link: str = None, 
                 week_number: int = None, deadline: datetime = None, is_open: bool = True, 
                 open_date: datetime = None):
        """Добавляет новое задание"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO tasks (title, description, link, week_number, deadline, is_open, open_date)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (title, description, link, week_number, 
                  deadline.isoformat() if deadline else None, is_open,
                  open_date.isoformat() if open_date else None))
            conn.commit()
    
    def submit_task(self, user_id: int, task_id: int, submission_type: str = 'text', 
                   content: str = None, file_id: str = None, file_path: str = None):
        """Записывает отправку задания пользователем"""
        moscow_tz = pytz.timezone('Europe/Moscow')
        submission_time = datetime.now(moscow_tz)
        
        # Проверяем, не опоздал ли пользователь
        is_on_time = self._check_submission_deadline(task_id, submission_time)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO submissions (user_id, task_id, submission_type, content, file_id, file_path, is_on_time)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, task_id, submission_type, content, file_id, file_path, is_on_time))
            conn.commit()
            
        return is_on_time
    
    def _check_submission_deadline(self, task_id: int, submission_time: datetime) -> bool:
        """Проверяет, отправлено ли задание в срок"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT deadline FROM tasks WHERE id = ?', (task_id,))
            result = cursor.fetchone()
            
            if not result or not result[0]:
                return True  # Если дедлайн не установлен, считаем, что в срок
            
            deadline = datetime.fromisoformat(result[0])
            return submission_time <= deadline
    
    def get_user_submissions(self, user_id: int) -> List[Tuple]:
        """Возвращает отправки пользователя с информацией о заданиях"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT t.title, s.submission_date, s.status, s.is_on_time
                FROM submissions s
                JOIN tasks t ON s.task_id = t.id
                WHERE s.user_id = ?
                ORDER BY s.submission_date DESC
            ''', (user_id,))
            return cursor.fetchall()
    
    def get_user_stats(self, user_id: int) -> Tuple[int, int]:
        """Возвращает статистику пользователя: выполнено заданий, всего открытых"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Количество выполненных заданий (только отправленных в срок)
            cursor.execute('''
                SELECT COUNT(DISTINCT task_id) 
                FROM submissions 
                WHERE user_id = ? AND is_on_time = TRUE
            ''', (user_id,))
            completed = cursor.fetchone()[0]
            
            # Общее количество открытых заданий текущей недели
            moscow_tz = pytz.timezone('Europe/Moscow')
            now = datetime.now(moscow_tz)
            
            cursor.execute('''
                SELECT COUNT(*) FROM tasks 
                WHERE is_open = TRUE AND (deadline IS NULL OR deadline > ?)
            ''', (now.isoformat(),))
            total_open = cursor.fetchone()[0]
            
            return completed, total_open
    
    def add_support_request(self, user_id: int, message: str):
        """Добавляет обращение в поддержку"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO support_requests (user_id, message)
                VALUES (?, ?)
            ''', (user_id, message))
            conn.commit()
    
    def create_weekly_tasks(self, week_number: int):
        """Создает тестовые задания для указанной недели"""
        moscow_tz = pytz.timezone('Europe/Moscow')
        
        # Понедельник в 11:00 МСК
        monday_publication = datetime.now(moscow_tz).replace(hour=11, minute=0, second=0, microsecond=0)
        
        # Четверг в 11:00 МСК
        thursday_publication = monday_publication + timedelta(days=3)
        
        # Дедлайн - суббота в 23:59 МСК
        deadline = monday_publication + timedelta(days=5, hours=12, minutes=59)
        
        # Задание на понедельник
        self.add_task(
            f"Экологическое наблюдение - Неделя {week_number}",
            "Проведите наблюдение за природой в вашем районе и поделитесь фотографиями",
            "https://example.com/observation",
            week_number,
            deadline,
            True
        )
        
        # Задание на четверг
        self.add_task(
            f"Экологическое действие - Неделя {week_number}",
            "Совершите одно действие для помощи природе и расскажите о нем",
            "https://example.com/action",
            week_number,
            deadline,
            True
        )

    def get_potential_reports(self, user_id: int = None) -> List[Tuple]:
        """Возвращает потенциальные отчеты для ручной обработки"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            if user_id:
                cursor.execute('''
                    SELECT id, user_id, message_data, message_type, received_date
                    FROM offline_messages 
                    WHERE user_id = ? AND message_type = 'potential_report' AND processed = FALSE
                    ORDER BY received_date DESC
                ''', (user_id,))
            else:
                cursor.execute('''
                    SELECT id, user_id, message_data, message_type, received_date
                    FROM offline_messages 
                    WHERE message_type = 'potential_report' AND processed = FALSE
                    ORDER BY received_date DESC
                ''')
            return cursor.fetchall()

    def mark_potential_report_as_submission(self, message_id: int, task_id: int, admin_notes: str = None):
        """Превращает потенциальный отчет в официальный отчет"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Получаем данные сообщения
            cursor.execute('''
                SELECT user_id, message_data FROM offline_messages WHERE id = ?
            ''', (message_id,))
            result = cursor.fetchone()
            
            if not result:
                return False
            
            user_id, message_data = result
            
            try:
                data = json.loads(message_data)
                submission_type = data.get('type', 'text')
                content = data.get('content', '')
                file_id = data.get('file_id')
                file_path = data.get('file_path')
                
                # Создаем официальный отчет
                moscow_tz = pytz.timezone('Europe/Moscow')
                submission_time = datetime.now(moscow_tz)
                is_on_time = self._check_submission_deadline(task_id, submission_time)
                
                cursor.execute('''
                    INSERT INTO submissions (user_id, task_id, submission_type, content, file_id, file_path, is_on_time, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'approved')
                ''', (user_id, task_id, submission_type, content, file_id, file_path, is_on_time))
                
                # Помечаем исходное сообщение как обработанное
                cursor.execute('''
                    UPDATE offline_messages SET processed = TRUE WHERE id = ?
                ''', (message_id,))
                
                # Добавляем заметку администратора
                if admin_notes:
                    cursor.execute('''
                        INSERT INTO offline_messages (user_id, message_data, message_type)
                        VALUES (?, ?, ?)
                    ''', (user_id, admin_notes, 'admin_note'))
                
                conn.commit()
                return True
                
            except (json.JSONDecodeError, KeyError) as e:
                logger.error(f"Ошибка при обработке потенциального отчета {message_id}: {e}")
                return False

    def get_all_potential_reports_summary(self) -> Dict[str, int]:
        """Возвращает сводку по потенциальным отчетам"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Общее количество
            cursor.execute('''
                SELECT COUNT(*) FROM offline_messages 
                WHERE message_type = 'potential_report' AND processed = FALSE
            ''')
            total = cursor.fetchone()[0]
            
            # По типам
            cursor.execute('''
                SELECT message_data, COUNT(*) FROM offline_messages 
                WHERE message_type = 'potential_report' AND processed = FALSE
                GROUP BY message_data
            ''')
            
            types_count = {'text': 0, 'photo': 0, 'video': 0, 'document': 0}
            
            for message_data, count in cursor.fetchall():
                try:
                    data = json.loads(message_data)
                    msg_type = data.get('type', 'text')
                    if msg_type in types_count:
                        types_count[msg_type] += count
                except json.JSONDecodeError:
                    pass
            
            return {
                'total': total,
                'types': types_count
            } 