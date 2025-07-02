#!/usr/bin/env python3
"""
Инструменты администратора для управления Эко-ботом
"""
import argparse
import sqlite3
from datetime import datetime, timedelta
import pytz
from database import Database

def add_task(args):
    """Добавляет новое задание"""
    db = Database()
    
    moscow_tz = pytz.timezone('Europe/Moscow')
    
    # Если указан номер недели, вычисляем дедлайн
    deadline = None
    if args.week:
        # Вычисляем дату субботы для указанной недели
        current_year = datetime.now(moscow_tz).year
        jan_4 = datetime(current_year, 1, 4, tzinfo=moscow_tz)
        week_start = jan_4 + timedelta(weeks=args.week - 1, days=-jan_4.weekday())
        deadline = week_start + timedelta(days=5, hours=23, minutes=59)  # Суббота 23:59
    
    db.add_task(
        title=args.title,
        description=args.description,
        link=args.link,
        week_number=args.week,
        deadline=deadline,
        is_open=args.open
    )
    
    print(f"✅ Задание '{args.title}' добавлено успешно!")
    if deadline:
        print(f"📅 Дедлайн: {deadline.strftime('%d.%m.%Y в %H:%M МСК')}")

def list_tasks(args):
    """Показывает список всех заданий"""
    db = Database()
    tasks = db.get_all_tasks()
    
    if not tasks:
        print("📝 Заданий пока нет")
        return
    
    print("📋 Список всех заданий:\n")
    for task_id, title, description, link, is_open in tasks:
        status = "🟢 Открыто" if is_open else "📁 Архив"
        print(f"ID: {task_id}")
        print(f"Название: {title}")
        print(f"Описание: {description or 'Не указано'}")
        print(f"Ссылка: {link or 'Не указана'}")
        print(f"Статус: {status}")
        print("-" * 50)

def list_users(args):
    """Показывает список пользователей"""
    db = Database()
    
    with sqlite3.connect(db.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT user_id, username, telegram_first_name, telegram_last_name,
                   first_name, last_name, participation_type, family_members_count, 
                   children_info, registration_completed, registration_date 
            FROM users 
            ORDER BY registration_date DESC
        ''')
        users = cursor.fetchall()
    
    if not users:
        print("👥 Пользователей пока нет")
        return
    
    print("👥 Список пользователей:\n")
    for user_data in users:
        user_id, username, tg_first, tg_last, first_name, last_name, participation, family_count, children, completed, reg_date = user_data
        
        status = "✅ Зарегистрирован" if completed else "⏳ Регистрация не завершена"
        
        print(f"ID: {user_id}")
        print(f"Username: @{username}" if username else "Username: не указан")
        print(f"Telegram: {tg_first} {tg_last or ''}".strip())
        if first_name and last_name:
            print(f"Имя: {first_name} {last_name}")
        print(f"Участие: {participation}")
        if participation == 'family':
            print(f"Участников семьи: {family_count}")
            if children:
                print(f"Дети: {children}")
        print(f"Статус: {status}")
        print(f"Дата регистрации: {reg_date}")
        print("-" * 50)

def show_stats(args):
    """Показывает общую статистику"""
    db = Database()
    
    with sqlite3.connect(db.db_path) as conn:
        cursor = conn.cursor()
        
        # Общее количество пользователей
        cursor.execute('SELECT COUNT(*) FROM users')
        total_users = cursor.fetchone()[0]
        
        # Завершивших регистрацию
        cursor.execute('SELECT COUNT(*) FROM users WHERE registration_completed = TRUE')
        registered_users = cursor.fetchone()[0]
        
        # Семейное участие
        cursor.execute('SELECT COUNT(*) FROM users WHERE participation_type = "family" AND registration_completed = TRUE')
        family_participants = cursor.fetchone()[0]
        
        # Общее количество заданий
        cursor.execute('SELECT COUNT(*) FROM tasks')
        total_tasks = cursor.fetchone()[0]
        
        # Открытые задания
        cursor.execute('SELECT COUNT(*) FROM tasks WHERE is_open = TRUE')
        open_tasks = cursor.fetchone()[0]
        
        # Отправленные отчеты
        cursor.execute('SELECT COUNT(*) FROM submissions')
        total_submissions = cursor.fetchone()[0]
        
        # Отчеты в срок
        cursor.execute('SELECT COUNT(*) FROM submissions WHERE is_on_time = TRUE')
        on_time_submissions = cursor.fetchone()[0]
    
    print("📊 Статистика Эко-бота:")
    print(f"👥 Всего пользователей: {total_users}")
    print(f"✅ Завершили регистрацию: {registered_users}")
    print(f"👨‍👩‍👧‍👦 Семейное участие: {family_participants}")
    print(f"📋 Всего заданий: {total_tasks}")
    print(f"🟢 Открытых заданий: {open_tasks}")
    print(f"📤 Всего отчетов: {total_submissions}")
    print(f"⏰ Отчетов в срок: {on_time_submissions}")

def create_weekly_tasks(args):
    """Создает задания для указанной недели"""
    db = Database()
    db.create_weekly_tasks(args.week)
    print(f"✅ Задания для недели {args.week} созданы!")

def close_task(args):
    """Закрывает задание (переводит в архив)"""
    db = Database()
    
    with sqlite3.connect(db.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE tasks SET is_open = FALSE WHERE id = ?', (args.task_id,))
        
        if cursor.rowcount > 0:
            conn.commit()
            print(f"✅ Задание {args.task_id} переведено в архив")
        else:
            print(f"❌ Задание {args.task_id} не найдено")

def main():
    parser = argparse.ArgumentParser(description='Инструменты администратора Эко-бота')
    subparsers = parser.add_subparsers(dest='command', help='Доступные команды')
    
    # Добавить задание
    add_parser = subparsers.add_parser('add-task', help='Добавить новое задание')
    add_parser.add_argument('title', help='Название задания')
    add_parser.add_argument('--description', '-d', help='Описание задания')
    add_parser.add_argument('--link', '-l', help='Ссылка на задание')
    add_parser.add_argument('--week', '-w', type=int, help='Номер недели')
    add_parser.add_argument('--open', action='store_true', default=True, help='Задание открыто')
    add_parser.set_defaults(func=add_task)
    
    # Список заданий
    list_tasks_parser = subparsers.add_parser('list-tasks', help='Показать все задания')
    list_tasks_parser.set_defaults(func=list_tasks)
    
    # Список пользователей
    list_users_parser = subparsers.add_parser('list-users', help='Показать всех пользователей')
    list_users_parser.set_defaults(func=list_users)
    
    # Статистика
    stats_parser = subparsers.add_parser('stats', help='Показать статистику')
    stats_parser.set_defaults(func=show_stats)
    
    # Создать задания недели
    weekly_parser = subparsers.add_parser('create-week', help='Создать задания для недели')
    weekly_parser.add_argument('week', type=int, help='Номер недели')
    weekly_parser.set_defaults(func=create_weekly_tasks)
    
    # Закрыть задание
    close_parser = subparsers.add_parser('close-task', help='Закрыть задание')
    close_parser.add_argument('task_id', type=int, help='ID задания')
    close_parser.set_defaults(func=close_task)
    
    args = parser.parse_args()
    
    if hasattr(args, 'func'):
        args.func(args)
    else:
        parser.print_help()

if __name__ == '__main__':
    main() 