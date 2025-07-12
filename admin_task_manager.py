#!/usr/bin/env python3
"""
Расширенный менеджер заданий для админ-бота
Дополнительные функции для создания и управления заданиями
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import pytz

logger = logging.getLogger(__name__)

class TaskManager:
    """Класс для управления заданиями с расширенными функциями"""
    
    def __init__(self, db):
        self.db = db
        self.moscow_tz = pytz.timezone('Europe/Moscow')
    
    def create_task_from_template(self, template_name: str, week_number: int = None, 
                                custom_params: Dict[str, Any] = None) -> dict:
        """
        Создает задание из шаблона
        
        Args:
            template_name: Имя шаблона
            week_number: Номер недели (если None, то текущая)
            custom_params: Дополнительные параметры для настройки
        
        Returns:
            dict: Данные созданного задания
        """
        if week_number is None:
            week_number = datetime.now(self.moscow_tz).isocalendar()[1]
        
        templates = self._get_task_templates()
        template = templates.get(template_name)
        
        if not template:
            raise ValueError(f"Шаблон '{template_name}' не найден")
        
        # Применяем кастомные параметры
        if custom_params:
            template.update(custom_params)
        
        # Добавляем номер недели к названию
        template['title'] = f"{template['title']} - Неделя {week_number}"
        template['week_number'] = week_number
        
        # Вычисляем дедлайн
        deadline = self._calculate_deadline_for_week(week_number)
        template['deadline'] = deadline
        
        return template
    
    def _get_task_templates(self) -> Dict[str, dict]:
        """Возвращает доступные шаблоны заданий"""
        return {
            'observation': {
                'title': 'Экологическое наблюдение',
                'description': 'Проведите наблюдение за природой в вашем районе. Сфотографируйте интересные природные объекты и поделитесь своими наблюдениями.',
                'link': None,
                'category': 'observation'
            },
            'action': {
                'title': 'Экологическое действие',
                'description': 'Совершите одно полезное действие для окружающей среды. Это может быть уборка территории, посадка растений или сортировка отходов.',
                'link': None,
                'category': 'action'
            },
            'research': {
                'title': 'Исследование природы',
                'description': 'Проведите небольшое исследование природного объекта в вашем районе. Изучите его особенности и поделитесь результатами.',
                'link': None,
                'category': 'research'
            },
            'cleanup': {
                'title': 'Экологическая уборка',
                'description': 'Организуйте уборку территории в вашем районе. Соберите мусор, очистите природную зону и поделитесь результатами.',
                'link': None,
                'category': 'action'
            },
            'education': {
                'title': 'Экологическое просвещение',
                'description': 'Поделитесь знаниями об экологии с окружающими. Расскажите друзьям или семье о важности охраны природы.',
                'link': None,
                'category': 'education'
            },
            'monitoring': {
                'title': 'Экологический мониторинг',
                'description': 'Проведите измерения экологических показателей в вашем районе: качество воздуха, воды, уровень шума.',
                'link': None,
                'category': 'research'
            }
        }
    
    def create_weekly_task_set(self, week_number: int, task_types: List[str] = None) -> List[dict]:
        """
        Создает набор заданий для недели
        
        Args:
            week_number: Номер недели
            task_types: Список типов заданий (если None, то стандартный набор)
        
        Returns:
            List[dict]: Список созданных заданий
        """
        if task_types is None:
            task_types = ['observation', 'action']  # Стандартный набор
        
        tasks = []
        for task_type in task_types:
            try:
                task_data = self.create_task_from_template(task_type, week_number)
                tasks.append(task_data)
            except ValueError as e:
                logger.warning(f"Не удалось создать задание типа '{task_type}': {e}")
        
        return tasks
    
    def _calculate_deadline_for_week(self, week_number: int) -> datetime:
        """Вычисляет дедлайн для недели (суббота 23:59)"""
        current_year = datetime.now(self.moscow_tz).year
        jan_4 = datetime(current_year, 1, 4, tzinfo=self.moscow_tz)
        week_start = jan_4 + timedelta(weeks=week_number - 1, days=-jan_4.weekday())
        return week_start + timedelta(days=5, hours=23, minutes=59)
    
    def validate_task_data(self, task_data: dict) -> tuple[bool, List[str]]:
        """
        Валидирует данные задания
        
        Args:
            task_data: Словарь с данными задания
        
        Returns:
            tuple: (is_valid, list_of_errors)
        """
        errors = []
        
        # Проверка обязательных полей
        if not task_data.get('title'):
            errors.append("Отсутствует название задания")
        elif len(task_data['title']) < 5:
            errors.append("Название задания слишком короткое (минимум 5 символов)")
        elif len(task_data['title']) > 100:
            errors.append("Название задания слишком длинное (максимум 100 символов)")
        
        if not task_data.get('description'):
            errors.append("Отсутствует описание задания")
        elif len(task_data['description']) < 10:
            errors.append("Описание задания слишком короткое (минимум 10 символов)")
        elif len(task_data['description']) > 1000:
            errors.append("Описание задания слишком длинное (максимум 1000 символов)")
        
        # Проверка ссылки
        if task_data.get('link') and not self._validate_url(task_data['link']):
            errors.append("Некорректная ссылка")
        
        # Проверка номера недели
        if task_data.get('week_number'):
            week = task_data['week_number']
            if not isinstance(week, int) or week < 1 or week > 53:
                errors.append("Некорректный номер недели (должен быть от 1 до 53)")
        
        # Проверка дедлайна
        if task_data.get('deadline'):
            deadline = task_data['deadline']
            if isinstance(deadline, str):
                try:
                    deadline = datetime.fromisoformat(deadline)
                except ValueError:
                    errors.append("Некорректный формат дедлайна")
            
            if isinstance(deadline, datetime) and deadline <= datetime.now(self.moscow_tz):
                errors.append("Дедлайн не может быть в прошлом")
        
        return len(errors) == 0, errors
    
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
    
    def get_task_statistics(self, task_id: int) -> dict:
        """
        Получает статистику по заданию
        
        Args:
            task_id: ID задания
        
        Returns:
            dict: Статистика задания
        """
        try:
            with self.db._get_connection() as conn:
                cursor = conn.cursor()
                
                # Основная информация о задании
                cursor.execute('''
                    SELECT title, description, deadline, is_open, created_date
                    FROM tasks WHERE id = ?
                ''', (task_id,))
                task_info = cursor.fetchone()
                
                if not task_info:
                    return {'error': 'Задание не найдено'}
                
                # Статистика отчетов
                cursor.execute('''
                    SELECT 
                        COUNT(*) as total_submissions,
                        COUNT(CASE WHEN status = 'approved' THEN 1 END) as approved,
                        COUNT(CASE WHEN status = 'rejected' THEN 1 END) as rejected,
                        COUNT(CASE WHEN status = 'pending' THEN 1 END) as pending,
                        COUNT(CASE WHEN is_on_time = 1 THEN 1 END) as on_time
                    FROM submissions WHERE task_id = ?
                ''', (task_id,))
                stats = cursor.fetchone()
                
                # Уникальные участники
                cursor.execute('''
                    SELECT COUNT(DISTINCT user_id) as unique_users
                    FROM submissions WHERE task_id = ?
                ''', (task_id,))
                unique_users = cursor.fetchone()[0]
                
                return {
                    'title': task_info[0],
                    'description': task_info[1],
                    'deadline': task_info[2],
                    'is_open': task_info[3],
                    'created_date': task_info[4],
                    'total_submissions': stats[0],
                    'approved_submissions': stats[1],
                    'rejected_submissions': stats[2],
                    'pending_submissions': stats[3],
                    'on_time_submissions': stats[4],
                    'unique_participants': unique_users,
                    'completion_rate': (stats[1] / max(stats[0], 1)) * 100,
                    'on_time_rate': (stats[4] / max(stats[0], 1)) * 100
                }
                
        except Exception as e:
            logger.error(f"Ошибка при получении статистики задания {task_id}: {e}")
            return {'error': str(e)}
    
    def duplicate_task(self, task_id: int, new_week: int = None, modifications: dict = None) -> dict:
        """
        Дублирует существующее задание
        
        Args:
            task_id: ID задания для дублирования
            new_week: Новый номер недели (если None, то следующая неделя)
            modifications: Изменения для применения к дубликату
        
        Returns:
            dict: Данные нового задания
        """
        try:
            with self.db._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT title, description, link, week_number
                    FROM tasks WHERE id = ?
                ''', (task_id,))
                task_data = cursor.fetchone()
                
                if not task_data:
                    raise ValueError(f"Задание с ID {task_id} не найдено")
                
                # Создаем новое задание на основе существующего
                new_task = {
                    'title': task_data[0],
                    'description': task_data[1],
                    'link': task_data[2],
                    'week_number': new_week or (task_data[3] + 1 if task_data[3] else None)
                }
                
                # Применяем модификации
                if modifications:
                    new_task.update(modifications)
                
                # Обновляем название с новой неделей
                if new_task['week_number']:
                    # Убираем старый номер недели из названия
                    title = new_task['title']
                    if ' - Неделя ' in title:
                        title = title.split(' - Неделя ')[0]
                    new_task['title'] = f"{title} - Неделя {new_task['week_number']}"
                
                # Вычисляем новый дедлайн
                if new_task['week_number']:
                    new_task['deadline'] = self._calculate_deadline_for_week(new_task['week_number'])
                
                return new_task
                
        except Exception as e:
            logger.error(f"Ошибка при дублировании задания {task_id}: {e}")
            raise
    
    def get_template_suggestions(self, week_number: int) -> List[dict]:
        """
        Получает предложения шаблонов для недели
        
        Args:
            week_number: Номер недели
        
        Returns:
            List[dict]: Список предложенных шаблонов
        """
        templates = self._get_task_templates()
        suggestions = []
        
        # Логика выбора шаблонов в зависимости от недели
        if week_number % 4 == 1:  # Каждая 4-я неделя - исследование
            primary_templates = ['observation', 'research']
        elif week_number % 3 == 0:  # Каждая 3-я неделя - действие
            primary_templates = ['action', 'cleanup']
        else:  # Обычные недели
            primary_templates = ['observation', 'action']
        
        for template_name in primary_templates:
            if template_name in templates:
                template = templates[template_name].copy()
                template['template_name'] = template_name
                template['suggested_for_week'] = week_number
                suggestions.append(template)
        
        return suggestions
    
    def export_task_data(self, task_id: int, format: str = 'json') -> str:
        """
        Экспортирует данные задания
        
        Args:
            task_id: ID задания
            format: Формат экспорта ('json', 'csv')
        
        Returns:
            str: Экспортированные данные
        """
        try:
            stats = self.get_task_statistics(task_id)
            
            if 'error' in stats:
                raise ValueError(stats['error'])
            
            if format == 'json':
                return json.dumps(stats, ensure_ascii=False, indent=2)
            elif format == 'csv':
                # Простой CSV формат
                lines = []
                lines.append("Параметр,Значение")
                for key, value in stats.items():
                    lines.append(f"{key},{value}")
                return '\n'.join(lines)
            else:
                raise ValueError(f"Неподдерживаемый формат: {format}")
                
        except Exception as e:
            logger.error(f"Ошибка при экспорте данных задания {task_id}: {e}")
            raise 