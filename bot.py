import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import Message
from duckduckgo_search import DDGS

BOT_TOKEN = "9222915492:AAF9UHj9lvAF9Ke2qFc-AsvYafd6ERtybbY"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "👋 Assalom alaykum!\n\n"
        "🤖 Men bepul sun'iy intellekt yordamchingizman.\n"
        "💬 Istalgan savolingizni yozing — javob beraman!",
        parse_mode="HTML"
    )

@router.message(F.text & ~F.text.startswith("/"))
async def handle_ai_chat(message: Message):
    await message.bot.send_chat_action(message.chat.id, "typing")
    try:
        # DuckDuckGo orqali sun'iy intellektga so'rov yuborish (hech qanday kalit kerak emas)
        with DDGS() as ddgs:
            results = list(ddgs.chat(message.text, model="gpt-4o-mini"))
            if results and isinstance(results, list):
                answer = results[0].get("message", "Javob topilmadi.")
            else:
                # Agar chat ishlamasa, oddiy qidiruv natijasidan olamiz
                search_res = list(ddgs.text(message.text, max_results=1))
                answer = search_res[0].get("body", "Kechirasiz, javob berolmadi.") if search_res else "Javob topilmadi."
                
        await message.answer(answer)
    except Exception as e:
        # Fallback: agar chat ishlamasa oddiy matnli javob qaytarish
        try:
            with DDGS() as ddgs:
                r = list(ddgs.text(message.text, max_results=1))
                if r:
                    await message.answer(r[0].get("body"))
                else:
                    await message.answer(f"❌ Xatolik yuz berdi: {e}")
        except Exception as err:
            await message.answer(f"❌ Xatolik yuz berdi: {err}")

async def main():
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
