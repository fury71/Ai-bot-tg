import asyncio
import logging
import os
import sys
from collections import defaultdict, deque

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ChatAction
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import BufferedInputFile, Message
from aiogram.utils.chat_action import ChatActionSender
from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-4o-mini")
VIDEO_MODEL = os.getenv("VIDEO_MODEL", "sora-2")
VIDEO_SECONDS = os.getenv("VIDEO_SECONDS", "4")
VIDEO_SIZE = os.getenv("VIDEO_SIZE", "1280x720")
VIDEO_TIMEOUT = int(os.getenv("VIDEO_TIMEOUT", "600"))
HISTORY_LIMIT = int(os.getenv("HISTORY_LIMIT", "10"))

SYSTEM_PROMPT = (
    "Sen foydali, aqlli va do'stona yordamchisan. "
    "Foydalanuvchi qaysi tilda yozsa, o'sha tilda to'liq va tushunarli javob ber."
)

TG_MESSAGE_LIMIT = 4096
TG_CAPTION_LIMIT = 1024

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("bot")

if not BOT_TOKEN or not OPENAI_API_KEY:
    sys.exit("Xatolik: .env faylida BOT_TOKEN va OPENAI_API_KEY ko'rsatilishi shart.")

client = AsyncOpenAI(api_key=OPENAI_API_KEY)
router = Router()

# Har bir foydalanuvchi uchun oxirgi xabarlar tarixi (xotirada)
histories: dict[int, deque] = defaultdict(lambda: deque(maxlen=HISTORY_LIMIT * 2))


def split_text(text: str, limit: int = TG_MESSAGE_LIMIT) -> list[str]:
    """Uzun matnni Telegram limitiga mos bo'laklarga bo'ladi."""
    parts: list[str] = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = text.rfind(" ", 0, limit)
        if cut < limit // 2:
            cut = limit
        parts.append(text[:cut].strip())
        text = text[cut:].strip()
    if text:
        parts.append(text)
    return parts


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        "👋 Salom! Men sun'iy intellekt botman.\n\n"
        "💬 Menga istalgan savol yozing — ChatGPT kabi javob beraman.\n"
        "🎨 /rasm [tavsif] — rasm yaratish (DALL-E 3)\n"
        "🎬 /video [tavsif] — video yaratish\n"
        "🧹 /clear — suhbat tarixini tozalash\n\n"
        "Masalan: /rasm kosmosda uchayotgan mushuk"
    )


@router.message(Command("clear"))
async def cmd_clear(message: Message) -> None:
    histories.pop(message.from_user.id, None)
    await message.answer("🧹 Suhbat tarixi tozalandi.")


@router.message(Command("rasm"))
async def cmd_image(message: Message, command: CommandObject) -> None:
    prompt = (command.args or "").strip()
    if not prompt:
        await message.answer(
            "❗ Rasm tavsifini kiriting.\nMasalan: /rasm tog'lar orasidagi go'zal ko'l"
        )
        return

    status = await message.answer("🎨 Rasm yaratilmoqda, biroz kuting...")
    try:
        async with ChatActionSender(
            bot=message.bot, chat_id=message.chat.id, action=ChatAction.UPLOAD_PHOTO
        ):
            response = await client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                size="1024x1024",
                quality="standard",
                n=1,
            )
        image_url = response.data[0].url
        await message.answer_photo(
            photo=image_url,
            caption=f"🎨 {prompt}"[:TG_CAPTION_LIMIT],
        )
    except Exception as e:
        log.exception("Rasm yaratishda xatolik")
        await message.answer(f"❌ Rasm yaratib bo'lmadi:\n{_short_error(e)}")
    finally:
        await _safe_delete(status)


@router.message(Command("video"))
async def cmd_video(message: Message, command: CommandObject) -> None:
    prompt = (command.args or "").strip()
    if not prompt:
        await message.answer(
            "❗ Video tavsifini kiriting.\nMasalan: /video dengiz bo'yida to'lqinlar"
        )
        return

    status = await message.answer(
        "🎬 Video yaratilmoqda. Bu bir necha daqiqa olishi mumkin, iltimos kuting..."
    )
    try:
        async with ChatActionSender(
            bot=message.bot, chat_id=message.chat.id, action=ChatAction.UPLOAD_VIDEO
        ):
            video_bytes = await generate_video(prompt)
        await message.answer_video(
            video=BufferedInputFile(video_bytes, filename="video.mp4"),
            caption=f"🎬 {prompt}"[:TG_CAPTION_LIMIT],
            supports_streaming=True,
        )
    except TimeoutError:
        await message.answer("⏳ Video yaratish juda uzoq davom etdi. Keyinroq urinib ko'ring.")
    except Exception as e:
        log.exception("Video yaratishda xatolik")
        await message.answer(
            "❌ Video yaratib bo'lmadi.\n"
            "Sabab: video modeliga kirish huquqi yo'q yoki so'rov rad etildi.\n"
            f"Tafsilot: {_short_error(e)}"
        )
    finally:
        await _safe_delete(status)


async def generate_video(prompt: str) -> bytes:
    """OpenAI video API (Sora) orqali video yaratadi va bytes qaytaradi."""
    video = await client.videos.create(
        model=VIDEO_MODEL,
        prompt=prompt,
        seconds=VIDEO_SECONDS,
        size=VIDEO_SIZE,
    )

    waited = 0
    while video.status in ("queued", "in_progress"):
        if waited >= VIDEO_TIMEOUT:
            raise TimeoutError
        await asyncio.sleep(5)
        waited += 5
        video = await client.videos.retrieve(video.id)

    if video.status != "completed":
        error = getattr(video, "error", None)
        raise RuntimeError(getattr(error, "message", None) or f"Holat: {video.status}")

    content = await client.videos.download_content(video.id, variant="video")
    return await content.aread()


@router.message(F.text, ~F.text.startswith("/"))
async def chat_handler(message: Message) -> None:
    user_id = message.from_user.id
    history = histories[user_id]
    history.append({"role": "user", "content": message.text})

    messages = [{"role": "system", "content": SYSTEM_PROMPT}, *history]

    try:
        async with ChatActionSender.typing(bot=message.bot, chat_id=message.chat.id):
            response = await client.chat.completions.create(
                model=CHAT_MODEL,
                messages=messages,
                temperature=0.7,
            )
        answer = (response.choices[0].message.content or "").strip()
        if not answer:
            answer = "Kechirasiz, javob olinmadi. Qayta urinib ko'ring."
        history.append({"role": "assistant", "content": answer})

        for part in split_text(answer):
            await message.answer(part, parse_mode=None)
    except Exception as e:
        log.exception("Matnli javobda xatolik")
        if history and history[-1]["role"] == "user":
            history.pop()
        await message.answer(f"❌ Xatolik yuz berdi:\n{_short_error(e)}")


@router.message()
async def fallback_handler(message: Message) -> None:
    await message.answer("📝 Iltimos, matn yuboring yoki /rasm, /video buyruqlaridan foydalaning.")


async def _safe_delete(message: Message) -> None:
    try:
        await message.delete()
    except Exception:
        pass


def _short_error(e: Exception) -> str:
    return str(e)[:300]


async def main() -> None:
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=None))
    dp = Dispatcher()
    dp.include_router(router)

    await bot.delete_webhook(drop_pending_updates=True)
    log.info("Bot ishga tushdi")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("Bot to'xtatildi")
