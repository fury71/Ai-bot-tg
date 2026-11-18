import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import Message
from groq import Groq

# Token va Groq API kalit
BOT_TOKEN = "9222915492:AAF9UHj9lvAF9Ke2qFc-AsvYafd6ERtybbY"
GROQ_API_KEY = "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"

client = Groq(api_key=GROQ_API_KEY)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "👋 Assalom alaykum!\n\n"
        "🤖 Men Llama 3 asosida ishlaydigan sun'iy intellekt yordamchingizman.\n"
        "💬 Istalgan savolingizni yozing — darhol javob beraman!",
        parse_mode="HTML"
    )

@router.message(F.text & ~F.text.startswith("/"))
async def handle_ai_chat(message: Message):
    await message.bot.send_chat_action(message.chat.id, "typing")
    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "user", "content": message.text}
            ],
            temperature=0.7,
        )
        answer = completion.choices[0].message.content
        await message.answer(answer)
    except Exception as e:
        await message.answer(f"❌ Xatolik yuz berdi: {e}")

async def main():
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

