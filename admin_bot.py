#!/usr/bin/env python3
"""
Админ-бот для управления Эко-ботом
Позволяет администраторам:
- Просматривать все отчеты пользователей
- Добавлять новые задания
- Редактировать существующие задания
- Управлять статусами отчетов
- Получать статистику
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any

import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    MessageHandler, filters, ContextTypes, ConversationHandler
)

from database import Database

# Загружаем переменные окружения
from dotenv import load_dotenv
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния для диалогов
ADDING_TASK_TITLE = 1
ADDING_TASK_DESCRIPTION = 2
ADDING_TASK_LINK = 3
ADDING_TASK_OPEN_DATE = 4
ADDING_TASK_DEADLINE = 5

EDITING_TASK_TITLE = 10
EDITING_TASK_DESCRIPTION = 11
EDITING_TASK_LINK = 12
EDITING_TASK_STATUS = 13
EDITING_TASK_WEEK = 14
EDITING_TASK_DEADLINE = 15
EDITING_TASK_OPEN_DATE = 16

REVIEWING_SUBMISSION = 20

class AdminBot:
    def __init__(self):
        self.db = Database()
        self.moscow_tz = pytz.timezone('Europe/Moscow')
        
        # ID администраторов (можно добавить несколько)
        self.admin_ids = self._get_admin_ids()
        
    def _get_admin_ids(self) -> List[int]:
        """Получает список ID администраторов из переменных окружения"""
        admin_env = os.getenv('ADMIN_IDS', os.getenv('ADMIN_ID', ''))
        if not admin_env:
            logger.warning("ADMIN_IDS не найден в переменных окружения!")
            return []
        
        # Проверяем специальное значение "all"
        if admin_env.strip().lower() == 'all':
            logger.warning("⚠️ РЕЖИМ ОТКРЫТОГО ДОСТУПА: Админ-бот доступен всем пользователям!")
            return ['all']  # Специальный маркер
        
        admin_ids = []
        for admin_id in admin_env.split(','):
            try:
                admin_ids.append(int(admin_id.strip()))
            except ValueError:
                logger.warning(f"Некорректный ADMIN_ID: {admin_id}")
        
        logger.info(f"Загружены ID администраторов: {admin_ids}")
        return admin_ids
    
    def _is_admin(self, user_id: int) -> bool:
        """Проверяет, является ли пользователь администратором"""
        # Если включен режим открытого доступа
        if len(self.admin_ids) == 1 and self.admin_ids[0] == 'all':
            return True
        
        return user_id in self.admin_ids
    
    async def _check_admin_access(self, update: Update) -> bool:
        """Проверяет права администратора и отправляет сообщение об ошибке если нет прав"""
        user_id = update.effective_user.id
        if not self._is_admin(user_id):
            await update.effective_message.reply_text(
                "❌ **Доступ запрещен**\n\n"
                "Этот бот предназначен только для администраторов Эко-бота.",
                parse_mode='Markdown'
            )
            return False
        return True

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        if not await self._check_admin_access(update):
            return
        
        user = update.effective_user
        
        welcome_text = (
            f"🔧 **Админ-панель Эко-бота**\n\n"
            f"Добро пожаловать, {user.first_name}!\n\n"
            f"Доступные функции:\n"
            f"• 📋 Управление заданиями\n"
            f"• 📤 Просмотр отчетов\n"
            f"• ✅ Модерация отчетов\n"
            f"• 📊 Статистика\n"
            f"• 🔧 Системные функции\n\n"
            f"Выберите действие:"
        )
        
        keyboard = [
            [InlineKeyboardButton("📋 Задания", callback_data="tasks_menu")],
            [InlineKeyboardButton("📤 Отчеты", callback_data="reports_menu")],
            [InlineKeyboardButton("📊 Статистика", callback_data="stats_menu")],
            [InlineKeyboardButton("🔧 Система", callback_data="system_menu")]
        ]
        
        await update.message.reply_text(
            welcome_text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик callback кнопок"""
        if not await self._check_admin_access(update):
            return
        
        query = update.callback_query
        await query.answer()
        
        data = query.data
        
        if data == "main_menu":
            await self._show_main_menu(query)
        elif data == "tasks_menu":
            await self._show_tasks_menu(query)
        elif data == "reports_menu":
            await self._show_reports_menu(query)
        elif data == "stats_menu":
            await self._show_stats_menu(query)
        elif data == "system_menu":
            await self._show_system_menu(query)
        elif data == "add_task":
            await self._show_add_task_menu(query)
        elif data == "list_tasks":
            await self._show_tasks_list(query)
        elif data == "pending_reports":
            await self._show_pending_reports(query)
        elif data == "all_reports":
            await self._show_all_reports(query)
        elif data == "potential_reports":
            await self._show_potential_reports(query)
        elif data.startswith("task_"):
            await self._handle_task_action(query, context, data)
        elif data.startswith("report_"):
            await self._handle_report_action(query, context, data)
        elif data.startswith("approve_"):
            await self._approve_report(query, data)
        elif data.startswith("reject_"):
            await self._reject_report(query, data)
        elif data == "edit_task_preview":
            await self._edit_task_preview(query, context)
        elif data.startswith("edit_task_"):
            await self._start_edit_task(query, context, data)
        elif data.startswith("toggle_task_"):
            await self._toggle_task_status(query, data)
        elif data.startswith("delete_task_"):
            await self._delete_task(query, data)
        elif data.startswith("confirm_delete_"):
            await self._confirm_delete_task(query, data)
        elif data.startswith("task_reports_"):
            task_id = int(data.split('_')[2])  # task_reports_123
            await self._show_task_reports(query, f"task_reports_{task_id}")
        elif data.startswith("user_profile_"):
            await self._show_user_profile(query, data)
        elif data.startswith("user_reports_"):
            await self._show_user_reports(query, data)
        elif data == "export_data":
            await self._handle_export_data(query)
        elif data == "clear_logs":
            await self._handle_clear_logs(query)
        elif data == "confirm_clear_logs":
            await self._confirm_clear_logs(query)
        elif data.startswith("export_"):
            await self._handle_specific_export(query, data)
        elif data.startswith("show_file_"):
            await self._show_file(query, data)
        elif data.startswith("potential_"):
            await self._handle_potential_report(query, data)
        elif data.startswith("assign_potential_"):
            await self._assign_potential_to_task(query, data)
        elif data.startswith("mark_processed_"):
            await self._mark_potential_processed(query, data)
        elif data.startswith("delete_potential_"):
            await self._delete_potential_report(query, data)
        elif data.startswith("show_potential_file_"):
            await self._show_potential_file(query, data)
        elif data.startswith("edit_title_"):
            await self._start_edit_title(update, context)
        elif data.startswith("edit_desc_"):
            await self._start_edit_description(update, context)
        elif data.startswith("edit_link_"):
            await self._start_edit_link(update, context)
        elif data.startswith("edit_open_date_"):
            await self._start_edit_open_date(update, context)
        elif data.startswith("edit_deadline_"):
            await self._start_edit_deadline(update, context)
        # Новые обработчики для функционала добавления заданий
        elif data.startswith("template_"):
            await self._handle_template_callback(query, context, data)
        elif data == "confirm_create_task":
            await self._confirm_create_task(query, context)
        elif data == "edit_task_preview":
            await self._edit_task_preview(query, context)
        elif data == "edit_preview_title":
            await self._start_preview_edit_title(query, context, data)
        elif data == "edit_preview_description":
            await self._start_preview_edit_description(query, context, data)
        elif data == "edit_preview_link":
            await self._start_preview_edit_link(query, context, data)
        elif data == "edit_preview_open_date":
            await self._start_preview_edit_open_date(query, context, data)
        elif data == "edit_preview_deadline":
            await self._start_preview_edit_deadline(query, context, data)


    async def _handle_template_callback(self, query, context, data):
        """Обрабатывает выбор шаблона через callback"""
        template_type = data.replace('template_', '')
        
        # Применяем шаблон
        templates = {
            'observation': {
                'title': 'Экологическое наблюдение',
                'description': 'Проведите наблюдение за природой в вашем районе. Сфотографируйте интересные природные объекты и поделитесь своими наблюдениями.',
                'link': None
            },
            'action': {
                'title': 'Экологическое действие',
                'description': 'Совершите одно полезное действие для окружающей среды. Это может быть уборка территории, посадка растений или сортировка отходов.',
                'link': None
            },
            'research': {
                'title': 'Исследование природы',
                'description': 'Проведите небольшое исследование природного объекта в вашем районе. Изучите его особенности и поделитесь результатами.',
                'link': None
            }
        }
        
        template = templates.get(template_type)
        if not template:
            await query.edit_message_text("❌ Неизвестный шаблон!")
            return
        
        # Применяем шаблон
        current_date = datetime.now(self.moscow_tz)
        template['title'] = f"{template['title']} - {current_date.strftime('%d.%m.%Y')}"
        
        context.user_data['adding_task'] = template.copy()
        context.user_data['adding_task']['open_date'] = current_date
        
        # Автоматически устанавливаем дедлайн (через неделю)
        deadline = current_date + timedelta(days=7)
        deadline = deadline.replace(hour=23, minute=59, second=59)
        context.user_data['adding_task']['deadline'] = deadline
        
        # Показываем предварительный просмотр
        preview_text = self._generate_task_preview(context.user_data['adding_task'], deadline)
        
        keyboard = [
            [InlineKeyboardButton("✅ Создать задание", callback_data="confirm_create_task")],
            [InlineKeyboardButton("✏️ Изменить", callback_data="edit_task_preview")],
            [InlineKeyboardButton("❌ Отменить", callback_data="tasks_menu")]
        ]
        
        await query.edit_message_text(
            f"🎯 **Шаблон '{template_type}' применен!**\n\n{preview_text}",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _confirm_create_task(self, query, context):
        """Подтверждает создание задания"""
        task_data = context.user_data.get('adding_task', {})
        
        if not task_data:
            await query.edit_message_text("❌ Данные задания не найдены. Начните заново.")
            return
        
        try:
            # Создаем задание в базе данных
            # Определяем, открыто ли задание сейчас
            open_date = task_data.get('open_date', datetime.now(self.moscow_tz))
            is_open = open_date <= datetime.now(self.moscow_tz)
            
            self.db.add_task(
                title=task_data['title'],
                description=task_data['description'],
                link=task_data['link'],
                week_number=None,  # Больше не используем номер недели
                deadline=task_data['deadline'],
                is_open=is_open,
                open_date=open_date
            )
            
            # Получаем ID созданного задания
            with self.db._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT id FROM tasks WHERE title = ? ORDER BY id DESC LIMIT 1', (task_data['title'],))
                task_id = cursor.fetchone()[0]
            
            success_text = (
                "✅ **ЗАДАНИЕ УСПЕШНО СОЗДАНО!**\n\n"
                f"🆔 **ID задания:** {task_id}\n"
                f"📝 **Название:** {task_data['title']}\n"
                f"📄 **Описание:** {task_data['description'][:100]}{'...' if len(task_data['description']) > 100 else ''}\n"
                f"🔗 **Ссылка:** {task_data['link'] or 'не указана'}\n"
                f"📅 **Открытие:** {open_date.strftime('%d.%m.%Y в %H:%M МСК')}\n"
                f"⏰ **Дедлайн:** {task_data['deadline'].strftime('%d.%m.%Y в %H:%M МСК') if task_data['deadline'] else 'не установлен'}\n"
                f"🟢 **Статус:** {'Открыто' if is_open else 'Ожидает открытия'}\n\n"
                f"🎉 **Задание {'доступно пользователям' if is_open else 'будет открыто в указанное время'}!**"
            )
            
            keyboard = [
                [InlineKeyboardButton("➕ Создать еще задание", callback_data="add_task")],
                [InlineKeyboardButton("📋 Посмотреть задание", callback_data=f"task_{task_id}")],
                [InlineKeyboardButton("📝 Список заданий", callback_data="list_tasks")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
            ]
            
            await query.edit_message_text(
                success_text,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
            # Очищаем данные
            context.user_data.clear()
            
            # Логируем успешное создание
            logger.info(f"Создано новое задание: '{task_data['title']}' (ID: {task_id})")
            
        except Exception as e:
            logger.error(f"Ошибка при создании задания: {e}")
            
            error_text = (
                "❌ **ОШИБКА ПРИ СОЗДАНИИ ЗАДАНИЯ**\n\n"
                f"Произошла ошибка: {str(e)}\n\n"
                "Попробуйте еще раз или обратитесь к разработчику."
            )
            
            keyboard = [
                [InlineKeyboardButton("🔄 Попробовать снова", callback_data="confirm_create_task")],
                [InlineKeyboardButton("✏️ Изменить данные", callback_data="edit_task_preview")],
                [InlineKeyboardButton("❌ Отменить", callback_data="tasks_menu")]
            ]
            
            await query.edit_message_text(
                error_text,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

    async def _edit_task_preview(self, query, context):
        """Позволяет редактировать данные задания перед созданием"""
        task_data = context.user_data.get('adding_task', {})
        
        if not task_data:
            await query.edit_message_text("❌ Данные задания не найдены. Начните заново.")
            return
        
        open_date = task_data.get('open_date', datetime.now(self.moscow_tz))
        
        text = (
            "✏️ **РЕДАКТИРОВАНИЕ ЗАДАНИЯ**\n\n"
            f"📝 **Название:** {task_data['title']}\n"
            f"📄 **Описание:** {task_data['description'][:100]}{'...' if len(task_data['description']) > 100 else ''}\n"
            f"🔗 **Ссылка:** {task_data['link'] or 'не указана'}\n"
            f"📅 **Открытие:** {open_date.strftime('%d.%m.%Y в %H:%M МСК')}\n"
            f"⏰ **Дедлайн:** {task_data['deadline'].strftime('%d.%m.%Y в %H:%M МСК') if task_data['deadline'] else 'не установлен'}\n\n"
            f"Что хотите изменить?"
        )
        
        keyboard = [
            [InlineKeyboardButton("📝 Название", callback_data="edit_preview_title")],
            [InlineKeyboardButton("📄 Описание", callback_data="edit_preview_description")],
            [InlineKeyboardButton("🔗 Ссылку", callback_data="edit_preview_link")],
            [InlineKeyboardButton("📅 Дату открытия", callback_data="edit_preview_open_date")],
            [InlineKeyboardButton("⏰ Дедлайн", callback_data="edit_preview_deadline")],
            [InlineKeyboardButton("✅ Готово, создать", callback_data="confirm_create_task")],
            [InlineKeyboardButton("❌ Отменить", callback_data="tasks_menu")]
        ]
        
        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _start_preview_edit_title(self, query, context, data):
        """Начинает редактирование названия в предварительном просмотре"""
        task_data = context.user_data.get('adding_task', {})
        current_title = task_data.get('title', '')
        
        text = (
            "✏️ **Редактирование названия**\n\n"
            f"📝 **Текущее название:** {current_title}\n\n"
            "Введите новое название задания:"
        )
        
        await query.edit_message_text(text, parse_mode='Markdown')
        # Переводим в состояние редактирования названия
        return ADDING_TASK_TITLE

    async def _start_preview_edit_description(self, query, context, data):
        """Начинает редактирование описания в предварительном просмотре"""
        task_data = context.user_data.get('adding_task', {})
        current_description = task_data.get('description', '')
        
        text = (
            "✏️ **Редактирование описания**\n\n"
            f"📄 **Текущее описание:** {current_description[:200]}{'...' if len(current_description) > 200 else ''}\n\n"
            "Введите новое описание задания:"
        )
        
        await query.edit_message_text(text, parse_mode='Markdown')
        # Переводим в состояние редактирования описания
        return ADDING_TASK_DESCRIPTION

    async def _start_preview_edit_link(self, query, context, data):
        """Начинает редактирование ссылки в предварительном просмотре"""
        task_data = context.user_data.get('adding_task', {})
        current_link = task_data.get('link') or 'не указана'
        
        text = (
            "✏️ **Редактирование ссылки**\n\n"
            f"🔗 **Текущая ссылка:** {current_link}\n\n"
            "Введите новую ссылку или 'нет' чтобы убрать:"
        )
        
        await query.edit_message_text(text, parse_mode='Markdown')
        # Переводим в состояние редактирования ссылки
        return ADDING_TASK_LINK

    async def _start_preview_edit_open_date(self, query, context, data):
        """Начинает редактирование даты открытия в предварительном просмотре"""
        task_data = context.user_data.get('adding_task', {})
        current_date = task_data.get('open_date', datetime.now(self.moscow_tz))
        
        text = (
            "✏️ **Редактирование даты открытия**\n\n"
            f"📅 **Текущая дата:** {current_date.strftime('%d.%m.%Y в %H:%M МСК')}\n\n"
            "Введите новую дату открытия:\n"
            "• `сейчас` - открыть сейчас\n"
            "• `завтра` - завтра в 09:00\n"
            "• `ДД.ММ.ГГГГ ЧЧ:ММ` - конкретная дата"
        )
        
        await query.edit_message_text(text, parse_mode='Markdown')
        # Переводим в состояние редактирования даты открытия
        return ADDING_TASK_OPEN_DATE

    async def _start_preview_edit_deadline(self, query, context, data):
        """Начинает редактирование дедлайна в предварительном просмотре"""
        task_data = context.user_data.get('adding_task', {})
        current_deadline = task_data.get('deadline')
        
        if current_deadline:
            deadline_str = current_deadline.strftime('%d.%m.%Y в %H:%M МСК')
        else:
            deadline_str = 'не установлен'
        
        text = (
            "✏️ **Редактирование дедлайна**\n\n"
            f"⏰ **Текущий дедлайн:** {deadline_str}\n\n"
            "Введите новый дедлайн:\n"
            "• `авто` - автоматический расчет\n"
            "• `завтра` - завтра в 23:59\n"
            "• `ДД.ММ.ГГГГ ЧЧ:ММ` - конкретная дата\n"
            "• `нет` - без дедлайна"
        )
        
        await query.edit_message_text(text, parse_mode='Markdown')
        # Переводим в состояние редактирования дедлайна
        return ADDING_TASK_DEADLINE

    async def _show_main_menu(self, query):
        """Показывает главное меню"""
        text = (
            "🔧 **Админ-панель Эко-бота**\n\n"
            "Выберите раздел для работы:"
        )
        
        keyboard = [
            [InlineKeyboardButton("📋 Задания", callback_data="tasks_menu")],
            [InlineKeyboardButton("📤 Отчеты", callback_data="reports_menu")],
            [InlineKeyboardButton("📊 Статистика", callback_data="stats_menu")],
            [InlineKeyboardButton("🔧 Система", callback_data="system_menu")]
        ]
        
        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _show_tasks_menu(self, query):
        """Показывает меню управления заданиями"""
        text = (
            "📋 **Управление заданиями**\n\n"
            "Выберите действие:"
        )
        
        keyboard = [
            [InlineKeyboardButton("➕ Добавить задание", callback_data="add_task")],
            [InlineKeyboardButton("📝 Список заданий", callback_data="list_tasks")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
        ]
        
        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _show_reports_menu(self, query):
        """Показывает меню работы с отчетами"""
        # Получаем статистику отчетов
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            
            # Ожидающие проверки
            cursor.execute("SELECT COUNT(*) FROM submissions WHERE status = 'pending'")
            pending_count = cursor.fetchone()[0]
            
            # Всего отчетов
            cursor.execute("SELECT COUNT(*) FROM submissions")
            total_count = cursor.fetchone()[0]
            
            # Потенциальные отчеты
            cursor.execute("SELECT COUNT(*) FROM offline_messages WHERE message_type = 'potential_report' AND processed = FALSE")
            potential_count = cursor.fetchone()[0]
        
        text = (
            "📤 **Работа с отчетами**\n\n"
            f"⏳ Ожидают проверки: {pending_count}\n"
            f"📝 Всего отчетов: {total_count}\n"
            f"🔍 Потенциальные отчеты: {potential_count}\n\n"
            "Выберите действие:"
        )
        
        keyboard = [
            [InlineKeyboardButton(f"⏳ Ожидающие проверки ({pending_count})", callback_data="pending_reports")],
            [InlineKeyboardButton("📤 Все отчеты", callback_data="all_reports")],
            [InlineKeyboardButton(f"🔍 Потенциальные ({potential_count})", callback_data="potential_reports")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
        ]
        
        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _show_stats_menu(self, query):
        """Показывает статистику"""
        # Получаем статистику
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            
            # Пользователи
            cursor.execute('SELECT COUNT(*) FROM users')
            total_users = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM users WHERE registration_completed = TRUE')
            registered_users = cursor.fetchone()[0]
            
            # Задания
            cursor.execute('SELECT COUNT(*) FROM tasks')
            total_tasks = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM tasks WHERE is_open = TRUE')
            open_tasks = cursor.fetchone()[0]
            
            # Отчеты
            cursor.execute('SELECT COUNT(*) FROM submissions')
            total_submissions = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM submissions WHERE status = "pending"')
            pending_submissions = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM submissions WHERE status = "approved"')
            approved_submissions = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM submissions WHERE is_on_time = TRUE')
            on_time_submissions = cursor.fetchone()[0]
        
        text = (
            "📊 **Статистика Эко-бота**\n\n"
            f"👥 **Пользователи:**\n"
            f"   • Всего: {total_users}\n"
            f"   • Зарегистрированы: {registered_users}\n\n"
            f"📋 **Задания:**\n"
            f"   • Всего: {total_tasks}\n"
            f"   • Открытых: {open_tasks}\n\n"
            f"📤 **Отчеты:**\n"
            f"   • Всего: {total_submissions}\n"
            f"   • Ожидают проверки: {pending_submissions}\n"
            f"   • Одобрены: {approved_submissions}\n"
            f"   • Отправлены в срок: {on_time_submissions}\n\n"
            f"📈 **Активность:**\n"
            f"   • Процент завершения регистрации: {registered_users/max(total_users, 1)*100:.1f}%\n"
            f"   • Процент одобренных отчетов: {approved_submissions/max(total_submissions, 1)*100:.1f}%\n"
            f"   • Процент отчетов в срок: {on_time_submissions/max(total_submissions, 1)*100:.1f}%"
        )
        
        keyboard = [
            [InlineKeyboardButton("🔄 Обновить", callback_data="stats_menu")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
        ]
        
        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _show_system_menu(self, query):
        """Показывает системное меню"""
        text = (
            "🔧 **Системные функции**\n\n"
            "Доступные действия:"
        )
        
        keyboard = [
            [InlineKeyboardButton("📊 Экспорт данных", callback_data="export_data")],
            [InlineKeyboardButton("🧹 Очистка логов", callback_data="clear_logs")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
        ]
        
        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _show_add_task_menu(self, query):
        """Показывает меню добавления задания"""
        text = (
            "➕ **Добавление нового задания**\n\n"
            "🚀 **Быстрый старт:**\n"
            "• Используйте шаблоны для типовых заданий\n"
            "• Автоматический расчет дедлайнов\n"
            "• Предварительный просмотр перед созданием\n\n"
            "Выберите способ создания задания:"
        )
        
        keyboard = [
            [InlineKeyboardButton("🎯 Шаблон: Наблюдение", callback_data="template_observation")],
            [InlineKeyboardButton("🌱 Шаблон: Действие", callback_data="template_action")],
            [InlineKeyboardButton("🔬 Шаблон: Исследование", callback_data="template_research")],
            [InlineKeyboardButton("✏️ Создать с нуля", callback_data="create_manual")],
            [InlineKeyboardButton("❌ Отмена", callback_data="tasks_menu")]
        ]
        
        await query.edit_message_text(
            text, 
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _start_add_task_conversation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Начинает диалог создания задания с нуля"""
        query = update.callback_query
        await query.answer()
        
        if not await self._check_admin_access(update):
            return ConversationHandler.END
        
        context.user_data['adding_task'] = {}
        
        text = (
            "➕ **Создание задания с нуля**\n\n"
            "📝 **Шаг 1/5:** Введите название задания\n"
            "💡 *Минимум 5 символов, максимум 100*\n\n"
            "⚡ **Быстрые команды:**\n"
            "• `/template_observation` - Экологическое наблюдение\n"
            "• `/template_action` - Экологическое действие\n"
            "• `/template_research` - Исследование природы\n\n"
            "🔧 *Для отмены введите* `/cancel`"
        )
        
        await query.edit_message_text(text, parse_mode='Markdown')
        return ADDING_TASK_TITLE

    async def _start_add_task(self, query, context):
        """Начинает процесс добавления задания"""
        context.user_data['adding_task'] = {}
        
        # Получаем текущую неделю для подсказки
        current_week = datetime.now(self.moscow_tz).isocalendar()[1]
        
        text = (
            "➕ **Добавление нового задания**\n\n"
            "🚀 **Быстрый старт:**\n"
            "• Используйте шаблоны для типовых заданий\n"
            "• Автоматический расчет дедлайнов\n"
            "• Предварительный просмотр перед созданием\n\n"
            "📝 **Шаг 1/5:** Введите название задания\n"
            "💡 *Минимум 5 символов, максимум 100*\n\n"
            "⚡ **Быстрые шаблоны:**\n"
            "• `/template_observation` - Экологическое наблюдение\n"
            "• `/template_action` - Экологическое действие\n"
            "• `/template_research` - Исследование природы\n\n"
            "🔧 *Для отмены введите* `/cancel`"
        )
        
        keyboard = [
            [InlineKeyboardButton("🎯 Шаблон: Наблюдение", callback_data="template_observation")],
            [InlineKeyboardButton("🌱 Шаблон: Действие", callback_data="template_action")],
            [InlineKeyboardButton("🔬 Шаблон: Исследование", callback_data="template_research")],
            [InlineKeyboardButton("❌ Отмена", callback_data="tasks_menu")]
        ]
        
        await query.edit_message_text(
            text, 
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ADDING_TASK_TITLE

    async def handle_add_task_title(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает ввод названия задания"""
        if not await self._check_admin_access(update):
            return ConversationHandler.END
        
        title = update.message.text.strip()
        
        # Проверка на команды шаблонов
        if title.startswith('/template_'):
            template_type = title.replace('/template_', '')
            return await self._apply_task_template(update, context, template_type)
        
        # Валидация названия
        if len(title) < 5:
            await update.message.reply_text(
                "❌ **Название слишком короткое**\n\n"
                "Название задания должно содержать минимум 5 символов.\n"
                "Попробуйте еще раз или используйте шаблон:"
            )
            return ADDING_TASK_TITLE
        
        if len(title) > 100:
            await update.message.reply_text(
                "❌ **Название слишком длинное**\n\n"
                "Название задания не должно превышать 100 символов.\n"
                "Попробуйте сократить:"
            )
            return ADDING_TASK_TITLE
        
        # Проверка на дублирование
        if self._check_task_title_exists(title):
            await update.message.reply_text(
                "⚠️ **Задание с таким названием уже существует**\n\n"
                "Измените название или добавьте уточнение (например, номер недели):"
            )
            return ADDING_TASK_TITLE
        
        context.user_data['adding_task']['title'] = title
        
        # Прогресс-бар
        progress = "🟢🔘🔘🔘🔘"
        
        await update.message.reply_text(
            f"✅ **Название принято!**\n"
            f"📝 *{title}*\n\n"
            f"📊 **Прогресс:** {progress} (1/5)\n\n"
            f"📄 **Шаг 2/5:** Введите описание задания\n"
            f"💡 *Опишите, что должны сделать участники*\n\n"
            f"📋 **Примеры хорошего описания:**\n"
            f"• Сфотографируйте 3 вида растений в вашем районе\n"
            f"• Проведите уборку территории площадью 100 кв.м\n"
            f"• Измерьте температуру воды в ближайшем водоеме"
        )
        return ADDING_TASK_DESCRIPTION

    async def handle_add_task_description(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает ввод описания задания"""
        if not await self._check_admin_access(update):
            return ConversationHandler.END
        
        description = update.message.text.strip()
        
        # Валидация описания
        if len(description) < 10:
            await update.message.reply_text(
                "❌ **Описание слишком короткое**\n\n"
                "Описание должно содержать минимум 10 символов.\n"
                "Добавьте больше деталей о том, что нужно сделать:"
            )
            return ADDING_TASK_DESCRIPTION
        
        if len(description) > 1000:
            await update.message.reply_text(
                "❌ **Описание слишком длинное**\n\n"
                "Описание не должно превышать 1000 символов.\n"
                "Попробуйте сократить, оставив только самое важное:"
            )
            return ADDING_TASK_DESCRIPTION
        
        context.user_data['adding_task']['description'] = description
        
        # Прогресс-бар
        progress = "🟢🟢🔘🔘🔘"
        
        await update.message.reply_text(
            f"✅ **Описание принято!**\n"
            f"📄 *{description[:100]}{'...' if len(description) > 100 else ''}*\n\n"
            f"📊 **Прогресс:** {progress} (2/5)\n\n"
            f"🔗 **Шаг 3/5:** Введите ссылку на задание\n"
            f"💡 *Необязательно - для дополнительных материалов*\n\n"
            f"📋 **Варианты ввода:**\n"
            f"• Полная ссылка: `https://example.com/task`\n"
            f"• Без ссылки: `нет`, `no`, `-` или `пропустить`\n"
            f"• Telegram канал: `@channel_name`",
            parse_mode='Markdown'
        )
        return ADDING_TASK_LINK

    async def handle_add_task_link(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает ввод ссылки задания"""
        if not await self._check_admin_access(update):
            return ConversationHandler.END
        
        link = update.message.text.strip()
        
        # Обработка отсутствия ссылки
        if link.lower() in ['нет', 'no', '-', 'пропустить', 'skip']:
            link = None
        else:
            # Валидация ссылки
            if not self._validate_url(link):
                await update.message.reply_text(
                    "❌ **Некорректная ссылка**\n\n"
                    "Ссылка должна начинаться с `http://`, `https://` или `@` (для Telegram)\n\n"
                    "📋 **Примеры корректных ссылок:**\n"
                    "• `https://example.com/task`\n"
                    "• `@eco_channel`\n"
                    "• `https://t.me/eco_channel`\n\n"
                    "Или введите `нет` если ссылка не нужна:",
                    parse_mode='Markdown'
                )
                return ADDING_TASK_LINK
        
        context.user_data['adding_task']['link'] = link
        
        # Получаем текущий номер недели
        current_week = datetime.now(self.moscow_tz).isocalendar()[1]
        
        # Прогресс-бар
        progress = "🟢🟢🟢🔘🔘"
        
        await update.message.reply_text(
            f"✅ **Ссылка {'добавлена' if link else 'пропущена'}!**\n"
            f"🔗 *{link or 'не указана'}*\n\n"
            f"📊 **Прогресс:** {progress} (3/5)\n\n"
            f"📅 **Шаг 4/5:** Установите дату открытия задания\n"
            f"💡 *Когда задание станет доступно пользователям*\n\n"
            f"📋 **Варианты ввода:**\n"
            f"• Сейчас: `сейчас` или `now`\n"
            f"• Завтра: `завтра` или `tomorrow`\n"
            f"• Конкретная дата: `ДД.ММ.ГГГГ` или `ДД.ММ.ГГГГ ЧЧ:ММ`\n"
            f"• Через неделю: `неделя` или `week`"
        )
        return ADDING_TASK_OPEN_DATE

    async def handle_add_task_open_date(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает ввод даты открытия задания"""
        if not await self._check_admin_access(update):
            return ConversationHandler.END
        
        open_date_input = update.message.text.strip().lower()
        
        try:
            # Обработка различных вариантов ввода
            if open_date_input in ['сейчас', 'now']:
                open_date = datetime.now(self.moscow_tz)
            elif open_date_input in ['завтра', 'tomorrow']:
                open_date = datetime.now(self.moscow_tz) + timedelta(days=1)
                open_date = open_date.replace(hour=9, minute=0, second=0, microsecond=0)
            elif open_date_input in ['неделя', 'week']:
                open_date = datetime.now(self.moscow_tz) + timedelta(weeks=1)
                open_date = open_date.replace(hour=9, minute=0, second=0, microsecond=0)
            else:
                # Попытка парсинга ручного ввода
                try:
                    if ' ' in open_date_input:
                        # Формат с временем
                        open_date = datetime.strptime(open_date_input, '%d.%m.%Y %H:%M')
                    else:
                        # Только дата, время по умолчанию 09:00
                        open_date = datetime.strptime(open_date_input, '%d.%m.%Y')
                        open_date = open_date.replace(hour=9, minute=0)
                    
                    open_date = self.moscow_tz.localize(open_date)
                except ValueError:
                    raise ValueError("Неверный формат даты")
                
                # Проверка, что дата открытия не в прошлом (с учетом текущего времени)
                if open_date < datetime.now(self.moscow_tz):
                    await update.message.reply_text(
                        "❌ **Дата открытия в прошлом**\n\n"
                        "Дата открытия должна быть в будущем или сейчас.\n"
                        "Попробуйте еще раз:"
                    )
                    return ADDING_TASK_OPEN_DATE
                    
        except ValueError as e:
            await update.message.reply_text(
                "❌ **Неверный формат даты**\n\n"
                "Используйте один из форматов:\n"
                "• `ДД.ММ.ГГГГ ЧЧ:ММ` (например: 25.12.2024 09:00)\n"
                "• `ДД.ММ.ГГГГ` (время установится 09:00)\n"
                "• `сейчас` - открыть сейчас\n"
                "• `завтра` - завтра в 09:00\n"
                "• `неделя` - через неделю в 09:00"
            )
            return ADDING_TASK_OPEN_DATE
        
        context.user_data['adding_task']['open_date'] = open_date
        
        # Вычисляем предлагаемый дедлайн (через неделю после открытия)
        suggested_deadline = open_date + timedelta(days=7)
        suggested_deadline = suggested_deadline.replace(hour=23, minute=59, second=59)
        deadline_str = suggested_deadline.strftime('%d.%m.%Y %H:%M')
        
        # Прогресс-бар
        progress = "🟢🟢🟢🟢🔘"
        
        await update.message.reply_text(
            f"✅ **Дата открытия установлена!**\n"
            f"📅 *{open_date.strftime('%d.%m.%Y в %H:%M МСК')}*\n\n"
            f"📊 **Прогресс:** {progress} (4/5)\n\n"
            f"⏰ **Шаг 5/5:** Установите дедлайн\n"
            f"💡 *Предлагаемый дедлайн: {deadline_str}*\n\n"
            f"📋 **Варианты ввода:**\n"
            f"• Автоматический: `авто` или `auto`\n"
            f"• Ручной ввод: `ДД.ММ.ГГГГ ЧЧ:ММ`\n"
            f"• Завтра в 23:59: `завтра`\n"
            f"• Через неделю: `неделя`\n"
            f"• Без дедлайна: `нет`"
        )
        return ADDING_TASK_DEADLINE

    async def handle_add_task_deadline(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает ввод дедлайна и создает задание"""
        if not await self._check_admin_access(update):
            return ConversationHandler.END
        
        deadline_str = update.message.text.strip().lower()
        
        try:
            # Обработка различных вариантов ввода дедлайна
            if deadline_str in ['авто', 'auto']:
                # Автоматический дедлайн: через неделю после открытия
                open_date = context.user_data['adding_task'].get('open_date', datetime.now(self.moscow_tz))
                deadline = open_date + timedelta(days=7)
                deadline = deadline.replace(hour=23, minute=59, second=59)
            elif deadline_str in ['завтра', 'tomorrow']:
                deadline = datetime.now(self.moscow_tz).replace(hour=23, minute=59, second=59) + timedelta(days=1)
            elif deadline_str in ['неделя', 'week']:
                deadline = datetime.now(self.moscow_tz) + timedelta(weeks=1)
                deadline = deadline.replace(hour=23, minute=59, second=59)
            elif deadline_str in ['нет', 'no', '-']:
                deadline = None
            else:
                # Попытка парсинга ручного ввода
                try:
                    deadline = datetime.strptime(deadline_str, '%d.%m.%Y %H:%M')
                    deadline = self.moscow_tz.localize(deadline)
                except ValueError:
                    # Пробуем другие форматы
                    try:
                        deadline = datetime.strptime(deadline_str, '%d.%m.%Y')
                        deadline = self.moscow_tz.localize(deadline.replace(hour=23, minute=59))
                    except ValueError:
                        raise ValueError("Неверный формат даты")
                
                # Проверка, что дедлайн в будущем
                if deadline and deadline <= datetime.now(self.moscow_tz):
                    await update.message.reply_text(
                        "❌ **Дедлайн в прошлом**\n\n"
                        "Дедлайн должен быть в будущем.\n"
                        "Попробуйте еще раз:"
                    )
                    return ADDING_TASK_DEADLINE
                
                # Проверка, что дедлайн не раньше даты открытия
                open_date = context.user_data['adding_task'].get('open_date')
                if deadline and open_date and deadline <= open_date:
                    await update.message.reply_text(
                        "❌ **Дедлайн раньше даты открытия**\n\n"
                        "Дедлайн должен быть позже даты открытия задания.\n"
                        "Попробуйте еще раз:"
                    )
                    return ADDING_TASK_DEADLINE
                    
        except ValueError as e:
            await update.message.reply_text(
                "❌ **Неверный формат даты**\n\n"
                "Используйте один из форматов:\n"
                "• `ДД.ММ.ГГГГ ЧЧ:ММ` (например: 25.12.2024 23:59)\n"
                "• `ДД.ММ.ГГГГ` (время установится 23:59)\n"
                "• `авто` - автоматический расчет\n"
                "• `завтра` - завтра в 23:59\n"
                "• `неделя` - через неделю\n"
                "• `нет` - без дедлайна"
            )
            return ADDING_TASK_DEADLINE
        
        # Создаем задание
        task_data = context.user_data['adding_task']
        
        # Показываем предварительный просмотр
        preview_text = self._generate_task_preview(task_data, deadline)
        
        keyboard = [
            [InlineKeyboardButton("✅ Создать задание", callback_data="confirm_create_task")],
            [InlineKeyboardButton("✏️ Изменить", callback_data="edit_task_preview")],
            [InlineKeyboardButton("❌ Отменить", callback_data="tasks_menu")]
        ]
        
        # Сохраняем дедлайн для подтверждения
        context.user_data['adding_task']['deadline'] = deadline
        
        await update.message.reply_text(
            preview_text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        return ADDING_TASK_DEADLINE

    def _generate_task_preview(self, task_data: dict, deadline: datetime) -> str:
        """Генерирует предварительный просмотр задания"""
        progress = "🟢🟢🟢🟢🟢"
        
        open_date = task_data.get('open_date', datetime.now(self.moscow_tz))
        is_open = open_date <= datetime.now(self.moscow_tz)
        
        preview = (
            f"📋 **ПРЕДВАРИТЕЛЬНЫЙ ПРОСМОТР ЗАДАНИЯ**\n\n"
            f"📊 **Прогресс:** {progress} (5/5) ✅\n\n"
            f"📝 **Название:**\n{task_data['title']}\n\n"
            f"📄 **Описание:**\n{task_data['description']}\n\n"
            f"🔗 **Ссылка:**\n{task_data['link'] or 'не указана'}\n\n"
            f"📅 **Открытие:**\n{open_date.strftime('%d.%m.%Y в %H:%M МСК')}\n\n"
            f"⏰ **Дедлайн:**\n{deadline.strftime('%d.%m.%Y в %H:%M МСК') if deadline else 'не установлен'}\n\n"
            f"🟢 **Статус:** {'Открыто' if is_open else 'Ожидает открытия'}\n\n"
            f"🎯 **Готово к созданию!**\n"
            f"Проверьте данные и нажмите кнопку для создания задания."
        )
        
        return preview



    def _validate_url(self, url: str) -> bool:
        """Валидирует URL"""
        if not url:
            return False
        
        # Проверка на Telegram каналы/боты
        if url.startswith('@'):
            return len(url) > 1
        
        # Проверка на HTTP/HTTPS
        if url.startswith(('http://', 'https://')):
            return True
        
        # Проверка на t.me ссылки
        if url.startswith('t.me/'):
            return True
        
        return False

    def _check_task_title_exists(self, title: str) -> bool:
        """Проверяет, существует ли задание с таким названием"""
        try:
            with self.db._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT id FROM tasks WHERE title = ?', (title,))
                return cursor.fetchone() is not None
        except Exception:
            return False

    async def _apply_task_template(self, update: Update, context: ContextTypes.DEFAULT_TYPE, template_type: str):
        """Применяет шаблон задания"""
        templates = {
            'observation': {
                'title': 'Экологическое наблюдение',
                'description': 'Проведите наблюдение за природой в вашем районе. Сфотографируйте интересные природные объекты и поделитесь своими наблюдениями.',
                'link': None
            },
            'action': {
                'title': 'Экологическое действие',
                'description': 'Совершите одно полезное действие для окружающей среды. Это может быть уборка территории, посадка растений или сортировка отходов.',
                'link': None
            },
            'research': {
                'title': 'Исследование природы',
                'description': 'Проведите небольшое исследование природного объекта в вашем районе. Изучите его особенности и поделитесь результатами.',
                'link': None
            }
        }
        
        template = templates.get(template_type)
        if not template:
            await update.message.reply_text("❌ Неизвестный шаблон!")
            return ADDING_TASK_TITLE
        
        # Применяем шаблон
        current_date = datetime.now(self.moscow_tz)
        template['title'] = f"{template['title']} - {current_date.strftime('%d.%m.%Y')}"
        
        context.user_data['adding_task'] = template.copy()
        context.user_data['adding_task']['open_date'] = current_date
        
        # Автоматически устанавливаем дедлайн (через неделю)
        deadline = current_date + timedelta(days=7)
        deadline = deadline.replace(hour=23, minute=59, second=59)
        context.user_data['adding_task']['deadline'] = deadline
        
        # Показываем предварительный просмотр
        preview_text = self._generate_task_preview(context.user_data['adding_task'], deadline)
        
        keyboard = [
            [InlineKeyboardButton("✅ Создать задание", callback_data="confirm_create_task")],
            [InlineKeyboardButton("✏️ Изменить", callback_data="edit_task_preview")],
            [InlineKeyboardButton("❌ Отменить", callback_data="tasks_menu")]
        ]
        
        await update.message.reply_text(
            f"🎯 **Шаблон '{template_type}' применен!**\n\n{preview_text}",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        return ADDING_TASK_DEADLINE

    async def _show_tasks_list(self, query):
        """Показывает список всех заданий"""
        tasks = self.db.get_all_tasks()
        
        if not tasks:
            text = "📝 **Список заданий пуст**\n\nДобавьте первое задание!"
            keyboard = [
                [InlineKeyboardButton("➕ Добавить задание", callback_data="add_task")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
            ]
        else:
            text = f"📝 **Список заданий** (всего: {len(tasks)})\n\n"
            
            keyboard = []
            for task_id, title, description, link, is_open in tasks:
                status_emoji = "🟢" if is_open else "📁"
                short_title = title[:30] + "..." if len(title) > 30 else title
                
                keyboard.append([InlineKeyboardButton(
                    f"{status_emoji} {short_title}",
                    callback_data=f"task_{task_id}"
                )])
            
            keyboard.append([InlineKeyboardButton("➕ Добавить задание", callback_data="add_task")])
            keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")])
        
        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _handle_task_action(self, query, context, data):
        """Обрабатывает действия с заданием"""
        task_id = int(data.split('_')[1])
        
        # Получаем информацию о задании
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, title, description, link, is_open, week_number, deadline, open_date
                FROM tasks WHERE id = ?
            ''', (task_id,))
            task = cursor.fetchone()
            
            # Получаем количество отчетов по этому заданию
            cursor.execute('SELECT COUNT(*) FROM submissions WHERE task_id = ?', (task_id,))
            submissions_count = cursor.fetchone()[0]
        
        if not task:
            await query.edit_message_text("❌ Задание не найдено.")
            return
        
        task_id, title, description, link, is_open, week_number, deadline, open_date = task
        
        status = "🟢 Открыто" if is_open else "📁 Архив"
        deadline_str = "не установлен"
        if deadline:
            deadline_dt = datetime.fromisoformat(deadline)
            deadline_str = deadline_dt.strftime('%d.%m.%Y в %H:%M МСК')
        
        open_date_str = "не установлена"
        if open_date:
            open_date_dt = datetime.fromisoformat(open_date)
            open_date_str = open_date_dt.strftime('%d.%m.%Y в %H:%M МСК')
        
        text = (
            f"📋 **Информация о задании**\n\n"
            f"🆔 **ID:** {task_id}\n"
            f"📝 **Название:** {title}\n"
            f"📄 **Описание:** {description or 'не указано'}\n"
            f"🔗 **Ссылка:** {link or 'не указана'}\n"
            f"📅 **Дата открытия:** {open_date_str}\n"
            f"📅 **Неделя:** {week_number or 'не указана'} *(устаревшее поле)*\n"
            f"⏰ **Дедлайн:** {deadline_str}\n"
            f"📊 **Статус:** {status}\n"
            f"📤 **Отчетов получено:** {submissions_count}"
        )
        
        keyboard = [
            [InlineKeyboardButton("✏️ Редактировать", callback_data=f"edit_task_{task_id}")],
            [InlineKeyboardButton("📤 Отчеты по заданию", callback_data=f"task_reports_{task_id}")],
            [InlineKeyboardButton("🔄 Изменить статус", callback_data=f"toggle_task_{task_id}")],
            [InlineKeyboardButton("🗑️ Удалить", callback_data=f"delete_task_{task_id}")],
            [InlineKeyboardButton("📝 Список заданий", callback_data="list_tasks")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
        ]
        
        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _show_pending_reports(self, query):
        """Показывает отчеты, ожидающие проверки"""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT s.id, s.user_id, s.submission_date, s.submission_type, s.content, 
                       s.file_id, s.is_on_time, t.title, u.first_name, u.last_name
                FROM submissions s
                JOIN tasks t ON s.task_id = t.id
                LEFT JOIN users u ON s.user_id = u.user_id
                WHERE s.status = 'pending'
                ORDER BY s.submission_date ASC
                LIMIT 10
            ''')
            reports = cursor.fetchall()
        
        if not reports:
            text = "✅ **Нет отчетов, ожидающих проверки**"
            keyboard = [
                [InlineKeyboardButton("🔄 Обновить", callback_data="pending_reports")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
            ]
        else:
            text = f"⏳ **Отчеты, ожидающие проверки** (показано: {len(reports)})\n\n"
            
            keyboard = []
            for report in reports:
                submission_id, user_id, date, sub_type, content, file_id, is_on_time, task_title, first_name, last_name = report
                
                # Форматируем дату
                date_obj = datetime.fromisoformat(date.replace('Z', '+00:00'))
                formatted_date = date_obj.strftime("%d.%m %H:%M")
                
                # Имя пользователя
                user_name = f"{first_name or ''} {last_name or ''}".strip() or f"ID{user_id}"
                
                # Статус времени
                time_status = "⏰" if not is_on_time else "✅"
                
                # Тип отчета
                type_emoji = {"text": "📝", "photo": "📸", "video": "🎥", "document": "📄"}.get(sub_type, "📝")
                
                button_text = f"{type_emoji}{time_status} {user_name} • {formatted_date}"
                keyboard.append([InlineKeyboardButton(
                    button_text[:50],
                    callback_data=f"report_{submission_id}"
                )])
            
            keyboard.append([InlineKeyboardButton("🔄 Обновить", callback_data="pending_reports")])
            keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")])
        
        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _handle_report_action(self, query, context, data):
        """Обрабатывает действия с отчетом"""
        submission_id = int(data.split('_')[1])
        
        # Получаем подробную информацию об отчете
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT s.id, s.user_id, s.task_id, s.submission_date, s.submission_type, 
                       s.content, s.file_id, s.status, s.is_on_time,
                       t.title, t.description,
                       u.first_name, u.last_name, u.username
                FROM submissions s
                JOIN tasks t ON s.task_id = t.id
                LEFT JOIN users u ON s.user_id = u.user_id
                WHERE s.id = ?
            ''', (submission_id,))
            report = cursor.fetchone()
        
        if not report:
            await query.edit_message_text("❌ Отчет не найден.")
            return
        
        (sub_id, user_id, task_id, date, sub_type, content, file_id, status, 
         is_on_time, task_title, task_desc, first_name, last_name, username) = report
        
        # Форматируем информацию
        date_obj = datetime.fromisoformat(date.replace('Z', '+00:00'))
        formatted_date = date_obj.strftime("%d.%m.%Y в %H:%M МСК")
        
        user_name = f"{first_name or ''} {last_name or ''}".strip() or f"ID{user_id}"
        if username:
            user_name += f" (@{username})"
        
        time_status = "⏰ С опозданием" if not is_on_time else "✅ В срок"
        status_text = {"pending": "⏳ Ожидает проверки", "approved": "✅ Одобрен", "rejected": "❌ Отклонен"}.get(status, status)
        type_text = {"text": "📝 Текст", "photo": "📸 Фото", "video": "🎥 Видео", "document": "📄 Документ"}.get(sub_type, sub_type)
        
        text = (
            f"📤 **Отчет #{sub_id}**\n\n"
            f"👤 **Пользователь:** {user_name}\n"
            f"📋 **Задание:** {task_title}\n"
            f"📅 **Дата отправки:** {formatted_date}\n"
            f"📝 **Тип:** {type_text}\n"
            f"⏰ **Статус времени:** {time_status}\n"
            f"📊 **Статус проверки:** {status_text}\n\n"
            f"💬 **Содержимое:**\n{content[:500]}{'...' if len(content) > 500 else ''}"
        )
        
        keyboard = []
        
        if status == 'pending':
            keyboard.extend([
                [InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{sub_id}")],
                [InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{sub_id}")]
            ])
        
        if file_id:
            keyboard.append([InlineKeyboardButton("📎 Показать файл", callback_data=f"show_file_{sub_id}")])
        
        keyboard.extend([
            [InlineKeyboardButton("👤 Профиль пользователя", callback_data=f"user_profile_{user_id}")],
            [InlineKeyboardButton("📋 Задание", callback_data=f"task_{task_id}")],
            [InlineKeyboardButton("⏳ Ожидающие", callback_data="pending_reports")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
        ])
        
        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _approve_report(self, query, data):
        """Одобряет отчет"""
        submission_id = int(data.split('_')[1])
        
        # Обновляем статус в базе данных
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE submissions SET status = 'approved' WHERE id = ?
            ''', (submission_id,))
            conn.commit()
        
        await query.answer("✅ Отчет одобрен!")
        
        # Обновляем сообщение
        await self._handle_report_action(query, None, f"report_{submission_id}")

    async def _reject_report(self, query, data):
        """Отклоняет отчет"""
        submission_id = int(data.split('_')[1])
        
        # Обновляем статус в базе данных
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE submissions SET status = 'rejected' WHERE id = ?
            ''', (submission_id,))
            conn.commit()
        
        await query.answer("❌ Отчет отклонен!")
        
        # Обновляем сообщение
        await self._handle_report_action(query, None, f"report_{submission_id}")

    async def _show_potential_reports(self, query):
        """Показывает потенциальные отчеты для ручной обработки"""
        reports = self.db.get_potential_reports()
        
        if not reports:
            text = "✅ **Нет необработанных потенциальных отчетов**"
            keyboard = [
                [InlineKeyboardButton("🔄 Обновить", callback_data="potential_reports")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
            ]
        else:
            text = f"🔍 **Потенциальные отчеты** (найдено: {len(reports)})\n\n"
            text += "Это сообщения пользователей, которые могут быть отчетами, но были отправлены вне контекста задания.\n\n"
            
            keyboard = []
            for report_id, user_id, message_data, message_type, received_date in reports[:10]:
                try:
                    data = json.loads(message_data)
                    content = data.get('content', 'Нет содержимого')
                    msg_type = data.get('type', 'text')
                    
                    # Форматируем дату
                    date_obj = datetime.fromisoformat(received_date.replace('Z', '+00:00'))
                    formatted_date = date_obj.strftime("%d.%m.%Y в %H:%M МСК")
                    
                    type_emoji = {"text": "📝", "photo": "📸", "video": "🎥", "document": "📄"}.get(msg_type, "📝")
                    button_text = f"{type_emoji} ID{user_id} • {formatted_date}"
                    
                    keyboard.append([InlineKeyboardButton(
                        button_text,
                        callback_data=f"potential_{report_id}"
                    )])
                    
                except json.JSONDecodeError:
                    continue
            
            if len(reports) > 10:
                keyboard.append([InlineKeyboardButton(f"... и еще {len(reports) - 10}", callback_data="potential_reports_all")])
            
            keyboard.append([InlineKeyboardButton("🔄 Обновить", callback_data="potential_reports")])
            keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")])
        
        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _show_all_reports(self, query):
        """Показывает все отчеты с пагинацией"""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT s.id, s.user_id, s.submission_date, s.submission_type, s.status, 
                       s.is_on_time, t.title, u.first_name, u.last_name
                FROM submissions s
                JOIN tasks t ON s.task_id = t.id
                LEFT JOIN users u ON s.user_id = u.user_id
                ORDER BY s.submission_date DESC
                LIMIT 15
            ''')
            reports = cursor.fetchall()
            
            # Общее количество
            cursor.execute('SELECT COUNT(*) FROM submissions')
            total_count = cursor.fetchone()[0]
        
        if not reports:
            text = "📤 **Нет отчетов в системе**"
            keyboard = [
                [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
            ]
        else:
            text = f"📤 **Все отчеты** (показано: {len(reports)} из {total_count})\n\n"
            
            keyboard = []
            for report in reports:
                submission_id, user_id, date, sub_type, status, is_on_time, task_title, first_name, last_name = report
                
                # Форматируем дату
                date_obj = datetime.fromisoformat(date.replace('Z', '+00:00'))
                formatted_date = date_obj.strftime("%d.%m %H:%M")
                
                # Имя пользователя
                user_name = f"{first_name or ''} {last_name or ''}".strip() or f"ID{user_id}"
                
                # Статус
                status_emoji = {"pending": "⏳", "approved": "✅", "rejected": "❌"}.get(status, "❓")
                time_emoji = "⏰" if not is_on_time else "✅"
                type_emoji = {"text": "📝", "photo": "📸", "video": "🎥", "document": "📄"}.get(sub_type, "📝")
                
                button_text = f"{type_emoji}{status_emoji}{time_emoji} {user_name} • {formatted_date}"
                keyboard.append([InlineKeyboardButton(
                    button_text[:50],
                    callback_data=f"report_{submission_id}"
                )])
            
            if total_count > 15:
                keyboard.append([InlineKeyboardButton("📄 Показать еще", callback_data="all_reports_next")])
            
            keyboard.append([InlineKeyboardButton("📤 Отчеты", callback_data="reports_menu")])
            keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")])
        
        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _start_edit_task(self, query, context, data):
        """Начинает редактирование задания"""
        task_id = int(data.split('_')[2])  # edit_task_123
        
        # Получаем задание
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, title, description, link, is_open, week_number, deadline, open_date
                FROM tasks WHERE id = ?
            ''', (task_id,))
            task = cursor.fetchone()
        
        if not task:
            await query.edit_message_text("❌ Задание не найдено.")
            return
        
        task_id, title, description, link, is_open, week_number, deadline, open_date = task
        
        status = "🟢 Открыто" if is_open else "📁 Закрыто"
        deadline_str = "не установлен"
        if deadline:
            deadline_dt = datetime.fromisoformat(deadline)
            deadline_str = deadline_dt.strftime('%d.%m.%Y в %H:%M МСК')
        
        open_date_str = "не установлена"
        if open_date:
            open_date_dt = datetime.fromisoformat(open_date)
            open_date_str = open_date_dt.strftime('%d.%m.%Y в %H:%M МСК')
        
        text = (
            f"✏️ **Редактирование задания #{task_id}**\n\n"
            f"📝 **Название:** {title}\n"
            f"📄 **Описание:** {description or 'не указано'}\n"
            f"🔗 **Ссылка:** {link or 'не указана'}\n"
            f"📅 **Дата открытия:** {open_date_str}\n"
            f"📅 **Неделя:** {week_number or 'не указана'} *(устаревшее поле)*\n"
            f"⏰ **Дедлайн:** {deadline_str}\n"
            f"📊 **Статус:** {status}\n\n"
            f"Что хотите изменить?"
        )
        
        keyboard = [
            [InlineKeyboardButton("✏️ Название", callback_data=f"edit_title_{task_id}")],
            [InlineKeyboardButton("📄 Описание", callback_data=f"edit_desc_{task_id}")],
            [InlineKeyboardButton("🔗 Ссылку", callback_data=f"edit_link_{task_id}")],
            [InlineKeyboardButton("📅 Дату открытия", callback_data=f"edit_open_date_{task_id}")],
            [InlineKeyboardButton("⏰ Дедлайн", callback_data=f"edit_deadline_{task_id}")],
            [InlineKeyboardButton(f"📊 Статус ({status})", callback_data=f"toggle_task_{task_id}")],
            [InlineKeyboardButton("📋 Вернуться к заданию", callback_data=f"task_{task_id}")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
        ]
        
        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def handle_edit_title(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает ввод нового названия задания"""
        if not await self._check_admin_access(update):
            return
        
        new_title = update.message.text.strip()
        if len(new_title) < 5:
            await update.message.reply_text(
                "❌ Название задания должно содержать минимум 5 символов.\n"
                "Попробуйте еще раз:"
            )
            return
        
        task_id = context.user_data.get('editing_task_id')
        if not task_id:
            await update.message.reply_text("❌ Ошибка: ID задания не найден.")
            context.user_data.clear()
            return
        
        # Обновляем название в базе данных
        try:
            with self.db._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('UPDATE tasks SET title = ? WHERE id = ?', (new_title, task_id))
                conn.commit()
            
            keyboard = [
                [InlineKeyboardButton("📋 Вернуться к заданию", callback_data=f"task_{task_id}")],
                [InlineKeyboardButton("📝 Список заданий", callback_data="list_tasks")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
            ]
            
            await update.message.reply_text(
                f"✅ **Название задания успешно изменено!**\n\n"
                f"📝 **Новое название:** {new_title}",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
            # Очищаем данные
            context.user_data.clear()
            
        except Exception as e:
            logger.error(f"Ошибка при изменении названия задания: {e}")
            await update.message.reply_text(
                f"❌ Ошибка при изменении названия: {str(e)}"
            )

    async def _start_edit_description(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Начинает редактирование описания задания"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        task_id = int(data.split('_')[2])  # edit_desc_123
        
        # Сохраняем ID задания в контекст
        context.user_data['editing_task_id'] = task_id
        
        # Получаем задание
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT description FROM tasks WHERE id = ?', (task_id,))
            task = cursor.fetchone()
        
        if not task:
            await query.edit_message_text("❌ Задание не найдено.")
            return ConversationHandler.END
        
        current_description = task[0] or "не указано"
        
        text = (
            f"✏️ **Редактирование описания задания #{task_id}**\n\n"
            f"📄 **Текущее описание:** {current_description}\n\n"
            "Введите новое описание задания:\n\n"
            "💡 _Для отмены введите_ `/cancel`"
        )
        
        keyboard = [
            [InlineKeyboardButton("❌ Отмена", callback_data=f"task_{task_id}")]
        ]
        
        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        # Устанавливаем состояние редактирования
        context.user_data['editing_state'] = EDITING_TASK_DESCRIPTION

    async def handle_edit_description(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает ввод нового описания задания"""
        if not await self._check_admin_access(update):
            return
        
        new_description = update.message.text.strip()
        task_id = context.user_data.get('editing_task_id')
        
        if not task_id:
            await update.message.reply_text("❌ Ошибка: ID задания не найден.")
            context.user_data.clear()
            return
        
        # Обновляем описание в базе данных
        try:
            with self.db._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('UPDATE tasks SET description = ? WHERE id = ?', (new_description, task_id))
                conn.commit()
            
            keyboard = [
                [InlineKeyboardButton("📋 Вернуться к заданию", callback_data=f"task_{task_id}")],
                [InlineKeyboardButton("📝 Список заданий", callback_data="list_tasks")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
            ]
            
            await update.message.reply_text(
                f"✅ **Описание задания успешно изменено!**\n\n"
                f"📄 **Новое описание:** {new_description}",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
            # Очищаем данные
            context.user_data.clear()
            
        except Exception as e:
            logger.error(f"Ошибка при изменении описания задания: {e}")
            await update.message.reply_text(
                f"❌ Ошибка при изменении описания: {str(e)}"
            )

    async def _start_edit_title(self, update, context):
        """Начинает редактирование названия задания"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        task_id = int(data.split('_')[2])  # edit_title_123
        
        # Сохраняем ID задания в контекст
        context.user_data['editing_task_id'] = task_id
        
        # Получаем задание
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT title FROM tasks WHERE id = ?', (task_id,))
            task = cursor.fetchone()
        
        if not task:
            await query.edit_message_text("❌ Задание не найдено.")
            return ConversationHandler.END
        
        current_title = task[0] or "не указано"
        
        text = (
            f"✏️ **Редактирование названия задания #{task_id}**\n\n"
            f"📝 **Текущее название:** {current_title}\n\n"
            "Введите новое название задания:\n\n"
            "💡 _Для отмены введите_ `/cancel`"
        )
        
        keyboard = [
            [InlineKeyboardButton("❌ Отмена", callback_data=f"task_{task_id}")]
        ]
        
        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        # Устанавливаем состояние редактирования
        context.user_data['editing_state'] = EDITING_TASK_TITLE

    async def _start_edit_link(self, update, context):
        """Начинает редактирование ссылки задания"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        task_id = int(data.split('_')[2])  # edit_link_123
        
        # Сохраняем ID задания в контекст
        context.user_data['editing_task_id'] = task_id
        
        # Получаем задание
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT link FROM tasks WHERE id = ?', (task_id,))
            task = cursor.fetchone()
        
        if not task:
            await query.edit_message_text("❌ Задание не найдено.")
            return ConversationHandler.END
        
        current_link = task[0] or "не указана"
        
        text = (
            f"✏️ **Редактирование ссылки задания #{task_id}**\n\n"
            f"🔗 **Текущая ссылка:** {current_link}\n\n"
            "Введите новую ссылку на задание (или напишите 'нет' чтобы убрать ссылку):"
        )
        
        keyboard = [
            [InlineKeyboardButton("❌ Отмена", callback_data=f"task_{task_id}")]
        ]
        
        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        # Устанавливаем состояние редактирования
        context.user_data['editing_state'] = EDITING_TASK_LINK

    async def handle_edit_link(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает ввод новой ссылки задания"""
        if not await self._check_admin_access(update):
            return
        
        new_link = update.message.text.strip()
        if new_link.lower() in ['нет', 'no', '-', 'убрать']:
            new_link = None
        
        task_id = context.user_data.get('editing_task_id')
        if not task_id:
            await update.message.reply_text("❌ Ошибка: ID задания не найден.")
            context.user_data.clear()
            return
        
        # Обновляем ссылку в базе данных
        try:
            with self.db._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('UPDATE tasks SET link = ? WHERE id = ?', (new_link, task_id))
                conn.commit()
            
            keyboard = [
                [InlineKeyboardButton("📋 Вернуться к заданию", callback_data=f"task_{task_id}")],
                [InlineKeyboardButton("📝 Список заданий", callback_data="list_tasks")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
            ]
            
            await update.message.reply_text(
                f"✅ **Ссылка задания успешно изменена!**\n\n"
                f"🔗 **Новая ссылка:** {new_link or 'не указана'}",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
            # Очищаем данные
            context.user_data.clear()
            
        except Exception as e:
            logger.error(f"Ошибка при изменении ссылки задания: {e}")
            await update.message.reply_text(
                f"❌ Ошибка при изменении ссылки: {str(e)}"
            )

    async def _toggle_task_status(self, query, data):
        """Переключает статус задания (открыто/закрыто)"""
        task_id = int(data.split('_')[2])  # toggle_task_123
        
        # Переключаем статус
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            
            # Получаем текущий статус
            cursor.execute('SELECT is_open FROM tasks WHERE id = ?', (task_id,))
            result = cursor.fetchone()
            
            if not result:
                await query.answer("❌ Задание не найдено!")
                return
            
            current_status = result[0]
            new_status = not current_status
            
            # Обновляем статус
            cursor.execute('UPDATE tasks SET is_open = ? WHERE id = ?', (new_status, task_id))
            conn.commit()
        
        status_text = "открыто" if new_status else "закрыто"
        await query.answer(f"✅ Задание {status_text}!")
        
        # Возвращаемся к странице задания
        await self._handle_task_action(query, None, f"task_{task_id}")

    async def _delete_task(self, query, data):
        """Удаляет задание с подтверждением"""
        task_id = int(data.split('_')[2])  # delete_task_123
        
        # Получаем информацию о задании и количестве отчетов
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('SELECT title FROM tasks WHERE id = ?', (task_id,))
            task = cursor.fetchone()
            
            if not task:
                await query.answer("❌ Задание не найдено!")
                return
            
            cursor.execute('SELECT COUNT(*) FROM submissions WHERE task_id = ?', (task_id,))
            reports_count = cursor.fetchone()[0]
        
        title = task[0]
        
        text = (
            f"🗑️ **Удаление задания**\n\n"
            f"📝 **Задание:** {title}\n"
            f"📤 **Отчетов:** {reports_count}\n\n"
            f"⚠️ **Внимание!** Это действие нельзя отменить.\n"
            f"Все связанные отчеты также будут удалены.\n\n"
            f"Вы уверены?"
        )
        
        keyboard = [
            [InlineKeyboardButton("✅ Да, удалить", callback_data=f"confirm_delete_{task_id}")],
            [InlineKeyboardButton("❌ Отмена", callback_data=f"task_{task_id}")]
        ]
        
        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _confirm_delete_task(self, query, data):
        """Подтверждает удаление задания"""
        task_id = int(data.split('_')[2])  # confirm_delete_123
        
        try:
            with self.db._get_connection() as conn:
                cursor = conn.cursor()
                
                # Удаляем сначала все отчеты по заданию
                cursor.execute('DELETE FROM submissions WHERE task_id = ?', (task_id,))
                
                # Затем удаляем само задание
                cursor.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
                
                conn.commit()
            
            await query.answer("✅ Задание удалено!")
            
            # Переходим к списку заданий
            await self._show_tasks_list(query)
            
        except Exception as e:
            logger.error(f"Ошибка при удалении задания {task_id}: {e}")
            await query.answer("❌ Ошибка при удалении!")
            await self._handle_task_action(query, None, f"task_{task_id}")

    async def _show_task_reports(self, query, data):
        """Показывает отчеты по конкретному заданию"""
        task_id = int(data.split('_')[2])  # task_reports_123
        
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            
            # Получаем название задания
            cursor.execute('SELECT title FROM tasks WHERE id = ?', (task_id,))
            task = cursor.fetchone()
            
            if not task:
                await query.edit_message_text("❌ Задание не найдено.")
                return
            
            # Получаем отчеты по заданию
            cursor.execute('''
                SELECT s.id, s.user_id, s.submission_date, s.submission_type, s.status, 
                       s.is_on_time, u.first_name, u.last_name
                FROM submissions s
                LEFT JOIN users u ON s.user_id = u.user_id
                WHERE s.task_id = ?
                ORDER BY s.submission_date DESC
                LIMIT 10
            ''', (task_id,))
            reports = cursor.fetchall()
        
        task_title = task[0]
        
        if not reports:
            text = f"📋 **Отчеты по заданию**\n{task_title}\n\n📭 Отчетов пока нет."
            keyboard = [
                [InlineKeyboardButton("📋 Вернуться к заданию", callback_data=f"task_{task_id}")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
            ]
        else:
            text = f"📋 **Отчеты по заданию** ({len(reports)})\n{task_title}\n\n"
            
            keyboard = []
            for report in reports:
                submission_id, user_id, date, sub_type, status, is_on_time, first_name, last_name = report
                
                # Форматируем дату
                date_obj = datetime.fromisoformat(date.replace('Z', '+00:00'))
                formatted_date = date_obj.strftime("%d.%m %H:%M")
                
                # Имя пользователя
                user_name = f"{first_name or ''} {last_name or ''}".strip() or f"ID{user_id}"
                
                # Статусы
                status_emoji = {"pending": "⏳", "approved": "✅", "rejected": "❌"}.get(status, "❓")
                time_emoji = "⏰" if not is_on_time else "✅"
                type_emoji = {"text": "📝", "photo": "📸", "video": "🎥", "document": "📄"}.get(sub_type, "📝")
                
                button_text = f"{type_emoji}{status_emoji}{time_emoji} {user_name} • {formatted_date}"
                keyboard.append([InlineKeyboardButton(
                    button_text[:50],
                    callback_data=f"report_{submission_id}"
                )])
            
            keyboard.append([InlineKeyboardButton("📋 Вернуться к заданию", callback_data=f"task_{task_id}")])
            keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")])
        
        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _show_user_profile(self, query, data):
        """Показывает профиль пользователя"""
        user_id = int(data.split('_')[2])  # user_profile_123
        
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            
            # Получаем информацию о пользователе
            cursor.execute('''
                SELECT user_id, username, telegram_first_name, telegram_last_name,
                       first_name, last_name, participation_type, family_members_count,
                       children_info, registration_completed, registration_date
                FROM users WHERE user_id = ?
            ''', (user_id,))
            user = cursor.fetchone()
            
            if not user:
                await query.edit_message_text("❌ Пользователь не найден.")
                return
            
            # Статистика пользователя
            cursor.execute('SELECT COUNT(*) FROM submissions WHERE user_id = ?', (user_id,))
            total_submissions = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM submissions WHERE user_id = ? AND status = "approved"', (user_id,))
            approved_submissions = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM submissions WHERE user_id = ? AND is_on_time = TRUE', (user_id,))
            on_time_submissions = cursor.fetchone()[0]
        
        (uid, username, tg_first, tg_last, first_name, last_name, participation_type,
         family_count, children_info, registration_completed, reg_date) = user
        
        # Форматируем информацию
        full_name = f"{first_name or ''} {last_name or ''}".strip() or "Не указано"
        tg_name = f"{tg_first or ''} {tg_last or ''}".strip() or "Не указано"
        username_str = f"@{username}" if username else "Не указан"
        
        reg_status = "✅ Завершена" if registration_completed else "❌ Не завершена"
        participation = {"individual": "👤 Индивидуальное", "family": "👨‍👩‍👧‍👦 Семейное"}.get(participation_type, participation_type)
        
        if reg_date:
            reg_date_obj = datetime.fromisoformat(reg_date.replace('Z', '+00:00'))
            formatted_reg_date = reg_date_obj.strftime("%d.%m.%Y в %H:%M")
        else:
            formatted_reg_date = "Не указана"
        
        text = (
            f"👤 **Профиль пользователя**\n\n"
            f"🆔 **ID:** {uid}\n"
            f"👤 **Имя в Telegram:** {tg_name}\n"
            f"📱 **Username:** {username_str}\n"
            f"📝 **Полное имя:** {full_name}\n"
            f"🏠 **Тип участия:** {participation}\n"
            f"👨‍👩‍👧‍👦 **Участников в семье:** {family_count or 1}\n"
            f"👶 **Информация о детях:** {children_info or 'Не указана'}\n"
            f"✅ **Регистрация:** {reg_status}\n"
            f"📅 **Дата регистрации:** {formatted_reg_date}\n\n"
            f"📊 **Статистика:**\n"
            f"   • Всего отчетов: {total_submissions}\n"
            f"   • Одобрено: {approved_submissions}\n"
            f"   • В срок: {on_time_submissions}\n"
            f"   • Процент одобрения: {approved_submissions/max(total_submissions, 1)*100:.1f}%"
        )
        
        keyboard = [
            [InlineKeyboardButton("📤 Отчеты пользователя", callback_data=f"user_reports_{user_id}")],
            [InlineKeyboardButton("🔙 Назад", callback_data="reports_menu")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
        ]
        
        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _show_user_reports(self, query, data):
        """Показывает отчеты конкретного пользователя"""
        user_id = int(data.split('_')[2])  # user_reports_123
        
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            
            # Получаем имя пользователя
            cursor.execute('SELECT first_name, last_name FROM users WHERE user_id = ?', (user_id,))
            user = cursor.fetchone()
            
            if not user:
                await query.edit_message_text("❌ Пользователь не найден.")
                return
            
            user_name = f"{user[0] or ''} {user[1] or ''}".strip() or f"ID{user_id}"
            
            # Получаем отчеты пользователя
            cursor.execute('''
                SELECT s.id, s.submission_date, s.submission_type, s.status, 
                       s.is_on_time, t.title
                FROM submissions s
                JOIN tasks t ON s.task_id = t.id
                WHERE s.user_id = ?
                ORDER BY s.submission_date DESC
                LIMIT 10
            ''', (user_id,))
            reports = cursor.fetchall()
        
        if not reports:
            text = f"👤 **Отчеты пользователя**\n{user_name}\n\n📭 Отчетов пока нет."
            keyboard = [
                [InlineKeyboardButton("👤 Профиль", callback_data=f"user_profile_{user_id}")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
            ]
        else:
            text = f"👤 **Отчеты пользователя** ({len(reports)})\n{user_name}\n\n"
            
            keyboard = []
            for report in reports:
                submission_id, date, sub_type, status, is_on_time, task_title = report
                
                # Форматируем дату
                date_obj = datetime.fromisoformat(date.replace('Z', '+00:00'))
                formatted_date = date_obj.strftime("%d.%m %H:%M")
                
                # Статусы
                status_emoji = {"pending": "⏳", "approved": "✅", "rejected": "❌"}.get(status, "❓")
                time_emoji = "⏰" if not is_on_time else "✅"
                type_emoji = {"text": "📝", "photo": "📸", "video": "🎥", "document": "📄"}.get(sub_type, "📝")
                
                button_text = f"{type_emoji}{status_emoji}{time_emoji} {task_title[:20]}... • {formatted_date}"
                keyboard.append([InlineKeyboardButton(
                    button_text[:50],
                    callback_data=f"report_{submission_id}"
                )])
            
            keyboard.append([InlineKeyboardButton("👤 Профиль", callback_data=f"user_profile_{user_id}")])
            keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")])
        
        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _handle_export_data(self, query):
        """Обрабатывает команду экспорта данных"""
        text = (
            "📊 **Экспорт данных**\n\n"
            "Выберите тип данных для экспорта:"
        )
        
        keyboard = [
            [InlineKeyboardButton("👥 Пользователи", callback_data="export_users")],
            [InlineKeyboardButton("📋 Задания", callback_data="export_tasks")],
            [InlineKeyboardButton("📤 Отчеты", callback_data="export_submissions")],
            [InlineKeyboardButton("📊 Полная выгрузка", callback_data="export_full")],
            [InlineKeyboardButton("🔙 Системное меню", callback_data="system_menu")]
        ]
        
        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _handle_clear_logs(self, query):
        """Обрабатывает команду очистки логов"""
        # Проверяем размер логов
        log_stats = self._get_log_stats()
        
        text = (
            "🧹 **Очистка системных логов**\n\n"
            f"📂 **Текущий статус:**\n"
            f"• Потенциальные отчеты: {log_stats['potential_reports']}\n"
            f"• Обработанные офлайн-сообщения: {log_stats['processed_offline']}\n"
            f"• Записи состояний: {log_stats['user_states']}\n"
            f"• Старые запросы поддержки: {log_stats['old_support_requests']}\n\n"
            f"⚠️ **Внимание!** Это действие необратимо.\n"
            f"Рекомендуется сначала сделать экспорт данных.\n\n"
            f"Продолжить очистку?"
        )
        
        keyboard = [
            [InlineKeyboardButton("✅ Да, очистить", callback_data="confirm_clear_logs")],
            [InlineKeyboardButton("❌ Отмена", callback_data="system_menu")]
        ]
        
        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _confirm_clear_logs(self, query):
        """Подтверждает очистку логов"""
        try:
            cleaned = self._perform_log_cleanup()
            
            text = (
                "✅ **Очистка завершена успешно!**\n\n"
                f"📊 **Результаты:**\n"
                f"• Удалено потенциальных отчетов: {cleaned['potential_reports']}\n"
                f"• Удалено офлайн-сообщений: {cleaned['offline_messages']}\n"
                f"• Очищено старых состояний: {cleaned['old_states']}\n"
                f"• Архивировано запросов поддержки: {cleaned['support_requests']}\n\n"
                f"💾 **База данных оптимизирована**"
            )
            
        except Exception as e:
            logger.error(f"Ошибка при очистке логов: {e}")
            text = (
                "❌ **Ошибка при очистке!**\n\n"
                f"Подробности: {str(e)}\n\n"
                f"Проверьте логи для получения дополнительной информации."
            )
        
        keyboard = [
            [InlineKeyboardButton("🔧 Системное меню", callback_data="system_menu")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
        ]
        
        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _handle_specific_export(self, query, data):
        """Обрабатывает команду экспорта конкретных данных"""
        export_type = data.split('_')[1]  # export_users -> users
        
        try:
            # Генерируем файл экспорта
            file_path = await self._generate_export_file(export_type)
            
            if file_path:
                # Отправляем файл пользователю
                with open(file_path, 'rb') as file:
                    await query.message.reply_document(
                        document=file,
                        filename=os.path.basename(file_path),
                        caption=f"📊 Экспорт данных: {self._get_export_type_name(export_type)}"
                    )
                
                # Удаляем временный файл
                os.remove(file_path)
                
                await query.answer("✅ Файл отправлен!")
            else:
                await query.answer("❌ Ошибка при создании файла экспорта")
                
        except Exception as e:
            logger.error(f"Ошибка при экспорте {export_type}: {e}")
            await query.answer(f"❌ Ошибка: {str(e)}")
        
        # Возвращаемся к меню экспорта
        await self._handle_export_data(query)

    async def _send_local_file(self, query, file_path: str, caption: str):
        """Отправляет локальный файл пользователю"""
        try:
            full_path = os.path.join("uploaded_files", file_path)
            
            if not os.path.exists(full_path):
                await query.message.reply_text(
                    "❌ *Файл не найден на сервере*\n\n"
                    f"Файл был удален или перемещен\\.\n"
                    f"Путь: `{file_path}`",
                    parse_mode='MarkdownV2'
                )
                return False
            
            # Определяем тип файла по расширению
            file_extension = file_path.lower().split('.')[-1] if '.' in file_path else ''
            
            with open(full_path, 'rb') as file:
                if file_extension in ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp'] or 'photos/' in file_path:
                    await query.message.reply_photo(
                        photo=file,
                        caption=caption,
                        parse_mode='Markdown'
                    )
                elif file_extension in ['mp4', 'avi', 'mov', 'mkv', 'webm'] or 'videos/' in file_path:
                    await query.message.reply_video(
                        video=file,
                        caption=caption,
                        parse_mode='Markdown'
                    )
                else:
                    await query.message.reply_document(
                        document=file,
                        caption=caption,
                        parse_mode='Markdown',
                        filename=os.path.basename(file_path)
                    )
            
            await query.answer("✅ Файл отправлен!")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при отправке локального файла {file_path}: {e}")
            await query.answer("❌ Ошибка при отправке файла!")
            return False

    async def _show_file(self, query, data):
        """Показывает файл"""
        submission_id = int(data.split('_')[2])  # show_file_123
        
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT s.file_id, s.file_path, s.submission_type, s.content, 
                       u.first_name, u.last_name, t.title
                FROM submissions s
                LEFT JOIN users u ON s.user_id = u.user_id
                LEFT JOIN tasks t ON s.task_id = t.id
                WHERE s.id = ?
            ''', (submission_id,))
            result = cursor.fetchone()
        
        if not result:
            await query.answer("❌ Файл не найден!")
            return
        
        file_id, file_path, submission_type, content, first_name, last_name, task_title = result
        
        if not file_id and not file_path:
            await query.answer("❌ К этому отчету не прикреплен файл!")
            return
        
        user_name = f"{first_name or ''} {last_name or ''}".strip() or "Пользователь"
        caption = f"📁 **Файл к отчету**\n\n👤 **От:** {user_name}\n📋 **Задание:** {task_title}\n\n💬 **Комментарий:** {content[:100]}{'...' if len(content) > 100 else ''}"
        
        # Приоритет: сначала пробуем локальный файл, потом file_id
        if file_path:
            success = await self._send_local_file(query, file_path, caption)
            if success:
                return
        
        # Fallback к старому методу с file_id
        if file_id:
            try:
                if submission_type == 'photo':
                    await query.message.reply_photo(
                        photo=file_id,
                        caption=caption,
                        parse_mode='Markdown'
                    )
                elif submission_type == 'video':
                    await query.message.reply_video(
                        video=file_id,
                        caption=caption,
                        parse_mode='Markdown'
                    )
                elif submission_type == 'document':
                    await query.message.reply_document(
                        document=file_id,
                        caption=caption,
                        parse_mode='Markdown'
                    )
                else:
                    await query.answer("❌ Неподдерживаемый тип файла!")
                    return
                    
                await query.answer("✅ Файл отправлен (через file_id)!")
                
            except Exception as e:
                logger.error(f"Ошибка при отправке файла {file_id}: {e}")
                
                # Проверяем специфические ошибки Telegram
                error_message = str(e).lower()
                if "wrong file identifier" in error_message or "file not found" in error_message:
                    await query.answer("❌ Файл больше недоступен (устарел file_id)")
                    
                    # Уведомляем пользователя подробнее
                    await query.message.reply_text(
                        "⚠️ *Файл недоступен*\n\n"
                        f"Файл к отчету №{submission_id} больше не может быть загружен\\.\n"
                        "Это происходит когда file\\_id устаревает в системе Telegram\\.\n\n"
                        "💡 *Решение:* Попросите пользователя отправить файл повторно\\.",
                        parse_mode='MarkdownV2'
                    )
                else:
                    await query.answer("❌ Ошибка при отправке файла!")
        else:
            await query.answer("❌ Файл недоступен!")

    async def _handle_potential_report(self, query, data):
        """Обрабатывает потенциальный отчет"""
        report_id = int(data.split('_')[1])  # potential_123
        
        # Получаем информацию о потенциальном отчете
        reports = self.db.get_potential_reports()
        potential_report = None
        
        for report in reports:
            if report[0] == report_id:  # report[0] это ID
                potential_report = report
                break
        
        if not potential_report:
            await query.edit_message_text("❌ Потенциальный отчет не найден.")
            return
        
        report_id, user_id, message_data, message_type, received_date = potential_report
        
        try:
            data_dict = json.loads(message_data)
            content = data_dict.get('content', 'Нет содержимого')
            msg_type = data_dict.get('type', 'text')
            file_id = data_dict.get('file_id')
            
            # Форматируем дату
            date_obj = datetime.fromisoformat(received_date.replace('Z', '+00:00'))
            formatted_date = date_obj.strftime("%d.%m.%Y в %H:%M МСК")
            
            # Получаем информацию о пользователе
            with self.db._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT first_name, last_name, username FROM users WHERE user_id = ?', (user_id,))
                user_info = cursor.fetchone()
            
            if user_info:
                first_name, last_name, username = user_info
                user_name = f"{first_name or ''} {last_name or ''}".strip() or f"ID{user_id}"
                if username:
                    user_name += f" (@{username})"
            else:
                user_name = f"ID{user_id}"
            
            type_emoji = {"text": "📝", "photo": "📸", "video": "🎥", "document": "📄"}.get(msg_type, "📝")
            
            text = (
                f"🔍 **Потенциальный отчет #{report_id}**\n\n"
                f"👤 **Пользователь:** {user_name}\n"
                f"📅 **Дата получения:** {formatted_date}\n"
                f"📝 **Тип:** {type_emoji} {msg_type.title()}\n\n"
                f"💬 **Содержимое:**\n{content[:500]}{'...' if len(content) > 500 else ''}"
            )
            
            # Получаем список открытых заданий для привязки
            with self.db._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT id, title FROM tasks WHERE is_open = TRUE ORDER BY id DESC LIMIT 5')
                open_tasks = cursor.fetchall()
            
            keyboard = []
            
            # Кнопки для привязки к заданиям
            if open_tasks:
                keyboard.append([InlineKeyboardButton("📋 Привязать к заданию:", callback_data="dummy")])
                for task_id, task_title in open_tasks:
                    short_title = task_title[:30] + "..." if len(task_title) > 30 else task_title
                    keyboard.append([InlineKeyboardButton(
                        f"📝 {short_title}",
                        callback_data=f"assign_potential_{report_id}_{task_id}"
                    )])
            
            # Кнопки управления
            keyboard.extend([
                [InlineKeyboardButton("✅ Отметить как обработанный", callback_data=f"mark_processed_{report_id}")],
                [InlineKeyboardButton("❌ Удалить", callback_data=f"delete_potential_{report_id}")],
            ])
            
            if file_id:
                keyboard.append([InlineKeyboardButton("📎 Показать файл", callback_data=f"show_potential_file_{report_id}")])
            
            keyboard.extend([
                [InlineKeyboardButton("🔍 Потенциальные отчеты", callback_data="potential_reports")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
            ])
            
            await query.edit_message_text(
                text,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
        except json.JSONDecodeError:
            await query.edit_message_text("❌ Ошибка при обработке данных потенциального отчета.")
        except Exception as e:
            logger.error(f"Ошибка при обработке потенциального отчета {report_id}: {e}")
            await query.edit_message_text("❌ Произошла ошибка при обработке отчета.")

    def _get_log_stats(self) -> Dict[str, int]:
        """Получает статистику для очистки логов"""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            
            # Потенциальные отчеты
            cursor.execute("SELECT COUNT(*) FROM offline_messages WHERE message_type = 'potential_report' AND processed = FALSE")
            potential_reports = cursor.fetchone()[0]
            
            # Обработанные офлайн-сообщения старше 30 дней
            cursor.execute("""
                SELECT COUNT(*) FROM offline_messages 
                WHERE processed = TRUE 
                AND received_date < date('now', '-30 days')
            """)
            processed_offline = cursor.fetchone()[0]
            
            # Записи состояний старше 7 дней
            cursor.execute("""
                SELECT COUNT(*) FROM user_states 
                WHERE last_updated < datetime('now', '-7 days')
            """)
            user_states = cursor.fetchone()[0]
            
            # Закрытые запросы поддержки старше 30 дней
            cursor.execute("""
                SELECT COUNT(*) FROM support_requests 
                WHERE status = 'closed' 
                AND request_date < date('now', '-30 days')
            """)
            old_support_requests = cursor.fetchone()[0]
            
            return {
                'potential_reports': potential_reports,
                'processed_offline': processed_offline,
                'user_states': user_states,
                'old_support_requests': old_support_requests
            }

    def _perform_log_cleanup(self) -> Dict[str, int]:
        """Выполняет очистку логов и возвращает количество удаленных записей"""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            
            # Удаляем обработанные потенциальные отчеты
            cursor.execute("DELETE FROM offline_messages WHERE message_type = 'potential_report' AND processed = TRUE")
            potential_reports = cursor.rowcount
            
            # Удаляем старые офлайн-сообщения (старше 30 дней)
            cursor.execute("DELETE FROM offline_messages WHERE processed = TRUE AND received_date < date('now', '-30 days')")
            offline_messages = cursor.rowcount
            
            # Удаляем старые состояния пользователей (старше 7 дней)
            cursor.execute("DELETE FROM user_states WHERE last_updated < datetime('now', '-7 days')")
            old_states = cursor.rowcount
            
            # Архивируем старые запросы поддержки
            cursor.execute("UPDATE support_requests SET status = 'archived' WHERE status = 'closed' AND request_date < date('now', '-30 days')")
            support_requests = cursor.rowcount
            
            # Оптимизируем базу данных
            cursor.execute("VACUUM")
            
            conn.commit()
            
            return {
                'potential_reports': potential_reports,
                'offline_messages': offline_messages,
                'old_states': old_states,
                'support_requests': support_requests
            }

    async def _generate_export_file(self, export_type: str) -> str:
        """Генерирует файл экспорта данных"""
        import csv
        import tempfile
        
        timestamp = datetime.now(self.moscow_tz).strftime("%Y%m%d_%H%M%S")
        
        if export_type == "users":
            return await self._export_users_to_csv(timestamp)
        elif export_type == "tasks":
            return await self._export_tasks_to_csv(timestamp)
        elif export_type == "submissions":
            return await self._export_submissions_to_csv(timestamp)
        elif export_type == "full":
            return await self._export_full_data(timestamp)
        else:
            return None

    async def _export_users_to_csv(self, timestamp: str) -> str:
        """Экспортирует пользователей в CSV"""
        import csv
        import tempfile
        
        filename = f"eco_bot_users_{timestamp}.csv"
        temp_path = os.path.join(tempfile.gettempdir(), filename)
        
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT user_id, username, telegram_first_name, telegram_last_name,
                       first_name, last_name, participation_type, family_members_count,
                       children_info, registration_completed, registration_date
                FROM users ORDER BY registration_date DESC
            """)
            users = cursor.fetchall()
        
        with open(temp_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow([
                'User ID', 'Username', 'Telegram First Name', 'Telegram Last Name',
                'First Name', 'Last Name', 'Participation Type', 'Family Members',
                'Children Info', 'Registration Completed', 'Registration Date'
            ])
            writer.writerows(users)
        
        return temp_path

    async def _export_tasks_to_csv(self, timestamp: str) -> str:
        """Экспортирует задания в CSV"""
        import csv
        import tempfile
        
        filename = f"eco_bot_tasks_{timestamp}.csv"
        temp_path = os.path.join(tempfile.gettempdir(), filename)
        
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, title, description, link, is_open, week_number, deadline, open_date
                FROM tasks ORDER BY id DESC
            """)
            tasks = cursor.fetchall()
        
        with open(temp_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow([
                'ID', 'Title', 'Description', 'Link', 'Is Open', 'Week Number', 'Deadline', 'Open Date'
            ])
            writer.writerows(tasks)
        
        return temp_path

    async def _export_submissions_to_csv(self, timestamp: str) -> str:
        """Экспортирует отчеты в CSV"""
        import csv
        import tempfile
        
        filename = f"eco_bot_submissions_{timestamp}.csv"
        temp_path = os.path.join(tempfile.gettempdir(), filename)
        
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT s.id, s.user_id, s.task_id, s.submission_date, s.submission_type,
                       s.content, s.file_id, s.status, s.is_on_time, t.title, u.first_name, u.last_name
                FROM submissions s
                LEFT JOIN tasks t ON s.task_id = t.id
                LEFT JOIN users u ON s.user_id = u.user_id
                ORDER BY s.submission_date DESC
            """)
            submissions = cursor.fetchall()
        
        with open(temp_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow([
                'ID', 'User ID', 'Task ID', 'Submission Date', 'Type',
                'Content', 'File ID', 'Status', 'On Time', 'Task Title', 'First Name', 'Last Name'
            ])
            writer.writerows(submissions)
        
        return temp_path

    async def _export_full_data(self, timestamp: str) -> str:
        """Создает полный экспорт всех данных в ZIP архиве"""
        import zipfile
        import tempfile
        
        # Создаем временные CSV файлы
        users_file = await self._export_users_to_csv(timestamp)
        tasks_file = await self._export_tasks_to_csv(timestamp)
        submissions_file = await self._export_submissions_to_csv(timestamp)
        
        # Создаем ZIP архив
        zip_filename = f"eco_bot_full_export_{timestamp}.zip"
        zip_path = os.path.join(tempfile.gettempdir(), zip_filename)
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            zipf.write(users_file, os.path.basename(users_file))
            zipf.write(tasks_file, os.path.basename(tasks_file))
            zipf.write(submissions_file, os.path.basename(submissions_file))
            
            # Добавляем файл с метаданными
            metadata = f"""Экспорт данных Эко-бота
Дата создания: {datetime.now(self.moscow_tz).strftime('%d.%m.%Y %H:%M:%S МСК')}
Версия: 1.0

Содержимое архива:
- {os.path.basename(users_file)} - данные пользователей
- {os.path.basename(tasks_file)} - данные заданий  
- {os.path.basename(submissions_file)} - данные отчетов

Кодировка: UTF-8
Разделитель CSV: запятая
"""
            zipf.writestr("README.txt", metadata.encode('utf-8'))
        
        # Удаляем временные CSV файлы
        os.remove(users_file)
        os.remove(tasks_file)
        os.remove(submissions_file)
        
        return zip_path

    def _get_export_type_name(self, export_type: str) -> str:
        """Возвращает читаемое название типа экспорта"""
        names = {
            'users': 'Пользователи',
            'tasks': 'Задания',
            'submissions': 'Отчеты',
            'full': 'Полная выгрузка'
        }
        return names.get(export_type, export_type)

    async def _assign_potential_to_task(self, query, data):
        """Привязывает потенциальный отчет к заданию"""
        report_id, task_id = data.split('_')[2:]
        
        # Получаем информацию о задании
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, title, description, link, is_open, week_number, deadline, open_date
                FROM tasks WHERE id = ?
            ''', (task_id,))
            task = cursor.fetchone()
        
        if not task:
            await query.edit_message_text("❌ Задание не найдено.")
            return
        
        task_id, title, description, link, is_open, week_number, deadline, open_date = task
        
        # Получаем информацию о потенциальном отчете
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, user_id, message_data, message_type, received_date
                FROM offline_messages WHERE id = ?
            ''', (report_id,))
            potential_report = cursor.fetchone()
        
        if not potential_report:
            await query.edit_message_text("❌ Потенциальный отчет не найден.")
            return
        
        report_id, user_id, message_data, message_type, received_date = potential_report
        
        try:
            data_dict = json.loads(message_data)
            content = data_dict.get('content', 'Нет содержимого')
            msg_type = data_dict.get('type', 'text')
            file_id = data_dict.get('file_id')
            
            # Создаем новый отчет
            with self.db._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO submissions (user_id, task_id, submission_date, submission_type, content, file_id, status, is_on_time)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (user_id, task_id, datetime.now(self.moscow_tz).isoformat(), 'text', content, file_id, 'pending', True))
                submission_id = cursor.lastrowid
                conn.commit()
            
            # Обновляем статус потенциального отчета
            with self.db._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE offline_messages SET processed = TRUE WHERE id = ?
                ''', (report_id,))
                conn.commit()
            
            await query.answer("✅ Потенциальный отчет привязан к заданию!")
            
            # Возвращаемся к списку заданий
            await self._show_tasks_list(query)
            
        except Exception as e:
            logger.error(f"Ошибка при привязке потенциального отчета: {e}")
            await query.answer("❌ Ошибка при привязке потенциального отчета!")

    async def _mark_potential_processed(self, query, data):
        """Отмечает потенциальный отчет как обработанный"""
        report_id = int(data.split('_')[1])  # mark_processed_123
        
        # Обновляем статус в базе данных
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE offline_messages SET processed = TRUE WHERE id = ?
            ''', (report_id,))
            conn.commit()
        
        await query.answer("✅ Потенциальный отчет отмечен как обработанный!")
        
        # Возвращаемся к списку заданий
        await self._show_tasks_list(query)

    async def _delete_potential_report(self, query, data):
        """Удаляет потенциальный отчет"""
        report_id = int(data.split('_')[1])  # delete_potential_123
        
        # Получаем информацию о потенциальном отчете
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, user_id, message_data, message_type, received_date
                FROM offline_messages WHERE id = ?
            ''', (report_id,))
            potential_report = cursor.fetchone()
        
        if not potential_report:
            await query.edit_message_text("❌ Потенциальный отчет не найден.")
            return
        
        report_id, user_id, message_data, message_type, received_date = potential_report
        
        try:
            # Удаляем потенциальный отчет
            with self.db._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    DELETE FROM offline_messages WHERE id = ?
                ''', (report_id,))
                conn.commit()
            
            await query.answer("✅ Потенциальный отчет удален!")
            
            # Возвращаемся к списку заданий
            await self._show_tasks_list(query)
            
        except Exception as e:
            logger.error(f"Ошибка при удалении потенциального отчета: {e}")
            await query.answer("❌ Ошибка при удалении потенциального отчета!")

    async def _show_potential_file(self, query, data):
        """Показывает файл потенциального отчета"""
        report_id = int(data.split('_')[3])  # show_potential_file_123
        
        # Получаем информацию о потенциальном отчете из offline_messages
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT user_id, message_data
                FROM offline_messages WHERE id = ?
            ''', (report_id,))
            result = cursor.fetchone()
        
        if not result:
            await query.answer("❌ Потенциальный отчет не найден!")
            return
        
        user_id, message_data = result
        
        try:
            data_dict = json.loads(message_data)
            file_id = data_dict.get('file_id')
            file_path = data_dict.get('file_path')  # Новое поле
            content = data_dict.get('content', 'Нет содержимого')
            msg_type = data_dict.get('type', 'text')
            
            if not file_id and not file_path:
                await query.answer("❌ К этому потенциальному отчету не прикреплен файл!")
                return
            
            # Получаем информацию о пользователе
            with self.db._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT first_name, last_name FROM users WHERE user_id = ?', (user_id,))
                user_info = cursor.fetchone()
            
            user_name = "Пользователь"
            if user_info:
                user_name = f"{user_info[0] or ''} {user_info[1] or ''}".strip() or f"ID{user_id}"
            
            caption = f"📁 **Файл потенциального отчета**\n\n👤 **От:** {user_name}\n\n💬 **Содержимое:** {content[:100]}{'...' if len(content) > 100 else ''}"
            
            # Приоритет: сначала пробуем локальный файл, потом file_id
            if file_path:
                success = await self._send_local_file(query, file_path, caption)
                if success:
                    return
            
            # Fallback к старому методу с file_id
            if file_id:
                try:
                    if msg_type == 'photo':
                        await query.message.reply_photo(
                            photo=file_id,
                            caption=caption,
                            parse_mode='Markdown'
                        )
                    elif msg_type == 'video':
                        await query.message.reply_video(
                            video=file_id,
                            caption=caption,
                            parse_mode='Markdown'
                        )
                    elif msg_type == 'document':
                        await query.message.reply_document(
                            document=file_id,
                            caption=caption,
                            parse_mode='Markdown'
                        )
                    else:
                        await query.answer("❌ Неподдерживаемый тип файла!")
                        return
                        
                    await query.answer("✅ Файл отправлен (через file_id)!")
                    
                except Exception as e:
                    logger.error(f"Ошибка при отправке потенциального файла {file_id}: {e}")
                    
                    # Проверяем специфические ошибки Telegram
                    error_message = str(e).lower()
                    if "wrong file identifier" in error_message or "file not found" in error_message:
                        await query.answer("❌ Файл больше недоступен (устарел file_id)")
                        
                        # Уведомляем пользователя подробнее
                        await query.message.reply_text(
                            "⚠️ *Файл недоступен*\n\n"
                            f"Файл потенциального отчета №{report_id} больше не может быть загружен\\.\n"
                            "Это происходит когда file\\_id устаревает в системе Telegram\\.\n\n"
                            "💡 *Решение:* Файл был отправлен слишком давно и недоступен для загрузки.",
                            parse_mode='MarkdownV2'
                        )
                    else:
                        await query.answer("❌ Ошибка при отправке файла!")
            else:
                await query.answer("❌ Файл недоступен!")
                
        except json.JSONDecodeError:
            await query.answer("❌ Ошибка при обработке данных!")
        except Exception as e:
            logger.error(f"Ошибка при обработке потенциального файла: {e}")
            await query.answer("❌ Произошла ошибка!")

    async def _start_edit_open_date(self, update, context):
        """Начинает редактирование даты открытия задания"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        task_id = int(data.split('_')[3])  # edit_open_date_123
        
        # Сохраняем ID задания в контекст
        context.user_data['editing_task_id'] = task_id
        
        # Получаем задание
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT open_date FROM tasks WHERE id = ?', (task_id,))
            task = cursor.fetchone()
        
        if not task:
            await query.edit_message_text("❌ Задание не найдено.")
            return ConversationHandler.END
        
        current_open_date = task[0]
        if current_open_date:
            open_date_dt = datetime.fromisoformat(current_open_date)
            current_open_date_str = open_date_dt.strftime('%d.%m.%Y в %H:%M МСК')
        else:
            current_open_date_str = "не установлена"
        
        text = (
            f"✏️ **Редактирование даты открытия задания #{task_id}**\n\n"
            f"📅 **Текущая дата открытия:** {current_open_date_str}\n\n"
            "Введите новую дату открытия задания:\n\n"
            "📋 **Варианты ввода:**\n"
            "• `сейчас` - открыть сейчас\n"
            "• `завтра` - завтра в 09:00\n"
            "• `ДД.ММ.ГГГГ` - конкретная дата в 09:00\n"
            "• `ДД.ММ.ГГГГ ЧЧ:ММ` - конкретная дата и время\n"
            "• `неделя` - через неделю в 09:00\n\n"
            "💡 _Для отмены введите_ `/cancel`"
        )
        
        keyboard = [
            [InlineKeyboardButton("❌ Отмена", callback_data=f"task_{task_id}")]
        ]
        
        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        # Устанавливаем состояние редактирования
        context.user_data['editing_state'] = EDITING_TASK_OPEN_DATE

    async def handle_edit_open_date(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает ввод новой даты открытия задания"""
        if not await self._check_admin_access(update):
            return
        
        open_date_input = update.message.text.strip().lower()
        task_id = context.user_data.get('editing_task_id')
        
        if not task_id:
            await update.message.reply_text("❌ Ошибка: ID задания не найден.")
            context.user_data.clear()
            return
        
        try:
            # Обработка различных вариантов ввода
            if open_date_input in ['сейчас', 'now']:
                new_open_date = datetime.now(self.moscow_tz)
            elif open_date_input in ['завтра', 'tomorrow']:
                new_open_date = datetime.now(self.moscow_tz) + timedelta(days=1)
                new_open_date = new_open_date.replace(hour=9, minute=0, second=0, microsecond=0)
            elif open_date_input in ['неделя', 'week']:
                new_open_date = datetime.now(self.moscow_tz) + timedelta(weeks=1)
                new_open_date = new_open_date.replace(hour=9, minute=0, second=0, microsecond=0)
            else:
                # Попытка парсинга ручного ввода
                try:
                    if ' ' in open_date_input:
                        # Формат с временем
                        new_open_date = datetime.strptime(open_date_input, '%d.%m.%Y %H:%M')
                    else:
                        # Только дата, время по умолчанию 09:00
                        new_open_date = datetime.strptime(open_date_input, '%d.%m.%Y')
                        new_open_date = new_open_date.replace(hour=9, minute=0)
                    
                    new_open_date = self.moscow_tz.localize(new_open_date)
                except ValueError:
                    raise ValueError("Неверный формат даты")
                
                # Проверка, что дата открытия не в прошлом (с учетом текущего времени)
                if new_open_date < datetime.now(self.moscow_tz):
                    await update.message.reply_text(
                        "❌ **Дата открытия в прошлом**\n\n"
                        "Дата открытия должна быть в будущем или сейчас.\n"
                        "Попробуйте еще раз:"
                    )
                    return
                    
        except ValueError as e:
            await update.message.reply_text(
                "❌ **Неверный формат даты**\n\n"
                "Используйте один из форматов:\n"
                "• `ДД.ММ.ГГГГ ЧЧ:ММ` (например: 25.12.2024 09:00)\n"
                "• `ДД.ММ.ГГГГ` (время установится 09:00)\n"
                "• `сейчас` - открыть сейчас\n"
                "• `завтра` - завтра в 09:00\n"
                "• `неделя` - через неделю в 09:00"
            )
            return
        
        # Обновляем дату открытия в базе данных
        try:
            # Также обновляем статус is_open в зависимости от новой даты
            is_open = new_open_date <= datetime.now(self.moscow_tz)
            
            with self.db._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'UPDATE tasks SET open_date = ?, is_open = ? WHERE id = ?', 
                    (new_open_date.isoformat(), is_open, task_id)
                )
                conn.commit()
            
            keyboard = [
                [InlineKeyboardButton("📋 Вернуться к заданию", callback_data=f"task_{task_id}")],
                [InlineKeyboardButton("📝 Список заданий", callback_data="list_tasks")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
            ]
            
            status_text = "открыто" if is_open else "ожидает открытия"
            
            await update.message.reply_text(
                f"✅ **Дата открытия задания успешно изменена!**\n\n"
                f"📅 **Новая дата открытия:** {new_open_date.strftime('%d.%m.%Y в %H:%M МСК')}\n"
                f"📊 **Статус задания:** {status_text}",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
            # Очищаем данные
            context.user_data.clear()
            
        except Exception as e:
            logger.error(f"Ошибка при изменении даты открытия задания: {e}")
            await update.message.reply_text(
                f"❌ Ошибка при изменении даты открытия: {str(e)}"
            )

    async def _start_edit_deadline(self, update, context):
        """Начинает редактирование дедлайна задания"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        task_id = int(data.split('_')[2])  # edit_deadline_123
        
        # Сохраняем ID задания в контекст
        context.user_data['editing_task_id'] = task_id
        
        # Получаем задание
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT deadline, open_date FROM tasks WHERE id = ?', (task_id,))
            task = cursor.fetchone()
            
        if not task:
            await query.edit_message_text("❌ Задание не найдено.")
            return ConversationHandler.END
        
        current_deadline, open_date = task
        if current_deadline:
            deadline_dt = datetime.fromisoformat(current_deadline)
            current_deadline_str = deadline_dt.strftime('%d.%m.%Y в %H:%M МСК')
        else:
            current_deadline_str = "не установлен"
        
        # Предлагаем автоматический дедлайн
        if open_date:
            open_date_dt = datetime.fromisoformat(open_date)
            suggested_deadline = open_date_dt + timedelta(days=7)
            suggested_deadline = suggested_deadline.replace(hour=23, minute=59, second=59)
            suggested_str = suggested_deadline.strftime('%d.%m.%Y в %H:%M МСК')
        else:
            suggested_deadline = datetime.now(self.moscow_tz) + timedelta(days=7)
            suggested_deadline = suggested_deadline.replace(hour=23, minute=59, second=59)
            suggested_str = suggested_deadline.strftime('%d.%m.%Y в %H:%M МСК')
        
        text = (
            f"✏️ **Редактирование дедлайна задания #{task_id}**\n\n"
            f"⏰ **Текущий дедлайн:** {current_deadline_str}\n"
            f"💡 **Предлагаемый дедлайн:** {suggested_str}\n\n"
            "Введите новый дедлайн задания:\n\n"
            "📋 **Варианты ввода:**\n"
            "• `авто` - автоматический расчет (через неделю)\n"
            "• `завтра` - завтра в 23:59\n"
            "• `ДД.ММ.ГГГГ` - конкретная дата в 23:59\n"
            "• `ДД.ММ.ГГГГ ЧЧ:ММ` - конкретная дата и время\n"
            "• `неделя` - через неделю в 23:59\n"
            "• `нет` - убрать дедлайн\n\n"
            "💡 _Для отмены введите_ `/cancel`"
        )
        
        keyboard = [
            [InlineKeyboardButton("❌ Отмена", callback_data=f"task_{task_id}")]
        ]
        
        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        # Устанавливаем состояние редактирования
        context.user_data['editing_state'] = EDITING_TASK_DEADLINE

    async def handle_edit_deadline(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает ввод нового дедлайна задания"""
        if not await self._check_admin_access(update):
            return
        
        deadline_input = update.message.text.strip().lower()
        task_id = context.user_data.get('editing_task_id')
        
        if not task_id:
            await update.message.reply_text("❌ Ошибка: ID задания не найден.")
            context.user_data.clear()
            return
        
        # Получаем дату открытия для валидации
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT open_date FROM tasks WHERE id = ?', (task_id,))
            result = cursor.fetchone()
            open_date = result[0] if result else None
        
        try:
            # Обработка различных вариантов ввода дедлайна
            if deadline_input in ['авто', 'auto']:
                # Автоматический дедлайн: через неделю после открытия
                if open_date:
                    open_date_dt = datetime.fromisoformat(open_date)
                    new_deadline = open_date_dt + timedelta(days=7)
                else:
                    new_deadline = datetime.now(self.moscow_tz) + timedelta(days=7)
                new_deadline = new_deadline.replace(hour=23, minute=59, second=59)
            elif deadline_input in ['завтра', 'tomorrow']:
                new_deadline = datetime.now(self.moscow_tz).replace(hour=23, minute=59, second=59) + timedelta(days=1)
            elif deadline_input in ['неделя', 'week']:
                new_deadline = datetime.now(self.moscow_tz) + timedelta(weeks=1)
                new_deadline = new_deadline.replace(hour=23, minute=59, second=59)
            elif deadline_input in ['нет', 'no', '-']:
                new_deadline = None
            else:
                # Попытка парсинга ручного ввода
                try:
                    if ' ' in deadline_input:
                        new_deadline = datetime.strptime(deadline_input, '%d.%m.%Y %H:%M')
                    else:
                        new_deadline = datetime.strptime(deadline_input, '%d.%m.%Y')
                        new_deadline = new_deadline.replace(hour=23, minute=59)
                    
                    new_deadline = self.moscow_tz.localize(new_deadline)
                except ValueError:
                    raise ValueError("Неверный формат даты")
                
                # Проверка, что дедлайн в будущем
                if new_deadline and new_deadline <= datetime.now(self.moscow_tz):
                    await update.message.reply_text(
                        "❌ **Дедлайн в прошлом**\n\n"
                        "Дедлайн должен быть в будущем.\n"
                        "Попробуйте еще раз:"
                    )
                    return
                
                # Проверка, что дедлайн не раньше даты открытия
                if new_deadline and open_date:
                    open_date_dt = datetime.fromisoformat(open_date)
                    if new_deadline <= open_date_dt:
                        await update.message.reply_text(
                            "❌ **Дедлайн раньше даты открытия**\n\n"
                            "Дедлайн должен быть позже даты открытия задания.\n"
                            "Попробуйте еще раз:"
                        )
                        return
                    
        except ValueError as e:
            await update.message.reply_text(
                "❌ **Неверный формат даты**\n\n"
                "Используйте один из форматов:\n"
                "• `ДД.ММ.ГГГГ ЧЧ:ММ` (например: 25.12.2024 23:59)\n"
                "• `ДД.ММ.ГГГГ` (время установится 23:59)\n"
                "• `авто` - автоматический расчет\n"
                "• `завтра` - завтра в 23:59\n"
                "• `неделя` - через неделю\n"
                "• `нет` - без дедлайна"
            )
            return
        
        # Обновляем дедлайн в базе данных
        try:
            with self.db._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'UPDATE tasks SET deadline = ? WHERE id = ?', 
                    (new_deadline.isoformat() if new_deadline else None, task_id)
                )
                conn.commit()
            
            keyboard = [
                [InlineKeyboardButton("📋 Вернуться к заданию", callback_data=f"task_{task_id}")],
                [InlineKeyboardButton("📝 Список заданий", callback_data="list_tasks")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
            ]
            
            deadline_text = new_deadline.strftime('%d.%m.%Y в %H:%M МСК') if new_deadline else "не установлен"
            
            await update.message.reply_text(
                f"✅ **Дедлайн задания успешно изменен!**\n\n"
                f"⏰ **Новый дедлайн:** {deadline_text}",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
            # Очищаем данные
            context.user_data.clear()
            
        except Exception as e:
            logger.error(f"Ошибка при изменении дедлайна задания: {e}")
            await update.message.reply_text(
                f"❌ Ошибка при изменении дедлайна: {str(e)}"
            )

    async def handle_edit_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает сообщения во время редактирования заданий"""
        if not await self._check_admin_access(update):
            return
        
        # Проверяем, есть ли активное состояние редактирования
        editing_state = context.user_data.get('editing_state')
        
        if editing_state == EDITING_TASK_TITLE:
            await self.handle_edit_title(update, context)
        elif editing_state == EDITING_TASK_DESCRIPTION:
            await self.handle_edit_description(update, context)
        elif editing_state == EDITING_TASK_LINK:
            await self.handle_edit_link(update, context)
        elif editing_state == EDITING_TASK_OPEN_DATE:
            await self.handle_edit_open_date(update, context)
        elif editing_state == EDITING_TASK_DEADLINE:
            await self.handle_edit_deadline(update, context)
        # Если состояние не найдено, игнорируем сообщение

    async def cancel_conversation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отменяет текущий диалог"""
        if not await self._check_admin_access(update):
            return ConversationHandler.END
            
        # Очищаем данные
        context.user_data.clear()
        
        keyboard = [
            [InlineKeyboardButton("📋 Задания", callback_data="tasks_menu")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
        ]
        
        await update.message.reply_text(
            "❌ **Операция отменена**\n\n"
            "Выберите действие:",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ConversationHandler.END

# Расширяем класс Database методом для получения соединения
def add_connection_method():
    def _get_connection(self):
        import sqlite3
        return sqlite3.connect(self.db_path)
    
    Database._get_connection = _get_connection

# Применяем расширение
add_connection_method()

def main():
    """Основная функция запуска админ-бота"""
    # Проверяем токен
    token = os.getenv('ADMIN_BOT_TOKEN')
    if not token:
        logger.error("ADMIN_BOT_TOKEN не найден в переменных окружения!")
        logger.info("Создайте файл .env с ADMIN_BOT_TOKEN=your_admin_bot_token")
        return
    
    # Проверяем ID администраторов
    admin_ids_env = os.getenv('ADMIN_IDS', os.getenv('ADMIN_ID', ''))
    if not admin_ids_env:
        logger.error("ADMIN_IDS не найден в переменных окружения!")
        logger.info("Добавьте в .env файл: ADMIN_IDS=your_admin_telegram_id")
        return
    
    # Проверяем на режим открытого доступа
    if admin_ids_env.strip().lower() == 'all':
        logger.warning("⚠️ ⚠️ ⚠️  ВНИМАНИЕ: РЕЖИМ ОТКРЫТОГО ДОСТУПА! ⚠️ ⚠️ ⚠️")
        logger.warning("Админ-бот доступен ВСЕМ пользователям Telegram!")
        logger.warning("Это может быть небезопасно для продакшена!")
        logger.warning("Рекомендуется использовать только для тестирования!")
    else:
        # Проверяем корректность ID для обычного режима
        try:
            admin_ids = [int(aid.strip()) for aid in admin_ids_env.split(',') if aid.strip()]
            if not admin_ids:
                raise ValueError("Пустой список администраторов")
        except ValueError:
            logger.error("Некорректные ADMIN_IDS в переменных окружения!")
            logger.info("Формат: ADMIN_IDS=123456789,987654321 или ADMIN_IDS=all")
            return
    
    # Создаем приложение
    application = Application.builder().token(token).build()
    
    # Создаем экземпляр бота
    admin_bot = AdminBot()
    
    # ConversationHandler для добавления заданий
    add_task_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(admin_bot._start_add_task_conversation, pattern="^create_manual$")
        ],
        states={
            ADDING_TASK_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_bot.handle_add_task_title)],
            ADDING_TASK_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_bot.handle_add_task_description)],
            ADDING_TASK_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_bot.handle_add_task_link)],
            ADDING_TASK_OPEN_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_bot.handle_add_task_open_date)],
            ADDING_TASK_DEADLINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_bot.handle_add_task_deadline)],
        },
        fallbacks=[CommandHandler("cancel", admin_bot.cancel_conversation)],
        name="add_task",
        per_message=True
    )
    
    # Обработчик сообщений для редактирования заданий
    edit_message_handler = MessageHandler(
        filters.TEXT & ~filters.COMMAND, 
        admin_bot.handle_edit_message
    )
    
    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", admin_bot.start_command))
    application.add_handler(add_task_handler)
    application.add_handler(CallbackQueryHandler(admin_bot.handle_callback))
    application.add_handler(edit_message_handler)
    
    # Устанавливаем команды бота
    async def set_commands(app):
        commands = [
            BotCommand("start", "Запустить админ-панель")
        ]
        await app.bot.set_my_commands(commands)
    
    application.post_init = set_commands
    
    # Запускаем бота
    logger.info("🔧 Админ-бот запущен...")
    logger.info("📊 Система управления Эко-ботом готова к работе")
    logger.info("⏹️ Для остановки нажмите Ctrl+C")
    
    try:
        application.run_polling()
    except KeyboardInterrupt:
        logger.info("🛑 Админ-бот остановлен пользователем")
    except Exception as e:
        logger.error(f"❌ Ошибка при запуске админ-бота: {e}")

if __name__ == '__main__':
    main() 