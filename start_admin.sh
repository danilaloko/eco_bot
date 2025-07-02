#!/bin/bash
# Скрипт запуска Админ-бота для Эко-бота

echo "🔧 Запуск Админ-бота для управления Эко-ботом..."
echo "=============================================="

# Проверяем наличие .env файла
if [ ! -f ".env" ]; then
    echo "❌ Файл .env не найден!"
    echo "📝 Создайте файл .env на основе env_example.txt"
    echo ""
    echo "Пример команды:"
    echo "cp env_example.txt .env"
    echo "nano .env  # отредактируйте токены"
    echo ""
    exit 1
fi

# Проверяем наличие токена админ-бота
if ! grep -q "ADMIN_BOT_TOKEN=" .env || grep -q "ADMIN_BOT_TOKEN=your_admin_bot_token" .env; then
    echo "❌ ADMIN_BOT_TOKEN не настроен в .env файле!"
    echo "📝 Получите токен у @BotFather и добавьте в .env:"
    echo "ADMIN_BOT_TOKEN=your_admin_bot_token_here"
    echo ""
    exit 1
fi

# Проверяем наличие ID администраторов
if ! grep -q "ADMIN_IDS=" .env || grep -q "ADMIN_IDS=your_telegram_user_id" .env; then
    echo "❌ ADMIN_IDS не настроен в .env файле!"
    echo "📝 Добавьте ваш Telegram ID в .env:"
    echo "ADMIN_IDS=your_telegram_id"
    echo ""
    echo "💡 Узнать ваш ID можно у @userinfobot"
    echo "⚠️ Для открытого доступа (только тестирование): ADMIN_IDS=all"
    echo ""
    exit 1
fi

# Проверяем на режим открытого доступа
if grep -q "ADMIN_IDS=all" .env; then
    echo "⚠️ ⚠️ ⚠️  ВНИМАНИЕ: РЕЖИМ ОТКРЫТОГО ДОСТУПА! ⚠️ ⚠️ ⚠️"
    echo "Админ-бот будет доступен ВСЕМ пользователям!"
    echo "Используйте только для тестирования!"
    echo ""
    read -p "Продолжить с открытым доступом? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Отменено пользователем"
        exit 1
    fi
fi

# Проверяем наличие базы данных
if [ ! -f "eco_bot.db" ]; then
    echo "⚠️ База данных не найдена!"
    echo "🔄 Сначала запустите основной бот для создания базы:"
    echo "python bot.py"
    echo ""
    read -p "Продолжить запуск админ-бота? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Отменено пользователем"
        exit 1
    fi
fi

# Проверяем виртуальное окружение
if [ -d "venv" ]; then
    echo "🐍 Активация виртуального окружения..."
    source venv/bin/activate
fi

# Проверяем зависимости
echo "📦 Проверка зависимостей..."
python -c "import telegram, dotenv, pytz" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "❌ Не все зависимости установлены!"
    echo "🔧 Установите зависимости:"
    echo "pip install python-telegram-bot python-dotenv pytz"
    echo ""
    exit 1
fi

echo "✅ Все проверки пройдены!"
echo "🚀 Запуск Админ-бота..."
echo ""
echo "💡 Для остановки нажмите Ctrl+C"
echo "📱 Найдите бота в Telegram и отправьте /start"
echo ""

# Запуск с обработкой сигналов
trap 'echo -e "\n🛑 Админ-бот остановлен"; exit 0' SIGINT SIGTERM

python admin_bot.py 