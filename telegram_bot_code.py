
import telebot
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import requests

# Настройки
TOKEN = "8176657408:AAEyzumbAOjwvXE_31hO9g9T24pWjUqBmG4"
bot = telebot.TeleBot(TOKEN)
LOCATIONIQ_API_KEY = "pk.a7b3c4092bec6c741fe1a9efcbfb5292"

# Google Sheets
SHEET_NAME = "Workingtime"
CREDENTIALS_FILE = "workingtimejapil-a973e4ee8865.json"
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
credentials = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
client = gspread.authorize(credentials)
sheet = client.open(SHEET_NAME).sheet1

# Регистрация пользователей
@bot.message_handler(commands=["start"])
def start_handler(message):
    bot.send_message(message.chat.id, "Добро пожаловать! Давайте начнем регистрацию. Напишите вашу фамилию:")
    bot.register_next_step_handler(message, get_last_name)

def get_last_name(message):
    chat_id = message.chat.id
    last_name = message.text
    bot.send_message(chat_id, "Введите ваше имя:")
    bot.register_next_step_handler(message, get_first_name, last_name)

def get_first_name(message, last_name):
    chat_id = message.chat.id
    first_name = message.text
    bot.send_message(chat_id, "Введите ваше отчество:")
    bot.register_next_step_handler(message, get_middle_name, last_name, first_name)

def get_middle_name(message, last_name, first_name):
    chat_id = message.chat.id
    middle_name = message.text
    bot.send_message(chat_id, "Введите ваш номер телефона:")
    bot.register_next_step_handler(message, complete_registration, last_name, first_name, middle_name)

def complete_registration(message, last_name, first_name, middle_name):
    chat_id = message.chat.id
    phone = message.text
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Запись в Google Sheets
    sheet.append_row([
        chat_id, last_name, first_name, middle_name, phone, "not_working", "", "", 0
    ])

    bot.send_message(chat_id, f"Регистрация завершена! Добро пожаловать, {first_name}!")
    show_main_menu(chat_id)

# Главное меню
def show_main_menu(chat_id):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    user = get_user_from_sheet(chat_id)
    if not user:
        bot.send_message(chat_id, "Вы не зарегистрированы. Начните с команды /start.")
        return

    if user["status"] == "not_working":
        markup.add("Приход на работу", "Статус")
    else:
        markup.add("Уход с работы", "Статус")
    bot.send_message(chat_id, "Выберите действие:", reply_markup=markup)

# Получение данных из Google Sheets
def get_user_from_sheet(chat_id):
    users = sheet.get_all_records()
    for user in users:
        if str(user["chat_id"]) == str(chat_id):
            return user
    return None

# Поиск строки пользователя
def find_row_index(chat_id):
    data = sheet.get_all_records()
    for i, row in enumerate(data):
        if str(row["chat_id"]) == str(chat_id):
            return i + 2  # Индекс +2 из-за заголовков
    return None

# Обработка прихода и ухода
@bot.message_handler(func=lambda m: m.text in ["Приход на работу", "Уход с работы"])
def main_menu_handler(message):
    chat_id = message.chat.id
    action = message.text
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(telebot.types.KeyboardButton("Отправить геоданные", request_location=True))
    bot.send_message(chat_id, "Нажмите 'Отправить геоданные', чтобы зафиксировать время.", reply_markup=markup)

@bot.message_handler(content_types=["location"])
def handle_location(message):
    chat_id = message.chat.id
    user = get_user_from_sheet(chat_id)
    if not user:
        bot.send_message(chat_id, "Вы не зарегистрированы. Начните с команды /start.")
        return

    row_index = find_row_index(chat_id)
    action = sheet.cell(row_index, 6).value  # Текущий статус
    lat, lon = message.location.latitude, message.location.longitude
    location = get_address(lat, lon)
    now = datetime.now()

    if action == "not_working":
        sheet.update_cell(row_index, 7, now.isoformat())  # Фиксируем время прихода
        sheet.update_cell(row_index, 8, location)  # Сохраняем адрес
        sheet.update_cell(row_index, 6, "working")  # Обновляем статус
        bot.send_message(chat_id, f"Приход зафиксирован! Место: {location}. Время: {now.strftime('%H:%M:%S')}. Отличного дня!")
    elif action == "working":
        check_in_time = user["today_check_in"]
        try:
            check_in_time = datetime.fromisoformat(check_in_time)
        except ValueError:
            bot.send_message(chat_id, "Ошибка: некорректное значение времени прихода.")
            return

        worked_time = now - check_in_time
        total_hours = float(user["monthly_hours"]) + worked_time.total_seconds() / 3600
        sheet.update_cell(row_index, 7, "")  # Очищаем поле today_check_in
        sheet.update_cell(row_index, 6, "not_working")  # Обновляем статус
        sheet.update_cell(row_index, 9, total_hours)  # Обновляем часы
        bot.send_message(chat_id, f"Уход зафиксирован! Сегодня вы отработали {worked_time}. Отличная работа!")
    show_main_menu(chat_id)

# Получение адреса по координатам
def get_address(lat, lon):
    url = f"https://eu1.locationiq.com/v1/reverse.php?key={LOCATIONIQ_API_KEY}&lat={lat}&lon={lon}&format=json"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        return data.get("display_name", "Адрес не найден")
    return "Ошибка получения адреса"

# Обработка статуса
@bot.message_handler(func=lambda m: m.text == "Статус")
def handle_status(message):
    chat_id = message.chat.id
    user = get_user_from_sheet(chat_id)
    if not user:
        bot.send_message(chat_id, "Вы не зарегистрированы.")
        return

    now = datetime.now()
    today_hours = timedelta()
    if user["today_check_in"]:
        try:
            today_check_in = datetime.fromisoformat(user["today_check_in"])
            today_hours = now - today_check_in
        except ValueError:
            bot.send_message(chat_id, "Ошибка в данных времени прихода. Пожалуйста, уточните.")
            return

    monthly_hours = float(user["monthly_hours"])
    monthly_hours += today_hours.total_seconds() / 3600
    bot.send_message(
        chat_id,
        f"Сегодня вы отработали: {str(today_hours).split('.')[0]}"
        f"За месяц: {monthly_hours:.2f} часов.Спасибо за ваш вклад в компанию!")

# Запуск бота
bot.polling(none_stop=True)
