import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import Message
from google import genai

# Token va API kalitlar
BOT_TOKEN = "9222915492:AAF9UHj9lvAF9Ke2qFc-AsvYafd6ERtybbY"
GEMINI_API_KEY = "AQ.Ab8RN6JAhRoD4lQFsnVRQBa2FTk2Tf9CI7F2sE5MpBhXb8rznQ"

# Yangi Google GenAI mijozi
client = genai.Client(api_key=GEMINI_API_KEY)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "👋 Assalom alaykum!\n\n"
        "🤖 Men Google Gemini asosida ishlaydigan sun'iy intellekt yordamchingizman.\n"
        "💬 Istalgan savolingizni yozing — javob beraman!",
        parse_mode="HTML"
    )

@router.message(F.text & ~F.text.startswith("/"))
async def handle_ai_chat(message: Message):
    await message.bot.send_chat_action(message.chat.id, "typing")
    try:
        # Yangi formatdagi chaqiruv
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=message.text,
        )
        await message.answer(response.text)
    except Exception as e:
        await message.answer(f"❌ Xatolik yuz berdi: {e}")

async def main():
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
