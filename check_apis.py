"""
Kalitlar va modellarni HAQIQIY so'rovlar bilan tekshiradi.

Ishlatish:
    python check_apis.py            # Telegram + matn + rasm
    python check_apis.py --video    # + video (pullik bo'lishi mumkin, 1-3 daqiqa)
"""
import asyncio
import sys
import time
from pathlib import Path

import bot  # .env ni o'qiydi va klientlarni yaratadi
from aiogram import Bot

OUT = Path("check_output")
OUT.mkdir(exist_ok=True)


async def step(name: str, coro):
    started = time.monotonic()
    try:
        result = await coro
        print(f"✅ {name} — OK ({time.monotonic() - started:.1f}s)")
        return result
    except Exception as e:
        print(f"❌ {name} — XATO: {type(e).__name__}: {str(e)[:300]}")
        return None


async def main() -> None:
    async def telegram():
        tg = Bot(token=bot.BOT_TOKEN)
        try:
            me = await tg.get_me()
            return f"@{me.username}"
        finally:
            await tg.session.close()

    username = await step("Telegram token", telegram())
    if username:
        print(f"   Bot: {username}")

    text = await step(
        "Matn (Groq)",
        bot.chat_completion([{"role": "user", "content": "Salom! Bir jumlada o'zingni tanishtir."}]),
    )
    if text:
        print(f"   Ishlagan model: {bot._chat_models[0]}")
        print(f"   Javob: {text[:200]}")

    if bot.gemini_client is None:
        print("⏭  Rasm/video tekshirilmadi: GEMINI_API_KEY berilmagan (faqat matn ishlaydi).")
        return

    image = await step(
        "Rasm (Nano Banana)",
        bot.generate_image("quyoshli bog'da o'tirgan oq mushuk, realistik foto"),
    )
    if image:
        data, model = image
        path = OUT / f"test_image.{bot.image_extension(data)}"
        path.write_bytes(data)
        print(f"   Model: {model} | {len(data) // 1024} KB | saqlandi: {path}")

    if "--video" in sys.argv:
        video = await step(
            "Video (Gemini Omni Flash)",
            bot.generate_video("tog' ustida chiqayotgan quyosh, sokin musiqa"),
        )
        if video:
            data, model = video
            path = OUT / "test_video.mp4"
            path.write_bytes(data)
            print(f"   Model: {model} | {len(data) // 1024} KB | saqlandi: {path}")
    else:
        print("⏭  Video tekshirilmadi (tekshirish uchun: python check_apis.py --video)")


if __name__ == "__main__":
    asyncio.run(main())
