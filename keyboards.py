from telegram import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

class Keyboards:
    @staticmethod
    def main_menu():
        """Главное меню бота с компактным расположением"""
        keyboard = [
            [KeyboardButton("📋 Положение об игре"), KeyboardButton("📖 Инструкция по прохождению")],
            [KeyboardButton("📤 Отправить задание на проверку"), KeyboardButton("🏦 Банк заданий")],
            [KeyboardButton("📊 Мой результат"), KeyboardButton("👤 Изменить профиль")],
            [KeyboardButton("🆘 Обращение в поддержку"), KeyboardButton("🌿 О Движении друзей заповедных островов")]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    @staticmethod
    def participation_type():
        """Клавиатура для выбора типа участия в два ряда"""
        keyboard = [
            [KeyboardButton("👤 Индивидуально"), KeyboardButton("👨‍👩‍👧‍👦 Семьей")]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    
    @staticmethod
    def back_to_menu():
        """Кнопка возврата в главное меню"""
        keyboard = [[KeyboardButton("🏠 Главное меню")]]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    @staticmethod
    def profile_edit():
        """Клавиатура для изменения профиля"""
        keyboard = [
            [KeyboardButton("✏️ Изменить имя"), KeyboardButton("✏️ Изменить фамилию")],
            [KeyboardButton("🏠 Главное меню")]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    
    @staticmethod
    def out_of_context_actions():
        """Инлайн клавиатура для действий при сообщениях без контекста"""
        keyboard = [
            [InlineKeyboardButton("📤 Отправить задание на проверку", callback_data="submit_tasks")],
            [InlineKeyboardButton("🆘 Обращение в поддержку", callback_data="support")],
            [InlineKeyboardButton("📖 Инструкция по прохождению", callback_data="instructions")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def task_selection(tasks):
        """Инлайн клавиатура для выбора задания с компактным расположением"""
        keyboard = []
        
        # Группируем задания по 2 в ряд для более компактного вида
        for i in range(0, len(tasks), 2):
            row = []
            
            # Первое задание в ряду
            task_id, title, _, _ = tasks[i]
            # Сокращаем заголовок если он слишком длинный
            short_title = title[:25] + "..." if len(title) > 25 else title
            row.append(InlineKeyboardButton(
                f"📝 {short_title}", 
                callback_data=f"submit_task_{task_id}"
            ))
            
            # Второе задание в ряду (если есть)
            if i + 1 < len(tasks):
                task_id2, title2, _, _ = tasks[i + 1]
                short_title2 = title2[:25] + "..." if len(title2) > 25 else title2
                row.append(InlineKeyboardButton(
                    f"📝 {short_title2}", 
                    callback_data=f"submit_task_{task_id2}"
                ))
            
            keyboard.append(row)
        
        # Кнопка возврата в отдельном ряду
        keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")])
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def tasks_bank(open_tasks, archived_tasks):
        """Инлайн клавиатура для банка заданий в компактном виде"""
        keyboard = []
        
        # Первый ряд - кнопки категорий
        category_row = []
        if open_tasks:
            category_row.append(InlineKeyboardButton("🟢 Открытые", callback_data="show_open_tasks"))
        
        if archived_tasks:
            category_row.append(InlineKeyboardButton("📁 Архивные", callback_data="show_archived_tasks"))
        
        if category_row:
            keyboard.append(category_row)
        
        # Кнопка возврата
        keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")])
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def task_links(tasks, task_type="open"):
        """Инлайн клавиатура со ссылками на задания в компактном виде"""
        keyboard = []
        
        # Группируем ссылки по 2 в ряд
        for i in range(0, len(tasks), 2):
            row = []
            
            # Первая ссылка в ряду
            task_data = tasks[i]
            task_id, title, description, link = task_data[:4]
            
            if task_type == "open":
                is_open = True
            else:
                is_open = task_data[4] if len(task_data) > 4 else True
            
            if link:
                emoji = "🟢" if is_open else "📁"
                # Сокращаем название для компактности
                short_title = title[:20] + "..." if len(title) > 20 else title
                row.append(InlineKeyboardButton(
                    f"{emoji} {short_title}", 
                    url=link
                ))
            
            # Вторая ссылка в ряду (если есть)
            if i + 1 < len(tasks):
                task_data2 = tasks[i + 1]
                task_id2, title2, description2, link2 = task_data2[:4]
                
                if task_type == "open":
                    is_open2 = True
                else:
                    is_open2 = task_data2[4] if len(task_data2) > 4 else True
                
                if link2:
                    emoji2 = "🟢" if is_open2 else "📁"
                    short_title2 = title2[:20] + "..." if len(title2) > 20 else title2
                    row.append(InlineKeyboardButton(
                        f"{emoji2} {short_title2}", 
                        url=link2
                    ))
            
            if row:  # Добавляем ряд только если в нем есть кнопки
                keyboard.append(row)
        
        # Кнопки навигации в отдельном ряду
        keyboard.append([InlineKeyboardButton("🔙 Назад к банку заданий", callback_data="tasks_bank")])
        return InlineKeyboardMarkup(keyboard) 