import asyncio
import logging
import sys
import os
from collections import defaultdict, deque
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import Message
import google.generativeai as genai

# Token va API kalitlarni to'g'ridan-to'g'ri o'rnatamiz
BOT_TOKEN = "9222915492:AAF9UHj9lvAF9Ke2qFc-AsvYafd6ERtybbY"
GEMINI_API_KEY = "AQ.Ab8RN6JAhRoD4lQFsnVRQBa2FTk2Tf9CI7F2sE5MpBhXb8rznQ"

# Gemini API ni sozlash
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

# Foydalanuvchilar suhbat tarixi uchun xotira
histories = dict(int, deque(maxlen=10))

@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "👋 Assalom alaykum!\n\n"
        "🤖 Men Google Gemini asosida ishlaydigan sun'iy intellekt yordamchingizman.\n"
        "💬 Istalgan savolingizni yozing — javob beraman!\n"
        "🧹 <code>/clear</code> — suhbat tarixini tozalash",
        parse_mode="HTML"
    )

@router.message(Command("clear"))
async def cmd_clear(message: Message):
    user_id = message.from_user.id
    if user_id in histories:
        histories[user_id].clear()
    await message.answer("🧹 Suhbat tarixi tozalandi!")

@router.message(F.text & ~F.text.startswith("/"))
async def handle_ai_chat(message: Message):
    user_id = message.from_user.id
    if user_id not in histories:
        histories[user_id] = deque(maxlen=10)
    
    await message.bot.send_chat_action(message.chat.id, "typing")
    try:
        # Suhbat tarixini jamlab yuborish
        chat = model.start_chat(history=[])
        response = chat.send_message(message.text)
        await message.answer(response.text)
    except Exception as e:
        await message.answer(f"❌ Xatolik yuz berdi: {e}")

async def main():
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
 

