#!/usr/bin/env python3
"""
Скрипт для работы с потенциальными отчетами
"""

from database import Database
import json
from datetime import datetime

def main():
    db = Database()
    
    print("🔍 Проверка потенциальных отчетов")
    print("=" * 50)
    
    # Получаем сводку
    summary = db.get_all_potential_reports_summary()
    print(f"📊 Всего потенциальных отчетов: {summary['total']}")
    print(f"📝 Текстовых: {summary['types']['text']}")
    print(f"📸 Фото: {summary['types']['photo']}")
    print(f"🎥 Видео: {summary['types']['video']}")
    print(f"📄 Документов: {summary['types']['document']}")
    print()
    
    # Получаем все потенциальные отчеты
    reports = db.get_potential_reports()
    
    if not reports:
        print("✅ Нет необработанных потенциальных отчетов")
        return
    
    print("📋 Список потенциальных отчетов:")
    print("-" * 50)
    
    for report_id, user_id, message_data, message_type, received_date in reports:
        try:
            data = json.loads(message_data)
            content = data.get('content', 'Нет содержимого')
            msg_type = data.get('type', 'text')
            
            # Форматируем дату
            date_obj = datetime.fromisoformat(received_date.replace('Z', '+00:00'))
            formatted_date = date_obj.strftime("%d.%m.%Y %H:%M")
            
            print(f"ID: {report_id}")
            print(f"👤 Пользователь: {user_id}")
            print(f"📅 Дата: {formatted_date}")
            print(f"📝 Тип: {msg_type}")
            print(f"💬 Содержимое: {content[:100]}{'...' if len(content) > 100 else ''}")
            
            if 'file_id' in data:
                print(f"🗂️ File ID: {data['file_id']}")
            
            print("-" * 30)
            
        except json.JSONDecodeError:
            print(f"❌ Ошибка декодирования данных для отчета {report_id}")
    
    print(f"\n💡 Всего найдено: {len(reports)} потенциальных отчетов")
    print("\nДля обработки используйте admin_tools.py")

if __name__ == "__main__":
    main() 