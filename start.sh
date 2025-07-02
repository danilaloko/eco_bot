#!/bin/bash

# Скрипт запуска Эко-бота
echo "🌿 Запуск Эко-бота..."

# Проверяем наличие файла .env
if [ ! -f .env ]; then
    echo "❌ Файл .env не найден!"
    echo "📝 Создайте файл .env со следующим содержимым:"
    echo "BOT_TOKEN=your_bot_token_here"
    echo "ADMIN_ID=your_telegram_id_here"
    exit 1
fi

# Проверяем наличие Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 не установлен!"
    exit 1
fi

# Проверяем наличие pip
if ! command -v pip3 &> /dev/null; then
    echo "❌ pip3 не установлен!"
    exit 1
fi

# Устанавливаем зависимости, если необходимо
if [ ! -d "venv" ]; then
    echo "📦 Создание виртуального окружения..."
    python3 -m venv venv
fi

echo "🔧 Активация виртуального окружения..."
source venv/bin/activate

echo "📥 Установка зависимостей..."
pip install -r requirements.txt

echo "🚀 Запуск бота..."
python bot.py 