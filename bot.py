import os
import logging
import json
import asyncio
from datetime import datetime, timedelta
from dotenv import load_dotenv
import pytz
from typing import Optional
from telegram import Update, Document, PhotoSize, Video, InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes, ConversationHandler, BaseHandler
)

from database import Database
from keyboards import Keyboards

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Константы для состояний ConversationHandler
IDLE = 0
REGISTRATION_FIRST_NAME, REGISTRATION_LAST_NAME, PARTICIPATION_TYPE = range(1, 4)
FAMILY_MEMBERS_COUNT, CHILDREN_INFO = range(4, 6)
SUPPORT_MESSAGE = 10
TASK_SUBMISSION = 20
# Новые состояния для изменения профиля
EDIT_FIRST_NAME, EDIT_LAST_NAME = range(30, 32)

class OfflineMessageHandler(BaseHandler):
    """Обработчик для сохранения офлайн сообщений"""
    
    def __init__(self, db: Database):
        super().__init__(self.callback)
        self.db = db
    
    def check_update(self, update: Update) -> bool:
        """Проверяем все типы сообщений для сохранения"""
        return bool(update.effective_user and (update.message or update.callback_query))
    
    async def callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Сохраняем сообщение как офлайн если бот был недоступен"""
        if not update.effective_user:
            return
        
        user_id = update.effective_user.id
        
        try:
            # Определяем тип сообщения
            message_type = 'unknown'
            message_data = {}
            
            if update.message:
                if update.message.text:
                    message_type = 'text'
                    message_data = {
                        'text': update.message.text,
                        'date': update.message.date.isoformat()
                    }
                elif update.message.photo:
                    message_type = 'photo'
                    message_data = {
                        'caption': update.message.caption,
                        'file_id': update.message.photo[-1].file_id,
                        'date': update.message.date.isoformat()
                    }
                elif update.message.video:
                    message_type = 'video'
                    message_data = {
                        'caption': update.message.caption,
                        'file_id': update.message.video.file_id,
                        'date': update.message.date.isoformat()
                    }
                elif update.message.document:
                    message_type = 'document'
                    message_data = {
                        'caption': update.message.caption,
                        'file_id': update.message.document.file_id,
                        'filename': update.message.document.file_name,
                        'date': update.message.date.isoformat()
                    }
                elif update.message.voice:
                    message_type = 'voice'
                    message_data = {
                        'file_id': update.message.voice.file_id,
                        'date': update.message.date.isoformat()
                    }
            
            elif update.callback_query:
                message_type = 'callback'
                message_data = {
                    'data': update.callback_query.data,
                    'date': datetime.now().isoformat()
                }
            
            # Сохраняем только если это не команда /start (чтобы избежать дублирования)
            if message_type != 'unknown' and not (message_type == 'text' and 
                                                  message_data.get('text', '').startswith('/start')):
                
                # Здесь мы НЕ сохраняем сообщение как офлайн, если бот работает
                # Это просто middleware для логирования всех сообщений
                logger.info(f"Получено сообщение от пользователя {user_id}: тип {message_type}")
                
        except Exception as e:
            logger.error(f"Ошибка в OfflineMessageHandler: {e}")

class EcoBot:
    def __init__(self):
        self.db = Database()
        self.keyboards = Keyboards()
        self.moscow_tz = pytz.timezone('Europe/Moscow')
        
        # Создаем папку для файлов
        self.files_dir = "uploaded_files"
        os.makedirs(self.files_dir, exist_ok=True)
        
        # Создаем подпапки по типам файлов
        os.makedirs(os.path.join(self.files_dir, "photos"), exist_ok=True)
        os.makedirs(os.path.join(self.files_dir, "videos"), exist_ok=True)
        os.makedirs(os.path.join(self.files_dir, "documents"), exist_ok=True)
        
        # Инициализация тестовых данных
        self._init_test_data()
    
    def _should_show_july_21_message(self):
        """Проверяет, нужно ли показывать сообщение о первом задании 21 июля"""
        moscow_tz = pytz.timezone('Europe/Moscow')
        now = datetime.now(moscow_tz)
        
        # Дата и время когда сообщение должно перестать показываться: 21 июля 2025 в 00:00 МСК
        cutoff_date = moscow_tz.localize(datetime(2025, 7, 21, 0, 0, 0))
        
        return now < cutoff_date
    
    def _init_test_data(self):
        """Добавляем тестовые задания в базу данных"""
        try:
            tasks = self.db.get_all_tasks()
            if not tasks:
                # Создаем задания для текущей недели
                current_week = datetime.now(self.moscow_tz).isocalendar()[1]
                self.db.create_weekly_tasks(current_week)
                logger.info("Тестовые задания добавлены в базу данных")
        except Exception as e:
            logger.error(f"Ошибка при инициализации тестовых данных: {e}")

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        user = update.effective_user
        user_id = user.id
        
        # Добавляем пользователя в базу данных
        self.db.add_user(
            user_id,
            user.username,
            user.first_name,
            user.last_name
        )
        
        # Проверяем офлайн сообщения
        await self._process_offline_messages(update, context)
        
        # Восстанавливаем состояние пользователя
        saved_state, saved_context = self.db.get_user_state(user_id)
        
        # Если есть сохраненное состояние и не завершена регистрация
        if saved_state != IDLE and not self.db.is_user_registered(user_id):
            # Восстанавливаем контекст
            for key, value in saved_context.items():
                context.user_data[key] = value
            
            await update.message.reply_text(
                "🔄 **Восстановление сессии**\n\n"
                "Я помню, где мы остановились! Давайте продолжим регистрацию с того места, где прервались.",
                parse_mode='Markdown'
            )
            
            return await self._continue_from_state(update, context, saved_state)
        
        # Проверяем, завершена ли регистрация
        if self.db.is_user_registered(user_id):
            user_data = self.db.get_user(user_id)
            
            # Очищаем состояние (возвращаем в главное меню)
            self.db.clear_user_state(user_id)
            
            welcome_text = (
                f"🌿 С возвращением, {user_data[5]}!\n\n"
                "Добро пожаловать обратно в Эко-бот Движения друзей заповедных островов.\n\n"
            )
            
            # Добавляем информацию о первом задании 21 июля (до указанной даты)
            if self._should_show_july_21_message():
                welcome_text += (
                    "🎯 **ВАЖНАЯ ИНФОРМАЦИЯ!**\n"
                    "📅 **Первое задание будет открыто 21 июля 2025 года**\n\n"
                    "Следите за обновлениями и будьте готовы к участию!\n\n"
                )
            
            welcome_text += "Используйте меню ниже для навигации:"
            
            await update.message.reply_text(
                welcome_text,
                reply_markup=self.keyboards.main_menu()
            )
            return ConversationHandler.END
        else:
            # Начинаем процесс регистрации
            self.db.save_user_state(user_id, REGISTRATION_LAST_NAME)
            
            welcome_text = (
                f"🌿 Добро пожаловать в Эко-бот Движения друзей заповедных островов!\n\n"
                "Этот бот поможет вам участвовать в экологических заданиях и следить за своими успехами.\n\n"
            )
            
            # Добавляем информацию о первом задании 21 июля (до указанной даты)
            if self._should_show_july_21_message():
                welcome_text += (
                    "🎯 **ВАЖНАЯ ИНФОРМАЦИЯ!**\n"
                    "📅 **Первое задание будет открыто 21 июля 2025 года**\n\n"
                    "Зарегистрируйтесь сейчас, чтобы быть готовыми к участию!\n\n"
                )
            
            welcome_text += (
                "Для начала давайте зарегистрируем вас в системе.\n\n"
                "📝 **Введите вашу фамилию:**"
            )
            
            await update.message.reply_text(welcome_text, parse_mode='Markdown')
            return REGISTRATION_LAST_NAME

    async def _continue_from_state(self, update: Update, context: ContextTypes.DEFAULT_TYPE, state: int):
        """Продолжает процесс с сохраненного состояния"""
        if state == REGISTRATION_LAST_NAME:
            await update.message.reply_text("📝 **Введите вашу фамилию:**", parse_mode='Markdown')
            return REGISTRATION_LAST_NAME
        
        elif state == REGISTRATION_FIRST_NAME:
            last_name = context.user_data.get('last_name', '')
            await update.message.reply_text(
                f"✅ Фамилия: {last_name}\n\n📝 **Теперь введите ваше имя:**",
                parse_mode='Markdown'
            )
            return REGISTRATION_FIRST_NAME
        
        elif state == PARTICIPATION_TYPE:
            first_name = context.user_data.get('first_name', '')
            last_name = context.user_data.get('last_name', '')
            text = (
                f"✅ Имя: {first_name}\n"
                f"✅ Фамилия: {last_name}\n\n"
                "🏠 **Уточните, как вы планируете участвовать:**"
            )
            await update.message.reply_text(
                text,
                parse_mode='Markdown',
                reply_markup=self.keyboards.participation_type()
            )
            return PARTICIPATION_TYPE
        
        elif state == FAMILY_MEMBERS_COUNT:
            await update.message.reply_text(
                "👨‍👩‍👧‍👦 **Семейное участие**\n\n"
                "📝 Введите количество человек, которые будут участвовать от вашей семьи:",
                parse_mode='Markdown',
                reply_markup=self.keyboards.back_to_menu()
            )
            return FAMILY_MEMBERS_COUNT
        
        elif state == CHILDREN_INFO:
            count = context.user_data.get('family_members_count', 1)
            await update.message.reply_text(
                f"✅ Количество участников: {count}\n\n"
                "👶 **Участвуют ли дети?**\n"
                "Если да, укажите их возраст. Если нет, напишите 'нет':"
            )
            return CHILDREN_INFO
        
        
        elif state == TASK_SUBMISSION:
            task_id = current_context.get('selected_task_id')
            if task_id:
                context.user_data['selected_task_id'] = task_id
                await update.message.reply_text(
                    "📤 **Отправка отчета**\n\n"
                    "Отправьте ваш отчет одним из способов:\n"
                    "• 🔗 Ссылка на пост в социальных сетях\n"
                    "• 📸 Фотография\n"
                    "• 🎥 Видео\n"
                    "• 📄 Документ\n\n"
                    "⏰ Напоминание: дедлайн - суббота 23:59 МСК",
                    parse_mode='Markdown'
                )
                return TASK_SUBMISSION
            else:
                # Если нет ID задания, сбрасываем состояние
                self.db.clear_user_state(update.effective_user.id)
                return ConversationHandler.END
        
        elif state == EDIT_FIRST_NAME:
            await update.message.reply_text(
                "✏️ **Изменение имени**\n\n"
                "Введите новое имя:",
                parse_mode='Markdown',
                reply_markup=self.keyboards.back_to_menu()
            )
            return EDIT_FIRST_NAME
        
        elif state == EDIT_LAST_NAME:
            await update.message.reply_text(
                "✏️ **Изменение фамилии**\n\n"
                "Введите новую фамилию:",
                parse_mode='Markdown',
                reply_markup=self.keyboards.back_to_menu()
            )
            return EDIT_LAST_NAME
        
        else:
            # Неизвестное состояние, сбрасываем
            self.db.clear_user_state(update.effective_user.id)
            return ConversationHandler.END

    async def _process_offline_messages(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает сообщения, отправленные в офлайн режиме"""
        user_id = update.effective_user.id
        offline_messages = self.db.get_offline_messages(user_id)
        
        if offline_messages:
            # Убираем сообщение пользователю - только логируем
            logger.info(f"Обрабатываю {len(offline_messages)} офлайн сообщений для пользователя {user_id}")
            
            processed_count = 0
            for msg_id, message_data, message_type, received_date in offline_messages:
                try:
                    # Здесь можно добавить логику обработки разных типов сообщений
                    logger.info(f"Обработка офлайн сообщения {msg_id} от пользователя {user_id}")
                    
                    # Для демонстрации просто логируем содержимое
                    try:
                        data = json.loads(message_data)
                        if message_type == 'text':
                            logger.info(f"Офлайн текст: {data.get('text', '')}")
                        elif message_type in ['photo', 'video', 'document']:
                            logger.info(f"Офлайн {message_type}: {data.get('caption', 'без подписи')}")
                    except json.JSONDecodeError:
                        logger.info(f"Офлайн сообщение: {message_data}")
                    
                    # Помечаем сообщение как обработанное
                    self.db.mark_offline_message_processed(msg_id)
                    processed_count += 1
                    
                except Exception as e:
                    logger.error(f"Ошибка обработки офлайн сообщения {msg_id}: {e}")
            
            # Убираем сообщение пользователю - только логируем результат
            if processed_count > 0:
                logger.info(f"Успешно обработано {processed_count} офлайн сообщений для пользователя {user_id}")

    async def registration_last_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка ввода фамилии"""
        user_id = update.effective_user.id
        last_name = update.message.text.strip()
        
        # Сохраняем каждую попытку ввода
        try:
            input_data = json.dumps({
                'step': 'last_name',
                'input': last_name,
                'valid': len(last_name) >= 2,
                'date': update.message.date.isoformat()
            }, ensure_ascii=False)
            
            self.db.save_offline_message(user_id, input_data, 'registration_input')
        except Exception as e:
            logger.error(f"Не удалось сохранить ввод фамилии: {e}")
        
        if not last_name or len(last_name) < 2:
            # Сохраняем состояние с некорректным вводом
            self.db.save_user_state(user_id, REGISTRATION_LAST_NAME, {
                'invalid_attempts': context.user_data.get('invalid_attempts', 0) + 1,
                'last_invalid_input': last_name,
                'timestamp': update.message.date.isoformat()
            })
            
            await update.message.reply_text(
                "❌ Пожалуйста, введите корректную фамилию (минимум 2 символа):\n\n"
                "💾 Ваш ввод сохранен."
            )
            return REGISTRATION_LAST_NAME
        
        context.user_data['last_name'] = last_name
        
        # Сохраняем состояние с корректными данными
        self.db.save_user_state(
            user_id, 
            REGISTRATION_FIRST_NAME, 
            {
                **context.user_data,
                'last_name_confirmed': True,
                'timestamp': update.message.date.isoformat()
            }
        )
        
        await update.message.reply_text(
            f"✅ Фамилия: {last_name}\n\n📝 **Теперь введите ваше имя:**\n\n💾 Данные сохранены",
            parse_mode='Markdown'
        )
        return REGISTRATION_FIRST_NAME

    async def registration_first_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка ввода имени"""
        user_id = update.effective_user.id
        first_name = update.message.text.strip()
        
        # Сохраняем каждую попытку ввода
        try:
            input_data = json.dumps({
                'step': 'first_name',
                'input': first_name,
                'valid': len(first_name) >= 2,
                'current_data': context.user_data,
                'date': update.message.date.isoformat()
            }, ensure_ascii=False)
            
            self.db.save_offline_message(user_id, input_data, 'registration_input')
        except Exception as e:
            logger.error(f"Не удалось сохранить ввод имени: {e}")
        
        if not first_name or len(first_name) < 2:
            # Сохраняем состояние с некорректным вводом
            self.db.save_user_state(user_id, REGISTRATION_FIRST_NAME, {
                **context.user_data,
                'invalid_attempts': context.user_data.get('invalid_attempts', 0) + 1,
                'last_invalid_input': first_name,
                'timestamp': update.message.date.isoformat()
            })
            
            await update.message.reply_text(
                "❌ Пожалуйста, введите корректное имя (минимум 2 символа):\n\n"
                "💾 Ваш ввод сохранен."
            )
            return REGISTRATION_FIRST_NAME
        
        context.user_data['first_name'] = first_name
        
        # Сохраняем состояние с корректными данными
        self.db.save_user_state(
            user_id, 
            PARTICIPATION_TYPE, 
            {
                **context.user_data,
                'first_name_confirmed': True,
                'timestamp': update.message.date.isoformat()
            }
        )
        
        text = (
            f"✅ Имя: {first_name}\n"
            f"✅ Фамилия: {context.user_data['last_name']}\n\n"
            "🏠 **Уточните, как вы планируете участвовать:**\n\n"
            "💾 Данные сохранены"
        )
        
        await update.message.reply_text(
            text,
            parse_mode='Markdown',
            reply_markup=self.keyboards.participation_type()
        )
        return PARTICIPATION_TYPE

    async def participation_type(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка выбора типа участия"""
        user_id = update.effective_user.id
        text = update.message.text
        
        # Сохраняем выбор
        try:
            choice_data = json.dumps({
                'step': 'participation_type',
                'choice': text,
                'current_data': context.user_data,
                'date': update.message.date.isoformat()
            }, ensure_ascii=False)
            
            self.db.save_offline_message(user_id, choice_data, 'registration_choice')
        except Exception as e:
            logger.error(f"Не удалось сохранить выбор типа участия: {e}")
        
        if text == "👤 Индивидуально":
            context.user_data['participation_type'] = 'individual'
            
            # Сохраняем финальное состояние перед завершением
            self.db.save_user_state(user_id, IDLE, {
                **context.user_data,
                'participation_confirmed': True,
                'ready_for_completion': True,
                'timestamp': update.message.date.isoformat()
            })
            
            await self._complete_registration(update, context)
            return ConversationHandler.END
            
        elif text == "👨‍👩‍👧‍👦 Семьей":
            context.user_data['participation_type'] = 'family'
            
            # Сохраняем состояние для семейного участия
            self.db.save_user_state(
                user_id, 
                FAMILY_MEMBERS_COUNT, 
                {
                    **context.user_data,
                    'participation_confirmed': True,
                    'timestamp': update.message.date.isoformat()
                }
            )
            
            await update.message.reply_text(
                "👨‍👩‍👧‍👦 **Семейное участие**\n\n"
                "📝 Введите количество человек, которые будут участвовать от вашей семьи:\n\n"
                "💾 Данные сохранены",
                parse_mode='Markdown',
                reply_markup=self.keyboards.back_to_menu()
            )
            return FAMILY_MEMBERS_COUNT
        else:
            # Сохраняем некорректный выбор
            self.db.save_user_state(user_id, PARTICIPATION_TYPE, {
                **context.user_data,
                'invalid_choice': text,
                'invalid_attempts': context.user_data.get('invalid_attempts', 0) + 1,
                'timestamp': update.message.date.isoformat()
            })
            
            await update.message.reply_text(
                "❌ Пожалуйста, выберите один из предложенных вариантов:\n\n"
                "💾 Ваш выбор сохранен.",
                reply_markup=self.keyboards.participation_type()
            )
            return PARTICIPATION_TYPE

    async def family_members_count(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка количества участников семьи"""
        user_id = update.effective_user.id
        count_input = update.message.text.strip()
        
        # Сохраняем ввод
        try:
            input_data = json.dumps({
                'step': 'family_members_count',
                'input': count_input,
                'current_data': context.user_data,
                'date': update.message.date.isoformat()
            }, ensure_ascii=False)
            
            self.db.save_offline_message(user_id, input_data, 'registration_input')
        except Exception as e:
            logger.error(f"Не удалось сохранить ввод количества участников: {e}")
        
        try:
            count = int(count_input)
            if count < 1 or count > 10:
                raise ValueError()
        except ValueError:
            # Сохраняем состояние с некорректным вводом
            self.db.save_user_state(user_id, FAMILY_MEMBERS_COUNT, {
                **context.user_data,
                'invalid_count_input': count_input,
                'invalid_attempts': context.user_data.get('invalid_attempts', 0) + 1,
                'timestamp': update.message.date.isoformat()
            })
            
            await update.message.reply_text(
                "❌ Пожалуйста, введите корректное число от 1 до 10:\n\n"
                "💾 Ваш ввод сохранен."
            )
            return FAMILY_MEMBERS_COUNT
        
        context.user_data['family_members_count'] = count
        
        # Сохраняем состояние с корректными данными
        self.db.save_user_state(
            user_id, 
            CHILDREN_INFO, 
            {
                **context.user_data,
                'family_count_confirmed': True,
                'timestamp': update.message.date.isoformat()
            }
        )
        
        await update.message.reply_text(
            f"✅ Количество участников: {count}\n\n"
            "👶 **Участвуют ли дети?**\n"
            "Если да, укажите их возраст. Если нет, напишите 'нет':\n\n"
            "💾 Данные сохранены"
        )
        return CHILDREN_INFO

    async def children_info(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка информации о детях"""
        user_id = update.effective_user.id
        children_info = update.message.text.strip()
        
        # Сохраняем ввод
        try:
            input_data = json.dumps({
                'step': 'children_info',
                'input': children_info,
                'current_data': context.user_data,
                'date': update.message.date.isoformat()
            }, ensure_ascii=False)
            
            self.db.save_offline_message(user_id, input_data, 'registration_input')
        except Exception as e:
            logger.error(f"Не удалось сохранить информацию о детях: {e}")
        
        context.user_data['children_info'] = children_info if children_info.lower() != 'нет' else None
        
        # Сохраняем финальное состояние перед завершением
        self.db.save_user_state(user_id, IDLE, {
            **context.user_data,
            'children_info_confirmed': True,
            'ready_for_completion': True,
            'timestamp': update.message.date.isoformat()
        })
        
        await self._complete_registration(update, context)
        return ConversationHandler.END

    async def _complete_registration(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Завершение регистрации"""
        user_id = update.effective_user.id
        
        # Сохраняем данные в базу
        self.db.update_user_registration(
            user_id,
            context.user_data['first_name'],
            context.user_data['last_name'],
            context.user_data['participation_type'],
            context.user_data.get('family_members_count', 1),
            context.user_data.get('children_info')
        )
        
        # Очищаем состояние - регистрация завершена
        self.db.clear_user_state(user_id)
        
        # Формируем поздравительное сообщение
        if context.user_data['participation_type'] == 'individual':
            participation_text = "индивидуально"
        else:
            count = context.user_data.get('family_members_count', 1)
            children = context.user_data.get('children_info')
            participation_text = f"семьей ({count} чел.)"
            if children:
                participation_text += f", с детьми: {children}"
        
        congratulations_text = (
            f"🎉 **Поздравляем с завершением регистрации!**\n\n"
            f"👤 Участник: {context.user_data['first_name']} {context.user_data['last_name']}\n"
            f"🏠 Тип участия: {participation_text}\n\n"
        )
        
        # Добавляем информацию о первом задании 21 июля (до указанной даты)
        if self._should_show_july_21_message():
            congratulations_text += (
                "🎯 **ВАЖНАЯ ИНФОРМАЦИЯ!**\n"
                "📅 **Первое задание будет открыто 21 июля 2025 года**\n\n"
                "Вы зарегистрированы и готовы к участию!\n\n"
            )
        
        congratulations_text += (
            "📝 **Важные моменты:**\n"
            "• Бот будет принимать задания только от вас как зарегистрированного участника\n"
            "• В случае семейного участия отчеты отправляет только зарегистрированный участник\n"
            "• Задания публикуются по понедельникам и четвергам в 11:00 МСК\n"
            "• Дедлайн выполнения - суббота 23:59 МСК\n\n"
            "Теперь вы можете использовать все функции бота! 🌿"
        )
        
        await update.message.reply_text(
            congratulations_text,
            parse_mode='Markdown',
            reply_markup=self.keyboards.main_menu()
        )
        
        # Очищаем данные пользователя
        context.user_data.clear()

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик текстовых сообщений"""
        user_id = update.effective_user.id
        
        # Проверяем регистрацию
        if not self.db.is_user_registered(user_id):
            # Сохраняем сообщение как офлайн если пользователь не зарегистрирован
            try:
                message_data = json.dumps({
                    'text': update.message.text,
                    'date': update.message.date.isoformat(),
                    'context': 'unregistered_user'
                }, ensure_ascii=False)
                
                self.db.save_offline_message(user_id, message_data, 'text_unregistered')
                logger.info(f"Сообщение от незарегистрированного пользователя {user_id} сохранено")
            except Exception as e:
                logger.error(f"Не удалось сохранить сообщение незарегистрированного пользователя: {e}")
            
            await update.message.reply_text(
                "❌ Сначала необходимо завершить регистрацию. Отправьте команду /start\n\n"
                "💾 Ваше сообщение сохранено и будет обработано после регистрации.",
                reply_markup=self.keyboards.main_menu()
            )
            return
        
        # Сохраняем каждое сообщение зарегистрированного пользователя
        try:
            message_data = json.dumps({
                'text': update.message.text,
                'date': update.message.date.isoformat(),
                'context': 'main_menu'
            }, ensure_ascii=False)
            
            # Временно сохраняем, потом удалим если обработка прошла успешно
            temp_msg_id = None
            self.db.save_offline_message(user_id, message_data, 'text_processing')
            
            # Получаем ID последнего сохраненного сообщения
            temp_messages = self.db.get_offline_messages(user_id)
            if temp_messages:
                temp_msg_id = temp_messages[-1][0]
            
        except Exception as e:
            logger.error(f"Не удалось временно сохранить сообщение: {e}")
            temp_msg_id = None
        
        # Проверяем состояние пользователя ДО обработки команд
        saved_state, saved_context = self.db.get_user_state(user_id)
        
        # Если пользователь находится в состоянии редактирования профиля
        if saved_state == EDIT_FIRST_NAME:
            # Восстанавливаем контекст
            for key, value in saved_context.items():
                context.user_data[key] = value
            
            return await self.handle_edit_first_name(update, context)
        
        elif saved_state == EDIT_LAST_NAME:
            # Восстанавливаем контекст
            for key, value in saved_context.items():
                context.user_data[key] = value
            
            return await self.handle_edit_last_name(update, context)
        
        elif saved_state == TASK_SUBMISSION:
            # Восстанавливаем контекст
            for key, value in saved_context.items():
                context.user_data[key] = value
            
            return await self.handle_task_submission_content(update, context)
        
        # Очищаем состояние пользователя только если это команды главного меню
        text = update.message.text
        
        try:
            if text == "📋 Положение об игре":
                self.db.clear_user_state(user_id)  # Очищаем состояние
                await self._send_game_rules(update)
            
            elif text == "📖 Инструкция по прохождению":
                self.db.clear_user_state(user_id)  # Очищаем состояние
                await self._send_instructions(update)
            
            elif text == "📤 Отправить задание на проверку":
                self.db.clear_user_state(user_id)  # Очищаем состояние
                await self._send_task_submission(update, context)
            
            elif text == "🏦 Банк заданий":
                self.db.clear_user_state(user_id)  # Очищаем состояние
                await self._send_tasks_bank(update)
            
            elif text == "📊 Мой результат":
                self.db.clear_user_state(user_id)  # Очищаем состояние
                await self._send_user_results(update, user_id)
            
            elif text == "👤 Изменить профиль":
                self.db.clear_user_state(user_id)  # Очищаем состояние
                await self._show_profile_edit(update)
            
            elif text == "🌿 О Движении друзей заповедных островов":
                self.db.clear_user_state(user_id)  # Очищаем состояние
                await self._send_about_movement(update)
            
            elif text == "🏠 Главное меню":
                self.db.clear_user_state(user_id)  # Очищаем состояние
                await self._send_main_menu(update)
            
            elif text == "✏️ Изменить имя":
                # НЕ очищаем состояние - это начало процесса изменения
                await self._start_edit_first_name(update, context)
            
            elif text == "✏️ Изменить фамилию":
                # НЕ очищаем состояние - это начало процесса изменения
                await self._start_edit_last_name(update, context)
            
            elif text == "🆘 Обращение в поддержку":
                self.db.clear_user_state(user_id)  # Очищаем состояние
                await self._start_support_request(update, context)
            
            else:
                # Неизвестная команда - сохраняем как офлайн для анализа
                unknown_data = json.dumps({
                    'text': text,
                    'date': update.message.date.isoformat(),
                    'context': 'unknown_command'
                }, ensure_ascii=False)
                
                self.db.save_offline_message(user_id, unknown_data, 'text_unknown')
                
                # Проверяем, не похоже ли это на попытку отправить задание
                if len(text) > 10:  # Если сообщение длинное, возможно это отчет
                    # Сохраняем как потенциальный отчет для ручной обработки
                    potential_report_data = json.dumps({
                        'user_id': user_id,
                        'content': text,
                        'type': 'text',
                        'date': update.message.date.isoformat(),
                        'context': 'potential_report_out_of_context'
                    }, ensure_ascii=False)
                    
                    self.db.save_offline_message(user_id, potential_report_data, 'potential_report')
                    logger.info(f"Потенциальный отчет от пользователя {user_id} сохранен для ручной обработки")
                    
                    warning_text = (
                        "⚠️ **ВНИМАНИЕ! Ваше задание НЕ ПРИНЯТО!**\n\n"
                        "Похоже, вы пытаетесь отправить отчет по заданию, но это сообщение "
                        "отправлено вне контекста и **НЕ БУДЕТ ЗАСЧИТАНО**.\n\n"
                        "🔹 **Для правильной отправки заданий:**\n"
                        "1️⃣ Изучите инструкцию по прохождению\n"
                        "2️⃣ Используйте кнопку 'Отправить задание на проверку'\n"
                        "3️⃣ Выберите конкретное задание из списка\n"
                        "4️⃣ Только тогда отправляйте свой отчет\n\n"
                        "💾 Ваше сообщение сохранено для анализа администратором.\n\n"
                        "**Что делать сейчас?**"
                    )
                    keyboard = self.keyboards.out_of_context_actions()
                else:
                    warning_text = (
                        "❓ **Неизвестная команда**\n\n"
                        "Используйте кнопки меню для навигации по боту.\n\n"
                        "💾 Ваше сообщение сохранено для анализа.\n\n"
                        "**Доступные действия:**"
                    )
                    keyboard = self.keyboards.out_of_context_actions()
                
                await update.message.reply_text(
                    warning_text,
                    parse_mode='Markdown',
                    reply_markup=keyboard
                )
            
            # Если обработка прошла успешно, удаляем временное сообщение
            if temp_msg_id:
                self.db.mark_offline_message_processed(temp_msg_id)
                
        except Exception as e:
            logger.error(f"Ошибка при обработке сообщения: {e}")
            # Не удаляем временное сообщение при ошибке
            # Но всё равно показываем меню
            await update.message.reply_text(
                "⚠️ Произошла ошибка при обработке сообщения.\n\n"
                "💾 Сообщение сохранено. Попробуйте ещё раз или отправьте /start",
                reply_markup=self.keyboards.main_menu()
            )

    async def _send_game_rules(self, update: Update):
        """Отправляет положение об игре (PDF файл)"""
        text = (
            "📋 **Положение об игре**\n\n"
            "К сожалению, PDF файл с положением пока не загружен. "
            "Обратитесь в поддержку для получения актуального документа.\n\n"
            "**Основные правила:**\n"
            "• Задания публикуются дважды в неделю: понедельник и четверг в 11:00 МСК\n"
            "• Дедлайн выполнения: суббота 23:59 МСК\n"
            "• Отчеты принимаются в виде ссылок на посты, фото или видео\n"
            "• Опоздавшие отчеты не засчитываются\n"
            "• Соблюдайте экологические принципы\n"
            "• В семейном участии отчеты отправляет только зарегистрированный участник"
        )
        await update.message.reply_text(
            text, 
            parse_mode='Markdown',
            reply_markup=self.keyboards.main_menu()  # Обновляем меню
        )

    async def _send_instructions(self, update: Update):
        """Отправляет инструкцию по прохождению"""
        current_time = datetime.now(self.moscow_tz)
        weekday = current_time.weekday()  # 0 = понедельник
        
        # Определяем следующую дату публикации
        if weekday < 1:  # До понедельника
            next_publication = "понедельник в 11:00 МСК"
        elif weekday < 3:  # Между понедельником и четвергом
            next_publication = "четверг в 11:00 МСК"
        elif weekday < 5:  # Между четвергом и субботой
            next_publication = "следующий понедельник в 11:00 МСК"
        else:  # Выходные
            next_publication = "понедельник в 11:00 МСК"
        
        text = (
            "📖 **Инструкция по прохождению**\n\n"
            "**Расписание заданий:**\n"
            "🕐 Публикация: понедельник и четверг в 11:00 МСК\n"
            "⏰ Дедлайн: суббота в 23:59 МСК\n"
            f"📅 Следующая публикация: {next_publication}\n\n"
            "**Как участвовать:**\n"
            "1️⃣ Дождитесь публикации заданий\n"
            "2️⃣ Изучите задание в разделе 'Банк заданий'\n"
            "3️⃣ Выполните задание согласно инструкциям\n"
            "4️⃣ Подготовьте отчет:\n"
            "   • Ссылка на пост в соцсетях\n"
            "   • Фотографии\n"
            "   • Видео\n"
            "5️⃣ Отправьте отчет до субботы 23:59 МСК\n"
            "6️⃣ Получите обратную связь\n\n"
            "⚠️ **Важно:** Опоздавшие отчеты не засчитываются, но мы всё равно вас поддержим!"
        )
        await update.message.reply_text(
            text, 
            parse_mode='Markdown',
            reply_markup=self.keyboards.main_menu()  # Обновляем меню
        )

    async def _send_task_submission(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает доступные для отправки задания (исключая уже отправленные)"""
        user_id = update.effective_user.id
        open_tasks = self.db.get_open_tasks()
        
        # Получаем ID заданий, на которые пользователь уже отправил отчеты
        submitted_task_ids = set()
        try:
            user_submissions = self.db.get_user_submissions(user_id)
            for submission in user_submissions:
                # Получаем ID задания из базы по названию
                for task in open_tasks:
                    if task[1] == submission[0]:  # Сравниваем название
                        submitted_task_ids.add(task[0])
                        break
        except Exception as e:
            logger.error(f"Ошибка при получении отправленных заданий: {e}")
        
        # Фильтруем задания, исключая уже отправленные
        available_tasks = [task for task in open_tasks if task[0] not in submitted_task_ids]
        
        if not available_tasks:
            text = (
                "📤 **Отправка отчетов**\n\n"
                f"🟢 Всего открытых заданий: {len(open_tasks)}\n"
                f"✅ Вы уже отправили отчеты по всем доступным заданиям!\n\n"
            )
            
            if len(open_tasks) == 0:
                text += (
                    "🚫 На данный момент нет доступных заданий для отправки.\n"
                    "Задания публикуются по понедельникам и четвергам в 11:00 МСК."
                )
            else:
                text += (
                    "🎉 Отличная работа! Проверьте раздел 'Мой результат' для отслеживания статуса проверки.\n\n"
                    "Новые задания публикуются по понедельникам и четвергам в 11:00 МСК."
                )
            
            await update.message.reply_text(
                text,
                parse_mode='Markdown',
                reply_markup=self.keyboards.main_menu()
            )
            return
        
        text = (
            "📤 **Отправка отчетов**\n\n"
            f"🟢 Всего открытых заданий: {len(open_tasks)}\n"
            f"📝 Доступно для отправки: {len(available_tasks)}\n"
            f"✅ Уже отправлено: {len(submitted_task_ids)}\n\n"
            "**Выберите задание для отправки отчета:**"
        )
        
        # Создаем клавиатуру с кнопками по одной в ряд
        keyboard = []
        
        for task_data in available_tasks:
            task_id, title, description, _ = task_data[:4]
            # Сокращаем название если слишком длинное  
            short_title = title[:40] + "..." if len(title) > 40 else title
            keyboard.append([InlineKeyboardButton(
                f"📝 {short_title}", 
                callback_data=f"submit_task_{task_id}"
            )])
        
        # Кнопка возврата
        keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")])
        
        await update.message.reply_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _send_tasks_bank(self, update: Update):
        """Показывает банк заданий - только открытые задания"""
        all_tasks = self.db.get_all_tasks()
        open_tasks = [task for task in all_tasks if task[4]]  # is_open = True
        
        current_week_tasks = self.db.get_current_week_tasks()
        
        if not open_tasks:
            text = (
                "🏦 **Банк заданий**\n\n"
                f"📅 Задания этой недели: {len(current_week_tasks)}\n"
                f"🟢 Открытых заданий: 0\n\n"
                "🚫 На данный момент нет открытых заданий.\n"
                "Задания публикуются по понедельникам и четвергам в 11:00 МСК."
            )
            
            keyboard = [[InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]]
            
            await update.message.reply_text(
                text,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        
        text = (
            "🏦 **Банк заданий**\n\n"
            f"📅 Задания этой недели: {len(current_week_tasks)}\n"
            f"🟢 Открытых заданий: {len(open_tasks)}\n\n"
            "**🟢 Открытые задания:**\n"
            "Нажмите на задание, чтобы перейти к его описанию:"
        )
        
        # Создаем клавиатуру с кнопками по одной в ряд
        keyboard = []
        
        # Добавляем кнопки открытых заданий по одной в ряд
        for task_data in open_tasks:
            task_id, title, description, link = task_data[:4]
            if link:
                # Сокращаем название если слишком длинное
                short_title = title[:40] + "..." if len(title) > 40 else title
                keyboard.append([InlineKeyboardButton(
                    f"🟢 {short_title}", 
                    url=link
                )])
        
        # Кнопка возврата в главное меню
        keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")])
        
        await update.message.reply_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _send_user_results(self, update: Update, user_id: int):
        """Отправляет результаты пользователя"""
        completed, total_open = self.db.get_user_stats(user_id)
        submissions = self.db.get_user_submissions(user_id)
        
        text = f"📊 **Мой результат**\n\n"
        text += f"✅ Выполнено заданий: {completed} из {total_open}\n\n"
        
        if submissions:
            text += "**История отправок:**\n\n"
            for title, submission_date, status, is_on_time in submissions:
                # Форматируем дату
                date_obj = datetime.fromisoformat(submission_date.replace('Z', '+00:00'))
                formatted_date = date_obj.strftime("%d.%m.%Y в %H:%M мск")
                
                if is_on_time:
                    time_status = "✅ В срок"
                else:
                    time_status = "⏰ С опозданием"
                
                status_emoji = {
                    'pending': '⏳',
                    'approved': '✅',
                    'rejected': '❌'
                }.get(status, '⏳')
                
                text += f"{status_emoji} **{title}**\n"
                text += f"   📅 {formatted_date}\n"
                text += f"   {time_status}\n\n"
        else:
            text += "📝 Вы еще не отправляли заданий на проверку."
        
        await update.message.reply_text(
            text, 
            parse_mode='Markdown',
            reply_markup=self.keyboards.main_menu()  # Обновляем меню
        )

    async def _send_about_movement(self, update: Update):
        """Информация о Движении"""
        text = (
            "🌿 **О Движении друзей заповедных островов**\n\n"
            "Движение друзей заповедных островов — это сообщество людей, "
            "объединенных общей целью сохранения природы и экологического просвещения.\n\n"
            "**Наши цели:**\n"
            "• Сохранение биоразнообразия\n"
            "• Экологическое образование\n"
            "• Развитие экотуризма\n"
            "• Научные исследования\n\n"
            "🌐 Узнать больше: https://dzo.wildnet.ru"
        )
        
        await update.message.reply_text(
            text,
            parse_mode='Markdown',
            disable_web_page_preview=False,
            reply_markup=self.keyboards.main_menu()  # Обновляем меню
        )

    async def _start_support_request(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отправляет ссылку на поддержку"""
        text = (
            "🆘 **Обращение в поддержку**\n\n"
            "Для получения помощи обратитесь к администратору:\n"
            "👨‍💻 @Danlocked\n\n"
            "Администратор поможет вам с:\n"
            "• Техническими вопросами\n"
            "• Проблемами с заданиями\n"
            "• Регистрацией и участием\n"
            "• Любыми другими вопросами"
        )
        
        await update.message.reply_text(
            text,
            parse_mode='Markdown',
            reply_markup=self.keyboards.main_menu()
        )

    async def _send_main_menu(self, update: Update):
        """Отправляет главное меню"""
        # Очищаем состояние при возврате в главное меню
        self.db.clear_user_state(update.effective_user.id)
        
        text = "🏠 **Главное меню**\n\nВыберите нужный раздел:"
        await update.message.reply_text(
            text,
            parse_mode='Markdown',
            reply_markup=self.keyboards.main_menu()  # Обновляем меню
        )

    async def _show_profile_edit(self, update: Update):
        """Показывает текущий профиль и опции редактирования"""
        user_id = update.effective_user.id
        user_data = self.db.get_user(user_id)
        
        if not user_data:
            await update.message.reply_text(
                "❌ Ошибка: данные пользователя не найдены.",
                reply_markup=self.keyboards.main_menu()
            )
            return
        
        # Извлекаем данные пользователя
        _, _, _, _, first_name, last_name, participation_type, family_members_count, children_info, registration_completed, _ = user_data
        
        # Формируем информацию о типе участия
        if participation_type == 'individual':
            participation_text = "👤 Индивидуально"
        else:
            participation_text = f"👨‍👩‍👧‍👦 Семьей ({family_members_count} чел.)"
            if children_info:
                participation_text += f", дети: {children_info}"
        
        text = (
            f"👤 **Профиль пользователя**\n\n"
            f"**Имя:** {first_name}\n"
            f"**Фамилия:** {last_name}\n"
            f"**Тип участия:** {participation_text}\n\n"
            "Выберите, что хотите изменить:"
        )
        
        await update.message.reply_text(
            text,
            parse_mode='Markdown',
            reply_markup=self.keyboards.profile_edit()
        )

    async def _start_edit_first_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Начинает процесс изменения имени"""
        user_id = update.effective_user.id
        
        # Сохраняем состояние
        self.db.save_user_state(user_id, EDIT_FIRST_NAME)
        
        await update.message.reply_text(
            "✏️ **Изменение имени**\n\n"
            "Введите новое имя:",
            parse_mode='Markdown',
            reply_markup=self.keyboards.back_to_menu()
        )
        
        return EDIT_FIRST_NAME

    async def _start_edit_last_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Начинает процесс изменения фамилии"""
        user_id = update.effective_user.id
        
        # Сохраняем состояние
        self.db.save_user_state(user_id, EDIT_LAST_NAME)
        
        await update.message.reply_text(
            "✏️ **Изменение фамилии**\n\n"
            "Введите новую фамилию:",
            parse_mode='Markdown',
            reply_markup=self.keyboards.back_to_menu()
        )
        
        return EDIT_LAST_NAME

    async def handle_edit_first_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает изменение имени"""
        user_id = update.effective_user.id
        new_first_name = update.message.text.strip()
        
        if update.message.text == "🏠 Главное меню":
            self.db.clear_user_state(user_id)
            await self._send_main_menu(update)
            return ConversationHandler.END
        
        # Валидация
        if not new_first_name or len(new_first_name) < 2:
            await update.message.reply_text(
                "❌ Пожалуйста, введите корректное имя (минимум 2 символа):",
                reply_markup=self.keyboards.back_to_menu()
            )
            return EDIT_FIRST_NAME
        
        # Обновляем имя в базе данных
        try:
            # Получаем текущие данные
            user_data = self.db.get_user(user_id)
            if user_data:
                # Обновляем только имя
                self.db.update_user_name(user_id, new_first_name, user_data[5])  # 5 - last_name
                
                # Очищаем состояние
                self.db.clear_user_state(user_id)
                
                await update.message.reply_text(
                    f"✅ **Имя успешно изменено!**\n\n"
                    f"Новое имя: **{new_first_name}**",
                    parse_mode='Markdown',
                    reply_markup=self.keyboards.main_menu()
                )
                
                return ConversationHandler.END
            else:
                raise Exception("Пользователь не найден")
                
        except Exception as e:
            logger.error(f"Ошибка при изменении имени: {e}")
            await update.message.reply_text(
                "❌ Произошла ошибка при сохранении. Попробуйте еще раз.",
                reply_markup=self.keyboards.main_menu()
            )
            return ConversationHandler.END

    async def handle_edit_last_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает изменение фамилии"""
        user_id = update.effective_user.id
        new_last_name = update.message.text.strip()
        
        if update.message.text == "🏠 Главное меню":
            self.db.clear_user_state(user_id)
            await self._send_main_menu(update)
            return ConversationHandler.END
        
        # Валидация
        if not new_last_name or len(new_last_name) < 2:
            await update.message.reply_text(
                "❌ Пожалуйста, введите корректную фамилию (минимум 2 символа):",
                reply_markup=self.keyboards.back_to_menu()
            )
            return EDIT_LAST_NAME
        
        # Обновляем фамилию в базе данных
        try:
            # Получаем текущие данные
            user_data = self.db.get_user(user_id)
            if user_data:
                # Обновляем только фамилию
                self.db.update_user_name(user_id, user_data[4], new_last_name)  # 4 - first_name
                
                # Очищаем состояние
                self.db.clear_user_state(user_id)
                
                await update.message.reply_text(
                    f"✅ **Фамилия успешно изменена!**\n\n"
                    f"Новая фамилия: **{new_last_name}**",
                    parse_mode='Markdown',
                    reply_markup=self.keyboards.main_menu()
                )
                
                return ConversationHandler.END
            else:
                raise Exception("Пользователь не найден")
                
        except Exception as e:
            logger.error(f"Ошибка при изменении фамилии: {e}")
            await update.message.reply_text(
                "❌ Произошла ошибка при сохранении. Попробуйте еще раз.",
                reply_markup=self.keyboards.main_menu()
            )
            return ConversationHandler.END

    async def handle_task_submission_content(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает содержимое отчета по заданию"""
        user_id = update.effective_user.id
        
        # Сохраняем состояние перед обработкой
        current_state, current_context = self.db.get_user_state(user_id)
        
        if 'selected_task_id' not in context.user_data:
            # Восстанавливаем из состояния если потерялось
            if 'selected_task_id' in current_context:
                context.user_data['selected_task_id'] = current_context['selected_task_id']
                logger.info(f"Восстановлен task_id из сохраненного состояния: {current_context['selected_task_id']}")
            else:
                await update.message.reply_text(
                    "❌ Сначала выберите задание для отправки отчета.\n\n"
                    "💾 Ваш отчет сохранен и будет обработан при повторном выборе задания.",
                    reply_markup=self.keyboards.main_menu()
                )
                return ConversationHandler.END
        
        task_id = context.user_data['selected_task_id']
        
        # Обновляем состояние с актуальными данными
        self.db.save_user_state(user_id, TASK_SUBMISSION, {
            'selected_task_id': task_id,
            'submission_attempt': datetime.now().isoformat()
        })
        
        # Определяем тип отчета и содержимое
        file_path = None
        
        if update.message.text:
            submission_type = 'text'
            content = update.message.text
            file_id = None
        elif update.message.photo:
            submission_type = 'photo'
            content = update.message.caption or "Фото-отчет"
            
            # Скачиваем и сохраняем фото локально
            photo = update.message.photo[-1]  # Берем наибольшее разрешение
            file_path = await self._download_and_save_file(photo, "photo", user_id, context, task_id)
            file_id = photo.file_id  # Оставляем file_id как fallback
            
        elif update.message.video:
            submission_type = 'video'
            content = update.message.caption or "Видео-отчет"
            
            # Скачиваем и сохраняем видео локально
            video = update.message.video
            file_path = await self._download_and_save_file(video, "video", user_id, context, task_id)
            file_id = video.file_id  # Оставляем file_id как fallback
            
        elif update.message.document:
            submission_type = 'document'
            content = update.message.caption or f"Документ: {update.message.document.file_name}"
            
            # Скачиваем и сохраняем документ локально
            document = update.message.document
            file_path = await self._download_and_save_file(document, "document", user_id, context, task_id)
            file_id = document.file_id  # Оставляем file_id как fallback
            
        else:
            await update.message.reply_text(
                "❌ Поддерживаются только текстовые сообщения, фото, видео и документы.\n\n"
                "💾 Ваше сообщение сохранено. Попробуйте отправить поддерживаемый тип файла.",
                reply_markup=self.keyboards.main_menu()
            )
            return ConversationHandler.END
        
        # Сохраняем отчет как офлайн на случай ошибки  
        try:
            if submission_type == 'text':
                submission_data = json.dumps({
                    'type': 'text',
                    'content': content,
                    'task_id': task_id,
                    'date': update.message.date.isoformat()
                }, ensure_ascii=False)
            else:
                submission_data = json.dumps({
                    'type': submission_type,
                    'content': content,
                    'file_id': file_id,
                    'file_path': file_path,  # Добавляем путь к файлу
                    'task_id': task_id,
                    'date': update.message.date.isoformat()
                }, ensure_ascii=False)
            
            # Сохраняем как потенциальный отчет
            self.db.save_offline_message(user_id, submission_data, f'submission_{submission_type}')
            logger.info(f"Отчет от пользователя {user_id} временно сохранен")
            
        except Exception as e:
            logger.error(f"Не удалось сохранить отчет: {e}")

        # Сохраняем отчет и проверяем дедлайн
        try:
            # Передаем file_path вместо file_id в метод submit_task
            is_on_time = self.db.submit_task(user_id, task_id, submission_type, content, file_id, file_path)
            
            if is_on_time:
                response_text = (
                    "✅ **Задание отправлено на проверку!**\n\n"
                    "Ваш отчет принят в срок и будет рассмотрен администратором. "
                    "Результат проверки будет отправлен вам в этом чате.\n\n"
                    "Спасибо за участие! 🌿"
                )
            else:
                response_text = (
                    "⏰ **Отчет получен, но с опозданием**\n\n"
                    "К сожалению, дедлайн для этого задания уже прошел (суббота 23:59 МСК), "
                    "поэтому задание не будет засчитано.\n\n"
                    "🌟 **Но не расстраивайтесь!** Ваше участие ценно, и мы благодарим вас за вклад в защиту природы. "
                    "Следующие задания публикуются в понедельник и четверг в 11:00 МСК.\n\n"
                    "Продолжайте заботиться о планете! 🌿💚"
                )
            
            # Очищаем состояние после успешной отправки
            self.db.clear_user_state(user_id)
            
            await update.message.reply_text(
                response_text,
                parse_mode='Markdown',
                reply_markup=self.keyboards.main_menu()
            )
            
            # Очищаем данные
            context.user_data.clear()
            
            logger.info(f"Отчет от пользователя {user_id} по заданию {task_id} успешно обработан")
            return ConversationHandler.END
            
        except Exception as e:
            logger.error(f"Ошибка при сохранении отчета: {e}")
            
            # Сохраняем подробности ошибки
            error_data = json.dumps({
                'task_id': task_id,
                'submission_type': submission_type,
                'content': content[:100] if content else None,  # Первые 100 символов
                'file_id': file_id,
                'file_path': file_path,  # Добавляем путь к файлу
                'error': str(e),
                'date': datetime.now().isoformat()
            }, ensure_ascii=False)
            
            self.db.save_offline_message(user_id, error_data, 'submission_error')
            
            await update.message.reply_text(
                "⚠️ Произошла ошибка при сохранении отчета.\n\n"
                "💾 Ваш отчет сохранен и будет обработан администратором вручную.\n\n"
                "Попробуйте отправить команду /start для восстановления работы.",
                reply_markup=self.keyboards.main_menu()
            )
            
            return ConversationHandler.END

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик callback запросов (нажатий на инлайн кнопки)"""
        query = update.callback_query
        await query.answer()
        
        user_id = update.effective_user.id
        data = query.data
        
        # Проверяем регистрацию
        if not self.db.is_user_registered(user_id):
            await query.edit_message_text(
                "❌ Сначала необходимо завершить регистрацию. Отправьте команду /start",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")
                ]])
            )
            return
        
        try:
            if data == "main_menu":
                await self._show_main_menu_callback(query)
            
            elif data == "tasks_bank":
                await self._show_tasks_bank_callback(query)
            
            elif data.startswith("submit_task_"):
                task_id = int(data.split("_")[-1])
                await self._start_task_submission(query, context, task_id)
            
            elif data == "submit_tasks":
                # Показываем список заданий для отправки
                await self._show_task_submission_callback(query, context)
            
            elif data == "support":
                # Показываем информацию о поддержке
                await self._show_support_callback(query)
            
            elif data == "instructions":
                # Показываем инструкции
                await self._show_instructions_callback(query)
            
            else:
                await query.edit_message_text(
                    "❓ Неизвестная команда. Возвращаемся в главное меню.",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")
                    ]])
                )
                
        except Exception as e:
            logger.error(f"Ошибка в обработчике callback: {e}")
            await query.edit_message_text(
                "⚠️ Произошла ошибка при обработке запроса.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")
                ]])
            )

    async def _show_main_menu_callback(self, query):
        """Показывает главное меню через callback"""
        # Очищаем состояние при возврате в главное меню
        self.db.clear_user_state(query.from_user.id)
        
        await query.edit_message_text(
            "🏠 **Главное меню**\n\nВыберите нужный раздел:",
            parse_mode='Markdown'
        )
        # Отправляем новое сообщение с клавиатурой главного меню
        await query.message.reply_text(
            "Используйте меню для навигации:",
            reply_markup=self.keyboards.main_menu()
        )

    async def _show_tasks_bank_callback(self, query):
        """Показывает банк заданий через callback - только открытые задания"""
        all_tasks = self.db.get_all_tasks()
        open_tasks = [task for task in all_tasks if task[4]]  # is_open = True
        
        current_week_tasks = self.db.get_current_week_tasks()
        
        if not open_tasks:
            text = (
                "🏦 **Банк заданий**\n\n"
                f"📅 Задания этой недели: {len(current_week_tasks)}\n"
                f"🟢 Открытых заданий: 0\n\n"
                "🚫 На данный момент нет открытых заданий.\n"
                "Задания публикуются по понедельникам и четвергам в 11:00 МСК."
            )
            
            keyboard = [[InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]]
            
            await query.edit_message_text(
                text,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        
        text = (
            "🏦 **Банк заданий**\n\n"
            f"📅 Задания этой недели: {len(current_week_tasks)}\n"
            f"🟢 Открытых заданий: {len(open_tasks)}\n\n"
            "**🟢 Открытые задания:**\n"
            "Нажмите на задание, чтобы перейти к его описанию:"
        )
        
        # Создаем клавиатуру с кнопками по одной в ряд
        keyboard = []
        
        # Добавляем кнопки открытых заданий по одной в ряд
        for task_data in open_tasks:
            task_id, title, description, link = task_data[:4]
            if link:
                # Сокращаем название если слишком длинное
                short_title = title[:40] + "..." if len(title) > 40 else title
                keyboard.append([InlineKeyboardButton(
                    f"🟢 {short_title}", 
                    url=link
                )])
        
        # Кнопка возврата в главное меню
        keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")])
        
        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _show_archived_tasks_callback(self, query):
        """Показывает архивные задания через callback"""
        all_tasks = self.db.get_all_tasks()
        archived_tasks = [task for task in all_tasks if not task[4]]  # is_open = False
        
        if not archived_tasks:
            await query.edit_message_text(
                "📁 **Архивные задания**\n\n"
                "Архивных заданий пока нет.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Назад к банку заданий", callback_data="tasks_bank"),
                    InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")
                ]])
            )
            return
        
        text = (
            f"📁 **Архивные задания** ({len(archived_tasks)})\n\n"
            "Нажмите на задание, чтобы перейти к его описанию:"
        )
        
        # Создаем клавиатуру с кнопками по одной в ряд
        keyboard = []
        
        # Добавляем кнопки архивных заданий по одной в ряд
        for task_data in archived_tasks:
            task_id, title, description, link = task_data[:4]
            if link:
                # Сокращаем название если слишком длинное
                short_title = title[:40] + "..." if len(title) > 40 else title
                keyboard.append([InlineKeyboardButton(
                    f"📁 {short_title}", 
                    url=link
                )])
        
        # Кнопки навигации
        keyboard.append([InlineKeyboardButton("🔙 Назад к банку заданий", callback_data="tasks_bank")])
        keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")])
        
        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _start_task_submission(self, query, context, task_id):
        """Начинает процесс отправки задания"""
        context.user_data['selected_task_id'] = task_id
        
        # Сохраняем состояние отправки задания
        self.db.save_user_state(
            query.from_user.id, 
            TASK_SUBMISSION, 
            context.user_data
        )
        
        await query.edit_message_text(
            "📤 **Отправка отчета**\n\n"
            "Отправьте ваш отчет одним из способов:\n"
            "• 🔗 Ссылка на пост в социальных сетях\n"
            "• 📸 Фотография\n"
            "• 🎥 Видео\n"
            "• 📄 Документ\n\n"
            "⏰ Напоминание: дедлайн - суббота 23:59 МСК",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")
            ]])
        )
        
        return TASK_SUBMISSION

    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик ошибок"""
        logger.error(f"Ошибка при обработке update {update}: {context.error}")
        
        # При критической ошибке сохраняем сообщение как офлайн
        if update and update.effective_user:
            try:
                message_data = {}
                message_type = 'error'
                
                if update.message:
                    if update.message.text:
                        message_data = {
                            'text': update.message.text,
                            'error': str(context.error),
                            'date': update.message.date.isoformat()
                        }
                        message_type = 'text_error'
                    elif update.message.photo:
                        message_data = {
                            'caption': update.message.caption,
                            'file_id': update.message.photo[-1].file_id,
                            'error': str(context.error),
                            'date': update.message.date.isoformat()
                        }
                        message_type = 'photo_error'
                    elif update.message.video:
                        message_data = {
                            'caption': update.message.caption,
                            'file_id': update.message.video.file_id,
                            'error': str(context.error),
                            'date': update.message.date.isoformat()
                        }
                        message_type = 'video_error'
                
                self.db.save_offline_message(
                    update.effective_user.id,
                    json.dumps(message_data, ensure_ascii=False),
                    message_type
                )
                
                logger.info(f"Сообщение сохранено как офлайн из-за ошибки: {context.error}")
                
            except Exception as e:
                logger.error(f"Не удалось сохранить сообщение как офлайн: {e}")
        
        # Пытаемся отправить пользователю сообщение об ошибке
        try:
            if update and update.effective_message:
                await update.effective_message.reply_text(
                    "⚠️ Произошла ошибка при обработке вашего сообщения. "
                    "Ваше сообщение сохранено и будет обработано при следующем запуске бота.\n\n"
                    "Попробуйте отправить команду /start для восстановления работы.",
                    reply_markup=self.keyboards.main_menu()
                )
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение об ошибке пользователю: {e}")

    async def _show_task_submission_callback(self, query, context):
        """Показывает список заданий для отправки через callback"""
        user_id = query.from_user.id
        open_tasks = self.db.get_open_tasks()
        
        # Получаем ID заданий, на которые пользователь уже отправил отчеты
        submitted_task_ids = set()
        try:
            user_submissions = self.db.get_user_submissions(user_id)
            for submission in user_submissions:
                # Получаем ID задания из базы по названию
                for task in open_tasks:
                    if task[1] == submission[0]:  # Сравниваем название
                        submitted_task_ids.add(task[0])
                        break
        except Exception as e:
            logger.error(f"Ошибка при получении отправленных заданий: {e}")
        
        # Фильтруем задания, исключая уже отправленные
        available_tasks = [task for task in open_tasks if task[0] not in submitted_task_ids]
        
        if not available_tasks:
            text = (
                "📤 **Отправка отчетов**\n\n"
                f"🟢 Всего открытых заданий: {len(open_tasks)}\n"
                f"✅ Вы уже отправили отчеты по всем доступным заданиям!\n\n"
            )
            
            if len(open_tasks) == 0:
                text += (
                    "🚫 На данный момент нет доступных заданий для отправки.\n"
                    "Задания публикуются по понедельникам и четвергам в 11:00 МСК."
                )
            else:
                text += (
                    "🎉 Отличная работа! Проверьте раздел 'Мой результат' для отслеживания статуса проверки.\n\n"
                    "Новые задания публикуются по понедельникам и четвергам в 11:00 МСК."
                )
            
            await query.edit_message_text(
                text,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")
                ]])
            )
            # Отправляем новое сообщение с основным меню
            await query.message.reply_text(
                "Используйте меню для навигации:",
                reply_markup=self.keyboards.main_menu()
            )
            return
        
        text = (
            "📤 **Отправка отчетов**\n\n"
            f"🟢 Всего открытых заданий: {len(open_tasks)}\n"
            f"📝 Доступно для отправки: {len(available_tasks)}\n"
            f"✅ Уже отправлено: {len(submitted_task_ids)}\n\n"
            "**Выберите задание для отправки отчета:**"
        )
        
        # Создаем клавиатуру с кнопками по одной в ряд
        keyboard = []
        
        for task_data in available_tasks:
            task_id, title, description, _ = task_data[:4]
            # Сокращаем название если слишком длинное  
            short_title = title[:40] + "..." if len(title) > 40 else title
            keyboard.append([InlineKeyboardButton(
                f"📝 {short_title}", 
                callback_data=f"submit_task_{task_id}"
            )])
        
        # Кнопка возврата
        keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")])
        
        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _show_support_callback(self, query):
        """Показывает информацию о поддержке через callback"""
        text = (
            "🆘 **Обращение в поддержку**\n\n"
            "Для получения помощи обратитесь к администратору:\n"
            "👨‍💻 @Danlocked\n\n"
            "Администратор поможет вам с:\n"
            "• Техническими вопросами\n"
            "• Проблемами с заданиями\n"
            "• Регистрацией и участием\n"
            "• Любыми другими вопросами"
        )
        
        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")
            ]])
        )
        # Отправляем новое сообщение с основным меню
        await query.message.reply_text(
            "Используйте меню для навигации:",
            reply_markup=self.keyboards.main_menu()
        )

    async def _show_instructions_callback(self, query):
        """Показывает инструкции через callback"""
        current_time = datetime.now(self.moscow_tz)
        weekday = current_time.weekday()  # 0 = понедельник
        
        # Определяем следующую дату публикации
        if weekday < 1:  # До понедельника
            next_publication = "понедельник в 11:00 МСК"
        elif weekday < 3:  # Между понедельником и четвергом
            next_publication = "четверг в 11:00 МСК"
        elif weekday < 5:  # Между четвергом и субботой
            next_publication = "следующий понедельник в 11:00 МСК"
        else:  # Выходные
            next_publication = "понедельник в 11:00 МСК"
        
        text = (
            "📖 **Инструкция по прохождению**\n\n"
            "**Расписание заданий:**\n"
            "🕐 Публикация: понедельник и четверг в 11:00 МСК\n"
            "⏰ Дедлайн: суббота в 23:59 МСК\n"
            f"📅 Следующая публикация: {next_publication}\n\n"
            "**Как участвовать:**\n"
            "1️⃣ Дождитесь публикации заданий\n"
            "2️⃣ Изучите задание в разделе 'Банк заданий'\n"
            "3️⃣ Выполните задание согласно инструкциям\n"
            "4️⃣ Подготовьте отчет:\n"
            "   • Ссылка на пост в соцсетях\n"
            "   • Фотографии\n"
            "   • Видео\n"
            "5️⃣ Отправьте отчет до субботы 23:59 МСК\n"
            "6️⃣ Получите обратную связь\n\n"
            "⚠️ **Важно:** Опоздавшие отчеты не засчитываются, но мы всё равно вас поддержим!"
        )
        
        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")
            ]])
        )
        # Отправляем новое сообщение с основным меню
        await query.message.reply_text(
            "Используйте меню для навигации:",
            reply_markup=self.keyboards.main_menu()
        )

    async def handle_photo_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик фото сообщений"""
        user_id = update.effective_user.id
        
        # Проверяем регистрацию
        if not self.db.is_user_registered(user_id):
            await update.message.reply_text(
                "❌ Сначала необходимо завершить регистрацию. Отправьте команду /start\n\n"
                "💾 Ваше фото сохранено и будет обработано после регистрации.",
                reply_markup=self.keyboards.main_menu()
            )
            return
        
        # Проверяем состояние пользователя
        saved_state, saved_context = self.db.get_user_state(user_id)
        
        if saved_state == TASK_SUBMISSION:
            # Если в состоянии отправки задания - обрабатываем через основной handler
            for key, value in saved_context.items():
                context.user_data[key] = value
            return await self.handle_task_submission_content(update, context)
        
        # Иначе это потенциальный отчет вне контекста - сохраняем локально
        photo = update.message.photo[-1]
        file_path = await self._download_and_save_file(photo, "photo", user_id, context)
        
        photo_data = json.dumps({
            'user_id': user_id,
            'content': update.message.caption or "Фото без подписи",
            'type': 'photo',
            'file_id': photo.file_id,
            'file_path': file_path,  # Добавляем локальный путь
            'date': update.message.date.isoformat(),
            'context': 'potential_report_out_of_context'
        }, ensure_ascii=False)
        
        self.db.save_offline_message(user_id, photo_data, 'potential_report')
        logger.info(f"Потенциальный фото-отчет от пользователя {user_id} сохранен локально: {file_path}")
        
        await update.message.reply_text(
            "📸 **Фото получено!**\n\n"
            "Ваше фото сохранено и будет обработано администратором. "
            "Если это отчет по заданию, используйте кнопку 'Отправить отчет' из главного меню.",
            reply_markup=self.keyboards.main_menu()
        )

    async def handle_video_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик видео сообщений"""
        user_id = update.effective_user.id
        
        # Проверяем регистрацию
        if not self.db.is_user_registered(user_id):
            await update.message.reply_text(
                "❌ Сначала необходимо завершить регистрацию. Отправьте команду /start\n\n"
                "💾 Ваше видео сохранено и будет обработано после регистрации.",
                reply_markup=self.keyboards.main_menu()
            )
            return
        
        # Проверяем состояние пользователя
        saved_state, saved_context = self.db.get_user_state(user_id)
        
        if saved_state == TASK_SUBMISSION:
            # Если в состоянии отправки задания - обрабатываем через основной handler
            for key, value in saved_context.items():
                context.user_data[key] = value
            return await self.handle_task_submission_content(update, context)
        
        # Иначе это потенциальный отчет вне контекста - сохраняем локально
        video = update.message.video
        file_path = await self._download_and_save_file(video, "video", user_id, context)
        
        video_data = json.dumps({
            'user_id': user_id,
            'content': update.message.caption or "Видео без подписи",
            'type': 'video',
            'file_id': video.file_id,
            'file_path': file_path,  # Добавляем локальный путь
            'date': update.message.date.isoformat(),
            'context': 'potential_report_out_of_context'
        }, ensure_ascii=False)
        
        self.db.save_offline_message(user_id, video_data, 'potential_report')
        logger.info(f"Потенциальный видео-отчет от пользователя {user_id} сохранен локально: {file_path}")
        
        await update.message.reply_text(
            "🎥 **Видео получено!**\n\n"
            "Ваше видео сохранено и будет обработано администратором. "
            "Если это отчет по заданию, используйте кнопку 'Отправить отчет' из главного меню.",
            reply_markup=self.keyboards.main_menu()
        )

    async def handle_document_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик документов"""
        user_id = update.effective_user.id
        
        # Проверяем регистрацию
        if not self.db.is_user_registered(user_id):
            await update.message.reply_text(
                "❌ Сначала необходимо завершить регистрацию. Отправьте команду /start\n\n"
                "💾 Ваш документ сохранен и будет обработан после регистрации.",
                reply_markup=self.keyboards.main_menu()
            )
            return
        
        # Проверяем состояние пользователя
        saved_state, saved_context = self.db.get_user_state(user_id)
        
        if saved_state == TASK_SUBMISSION:
            # Если в состоянии отправки задания - обрабатываем через основной handler
            for key, value in saved_context.items():
                context.user_data[key] = value
            return await self.handle_task_submission_content(update, context)
        
        # Иначе это потенциальный отчет вне контекста - сохраняем локально
        document = update.message.document
        file_path = await self._download_and_save_file(document, "document", user_id, context)
        
        document_data = json.dumps({
            'user_id': user_id,
            'content': update.message.caption or f"Документ: {document.file_name}",
            'type': 'document',
            'file_id': document.file_id,
            'file_path': file_path,  # Добавляем локальный путь
            'filename': document.file_name,
            'date': update.message.date.isoformat(),
            'context': 'potential_report_out_of_context'
        }, ensure_ascii=False)
        
        self.db.save_offline_message(user_id, document_data, 'potential_report')
        logger.info(f"Потенциальный документ-отчет от пользователя {user_id} сохранен локально: {file_path}")
        
        await update.message.reply_text(
            "📄 **Документ получен!**\n\n"
            "Ваш документ сохранен и будет обработан администратором. "
            "Если это отчет по заданию, используйте кнопку 'Отправить отчет' из главного меню.",
            reply_markup=self.keyboards.main_menu()
        )

    async def _download_and_save_file(self, file_obj, file_type: str, user_id: int, context: ContextTypes.DEFAULT_TYPE, task_id: int = None) -> Optional[str]:
        """
        Скачивает файл от Telegram и сохраняет локально
        
        Args:
            file_obj: Объект файла от Telegram
            file_type: Тип файла (photo, video, document)
            user_id: ID пользователя
            context: Контекст бота для доступа к API
            task_id: ID задания (если есть)
            
        Returns:
            Путь к сохраненному файлу или None при ошибке
        """
        try:
            # Генерируем уникальное имя файла
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            if file_type == "photo":
                file_extension = ".jpg"
                subdirectory = "photos"
            elif file_type == "video":
                file_extension = ".mp4"
                subdirectory = "videos"
            elif file_type == "document":
                # Получаем оригинальное расширение если есть
                original_name = getattr(file_obj, 'file_name', '')
                if '.' in original_name:
                    file_extension = '.' + original_name.split('.')[-1]
                else:
                    file_extension = ".bin"
                subdirectory = "documents"
            else:
                file_extension = ".unknown"
                subdirectory = "documents"
            
            # Формируем имя файла: user123_task456_20250102_143000.jpg
            if task_id:
                filename = f"user{user_id}_task{task_id}_{timestamp}{file_extension}"
            else:
                filename = f"user{user_id}_potential_{timestamp}{file_extension}"
            
            # Полный путь к файлу
            file_path = os.path.join(self.files_dir, subdirectory, filename)
            
            # Получаем file_id для скачивания
            file_id = file_obj.file_id
            
            # Получаем информацию о файле от Telegram
            file_info = await context.bot.get_file(file_id)
            
            # Скачиваем файл 
            await file_info.download_to_drive(file_path)
            
            logger.info(f"Файл сохранен: {file_path} (размер: {os.path.getsize(file_path)} байт)")
            
            # Возвращаем относительный путь для сохранения в БД
            return os.path.join(subdirectory, filename)
            
        except Exception as e:
            logger.error(f"Ошибка при скачивании файла: {e}")
            return None

def main():
    """Основная функция запуска бота"""
    # Получаем токен из переменных окружения
    token = os.getenv('BOT_TOKEN')
    if not token:
        logger.error("BOT_TOKEN не найден в переменных окружения!")
        logger.info("Создайте файл .env с BOT_TOKEN=your_bot_token")
        return
    
    # Создаем экземпляр бота
    bot = EcoBot()
    
    # Создаем приложение без persistence (используем собственную систему сохранения)
    application = Application.builder().token(token).proxy(None).build()
    
    # Добавляем обработчик для отслеживания всех сообщений (middleware)
    offline_handler = OfflineMessageHandler(bot.db)
    application.add_handler(offline_handler, -1)  # Добавляем с низким приоритетом
    
    # ConversationHandler для регистрации без встроенного persistence
    registration_handler = ConversationHandler(
        entry_points=[CommandHandler("start", bot.start)],
        states={
            REGISTRATION_LAST_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.registration_last_name)],
            REGISTRATION_FIRST_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.registration_first_name)],
            PARTICIPATION_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.participation_type)],
            FAMILY_MEMBERS_COUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.family_members_count)],
            CHILDREN_INFO: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.children_info)]
        },
        fallbacks=[CommandHandler("start", bot.start)],
        allow_reentry=True,
        # Убираем persistent=True - используем собственную систему
        name="registration"
    )
    
    # ConversationHandler для отправки заданий
    task_submission_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(bot.handle_callback, pattern="^submit_task_")],
        states={
            TASK_SUBMISSION: [MessageHandler(
                filters.TEXT | filters.PHOTO | filters.VIDEO | filters.Document.ALL, 
                bot.handle_task_submission_content
            )]
        },
        fallbacks=[MessageHandler(filters.Regex("^🏠 Главное меню$"), bot._send_main_menu)],
        # Убираем persistent=True - используем собственную систему
        name="task_submission",
        per_message=False  # Добавляем для избежания предупреждения
    )
    
    # ConversationHandler для изменения профиля
    profile_edit_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^✏️ Изменить имя$"), bot._start_edit_first_name),
            MessageHandler(filters.Regex("^✏️ Изменить фамилию$"), bot._start_edit_last_name)
        ],
        states={
            EDIT_FIRST_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_edit_first_name)],
            EDIT_LAST_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_edit_last_name)]
        },
        fallbacks=[MessageHandler(filters.Regex("^🏠 Главное меню$"), bot._send_main_menu)],
        name="profile_edit",
        per_message=False
    )
    
    # Регистрируем обработчики
    application.add_handler(registration_handler)
    application.add_handler(task_submission_handler)
    application.add_handler(profile_edit_handler)
    application.add_handler(CallbackQueryHandler(bot.handle_callback))
    # Добавляем обработчик для кнопки поддержки
    application.add_handler(MessageHandler(filters.Regex("^🆘 Обращение в поддержку$"), bot._start_support_request))
    
    # Добавляем обработчики медиа сообщений
    application.add_handler(MessageHandler(filters.PHOTO, bot.handle_photo_message))
    application.add_handler(MessageHandler(filters.VIDEO, bot.handle_video_message))
    application.add_handler(MessageHandler(filters.Document.ALL, bot.handle_document_message))
    
    # Обработчик текстовых сообщений должен быть последним
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_message))
    
    # Добавляем обработчик ошибок
    application.add_error_handler(bot.error_handler)
    
    # Запускаем бота
    logger.info("🌿 Эко-бот запущен с поддержкой сохранения состояний...")
    logger.info("📱 Состояния пользователей сохраняются между перезапусками")
    logger.info("📬 Офлайн сообщения будут обработаны при следующем запуске")
    logger.info("🔄 Пользователи смогут продолжить с того места, где остановились")
    logger.info("💾 Используется собственная система persistence в SQLite")
    logger.info("⏹️ Для остановки нажмите Ctrl+C")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main() 