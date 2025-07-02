#!/usr/bin/env python3
"""
Демонстрационный скрипт для тестирования функций сохранения состояний
и офлайн сообщений в Эко-боте
"""
import json
from datetime import datetime
from database import Database

def demo_offline_messages():
    """Демонстрирует работу с офлайн сообщениями"""
    print("🧪 Демонстрация системы офлайн сообщений\n")
    
    db = Database()
    
    # Симулируем пользователя
    user_id = 123456789
    
    # Добавляем пользователя
    db.add_user(user_id, "testuser", "Тест", "Пользователь")
    
    # Симулируем офлайн сообщения разных типов
    offline_messages = [
        {
            'type': 'text',
            'data': {
                'text': 'Привет! Как дела с заданиями?',
                'date': datetime.now().isoformat()
            }
        },
        {
            'type': 'photo',
            'data': {
                'caption': 'Мой экологический отчет!',
                'file_id': 'AgACAgIAAxkBAAIBY2...',
                'date': datetime.now().isoformat()
            }
        },
        {
            'type': 'text',
            'data': {
                'text': '📊 Мой результат',
                'date': datetime.now().isoformat()
            }
        }
    ]
    
    print("📬 Сохраняем офлайн сообщения...")
    for msg in offline_messages:
        db.save_offline_message(
            user_id,
            json.dumps(msg['data'], ensure_ascii=False),
            msg['type']
        )
        print(f"   💾 Сохранено {msg['type']}: {msg['data'].get('text', msg['data'].get('caption', 'файл'))}")
    
    # Получаем офлайн сообщения
    print(f"\n📥 Получаем офлайн сообщения для пользователя {user_id}:")
    messages = db.get_offline_messages(user_id)
    
    for msg_id, message_data, message_type, received_date in messages:
        try:
            data = json.loads(message_data)
            content = data.get('text', data.get('caption', 'файл'))
            print(f"   📨 ID {msg_id}: [{message_type}] {content}")
        except json.JSONDecodeError:
            print(f"   📨 ID {msg_id}: [{message_type}] {message_data}")
    
    # Помечаем сообщения как обработанные
    print(f"\n✅ Помечаем сообщения как обработанные...")
    for msg_id, _, _, _ in messages:
        db.mark_offline_message_processed(msg_id)
        print(f"   ✓ Сообщение {msg_id} обработано")
    
    # Проверяем, что офлайн сообщений больше нет
    remaining = db.get_offline_messages(user_id)
    print(f"\n📭 Оставшихся офлайн сообщений: {len(remaining)}")

def demo_user_states():
    """Демонстрирует работу с состояниями пользователей"""
    print("\n🧪 Демонстрация системы сохранения состояний\n")
    
    db = Database()
    
    user_id = 987654321
    
    # Добавляем пользователя
    db.add_user(user_id, "stateuser", "Состояние", "Пользователь")
    
    print("💾 Сохраняем состояние пользователя...")
    
    # Симулируем состояние регистрации
    context_data = {
        'last_name': 'Иванов',
        'first_name': 'Иван',
        'participation_type': 'family'
    }
    
    db.save_user_state(user_id, 4, context_data)  # FAMILY_MEMBERS_COUNT = 4
    print(f"   ✓ Состояние: 4 (ввод количества участников семьи)")
    print(f"   ✓ Контекст: {context_data}")
    
    # Получаем состояние
    print(f"\n📥 Восстанавливаем состояние пользователя {user_id}:")
    state, restored_context = db.get_user_state(user_id)
    
    print(f"   📊 Состояние: {state}")
    print(f"   📝 Контекст: {restored_context}")
    
    # Обновляем состояние
    print(f"\n🔄 Обновляем состояние...")
    restored_context['family_members_count'] = 3
    db.save_user_state(user_id, 5, restored_context)  # CHILDREN_INFO = 5
    
    state, final_context = db.get_user_state(user_id)
    print(f"   📊 Новое состояние: {state}")
    print(f"   📝 Обновленный контекст: {final_context}")
    
    # Очищаем состояние
    print(f"\n🧹 Очищаем состояние...")
    db.clear_user_state(user_id)
    
    state, cleared_context = db.get_user_state(user_id)
    print(f"   📊 Очищенное состояние: {state}")
    print(f"   📝 Очищенный контекст: {cleared_context}")

def demo_error_recovery():
    """Демонстрирует восстановление после ошибок"""
    print("\n🧪 Демонстрация восстановления после ошибок\n")
    
    db = Database()
    
    user_id = 555666777
    db.add_user(user_id, "erroruser", "Ошибка", "Пользователь")
    
    print("💥 Симулируем ошибку с сохранением сообщения...")
    
    # Симулируем ошибку при обработке сообщения
    error_data = {
        'text': 'Сообщение, которое вызвало ошибку',
        'error': 'TimeoutError: Connection timed out',
        'date': datetime.now().isoformat()
    }
    
    db.save_offline_message(
        user_id,
        json.dumps(error_data, ensure_ascii=False),
        'text_error'
    )
    
    print(f"   💾 Сохранено сообщение с ошибкой: {error_data['text']}")
    print(f"   ⚠️ Ошибка: {error_data['error']}")
    
    # Восстанавливаем сообщения после исправления ошибки
    print(f"\n🔧 Восстанавливаем сообщения после исправления...")
    error_messages = db.get_offline_messages(user_id)
    
    for msg_id, message_data, message_type, received_date in error_messages:
        try:
            data = json.loads(message_data)
            print(f"   📨 Восстановлено: {data.get('text', 'файл')}")
            if 'error' in data:
                print(f"   🔍 Была ошибка: {data['error']}")
            
            # Помечаем как обработанное
            db.mark_offline_message_processed(msg_id)
            print(f"   ✅ Сообщение {msg_id} успешно обработано")
            
        except json.JSONDecodeError as e:
            print(f"   ❌ Ошибка при восстановлении сообщения {msg_id}: {e}")

def main():
    """Основная функция демонстрации"""
    print("🤖 Демонстрация системы сохранения состояний Эко-бота")
    print("=" * 60)
    
    try:
        demo_offline_messages()
        demo_user_states()
        demo_error_recovery()
        
        print("\n🎉 Все демонстрации завершены успешно!")
        print("\n📋 Возможности системы:")
        print("  ✅ Сохранение офлайн сообщений")
        print("  ✅ Восстановление состояний пользователей")
        print("  ✅ Обработка ошибок с сохранением данных")
        print("  ✅ Продолжение с места прерывания")
        
        print("\n🚀 Теперь бот готов к работе с полной поддержкой офлайн режима!")
        
    except Exception as e:
        print(f"\n❌ Ошибка при демонстрации: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main() 