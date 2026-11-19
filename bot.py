"""
Telegram AI bot (aiogram 3.x)

- Matn:  Groq (OpenAI-mos API, CHAT_MODEL, zaxira: CHAT_FALLBACK_MODEL) — ChatGPT kabi javob
- /rasm: Google Nano Banana (Gemini image) orqali rasm yaratish  (GEMINI_API_KEY kerak)
- /video: Google Gemini Omni Flash orqali video yaratish        (GEMINI_API_KEY kerak)
"""
import asyncio
import base64
import html
import logging
import os
import re
import sys
import tempfile
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path

import openai
from aiogram import BaseMiddleware, Bot, Dispatcher, F, Router
from aiogram.enums import ChatAction, ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import BotCommand, BufferedInputFile, Message
from aiogram.utils.chat_action import ChatActionSender
from dotenv import load_dotenv
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types
from openai import AsyncOpenAI

load_dotenv()


# --------------------------------------------------------------------------- #
# Sozlamalar
# --------------------------------------------------------------------------- #
def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "ha"}


def _env_str(name: str, default: str) -> str:
    value = os.getenv(name)
    return value.strip() if value and value.strip() else default


BOT_TOKEN = _env_str("BOT_TOKEN", "")
GROQ_API_KEY = _env_str("GROQ_API_KEY", "")
GROQ_BASE_URL = _env_str("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
GEMINI_API_KEY = _env_str("GEMINI_API_KEY", "")  # ixtiyoriy: faqat /rasm va /video uchun

# Matn (Groq)
CHAT_MODEL = _env_str("CHAT_MODEL", "openai/gpt-oss-120b")
CHAT_FALLBACK_MODEL = _env_str("CHAT_FALLBACK_MODEL", "openai/gpt-oss-20b")
CHAT_REASONING_EFFORT = _env_str("CHAT_REASONING_EFFORT", "low")  # low / medium / high (gpt-oss uchun)
HISTORY_LIMIT = int(_env_str("HISTORY_LIMIT", "10"))

# Rasm (Nano Banana)
IMAGE_MODEL = _env_str("IMAGE_MODEL", "gemini-nano-banana-2.1")
IMAGE_FALLBACK_MODEL = _env_str("IMAGE_FALLBACK_MODEL", "gemini-3.1-flash-image")
IMAGE_ASPECT_RATIO = _env_str("IMAGE_ASPECT_RATIO", "1:1")
IMAGE_SIZE = _env_str("IMAGE_SIZE", "1K")  # 1K / 2K / 4K (katta harf bilan!)

# Video (Gemini Omni Flash)
VIDEO_MODEL = _env_str("VIDEO_MODEL", "gemini-omni-1.1-flash")
VIDEO_ASPECT_RATIO = _env_str("VIDEO_ASPECT_RATIO", "16:9")  # 16:9 yoki 9:16
VIDEO_RESOLUTION = _env_str("VIDEO_RESOLUTION", "720p")
VIDEO_DELIVERY = _env_str("VIDEO_DELIVERY", "uri")  # uri (katta videolar uchun) yoki inline
VIDEO_TIMEOUT = int(_env_str("VIDEO_TIMEOUT", "600"))

# Umumiy
IMPROVE_PROMPT = _env_bool("IMPROVE_PROMPT", True)
MAX_PROMPT_LEN = int(_env_str("MAX_PROMPT_LEN", "1000"))
GEMINI_RETRIES = int(_env_str("GEMINI_RETRIES", "3"))
IMAGE_CONCURRENCY = int(_env_str("IMAGE_CONCURRENCY", "4"))
VIDEO_CONCURRENCY = int(_env_str("VIDEO_CONCURRENCY", "2"))
ALLOWED_USER_IDS = {
    int(x) for x in re.split(r"[,\s]+", os.getenv("ALLOWED_USER_IDS", "")) if x.strip().isdigit()
}

TG_MESSAGE_LIMIT = 4096
TG_CAPTION_LIMIT = 1024
TG_PHOTO_MAX_BYTES = 9 * 1024 * 1024
TG_VIDEO_MAX_BYTES = 49 * 1024 * 1024

SYSTEM_PROMPT = (
    "Sen foydali, aqlli va do'stona yordamchisan. "
    "Foydalanuvchi qaysi tilda yozsa, o'sha tilda to'liq, aniq va tushunarli javob ber."
)

IMAGE_ENHANCER_PROMPT = (
    "You are an expert prompt writer for an AI image generator. Rewrite the user's request "
    "(it may be in Uzbek, Russian, or any language) as ONE detailed English image prompt: "
    "subject, setting, style, composition, lighting, colors, mood. Keep the user's intent "
    "exactly; do not add unrelated objects or any text/captions inside the image unless the "
    "user asked for text (then keep that text verbatim in its original language). "
    "Output only the prompt, max 120 words, no quotes, no explanations."
)

VIDEO_ENHANCER_PROMPT = (
    "You are an expert prompt writer for an AI video generator. Rewrite the user's request "
    "(it may be in Uzbek, Russian, or any language) as ONE detailed English video prompt: "
    "scene, subject action, camera movement, lighting, mood, and a short sound description "
    "(ambient sound or calm music). Keep the user's intent exactly. Add 'No dialogue.' unless "
    "the user asked for speech. Output only the prompt, max 120 words, no quotes, no explanations."
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("bot")


def _require_keys() -> None:
    missing = [
        name for name, value in (("BOT_TOKEN", BOT_TOKEN), ("GROQ_API_KEY", GROQ_API_KEY)) if not value
    ]
    if missing:
        sys.exit(f"Xatolik: .env faylida quyidagilar yetishmayapti: {', '.join(missing)}")
    if not GEMINI_API_KEY:
        logging.getLogger("bot").warning(
            "GEMINI_API_KEY berilmagan: /rasm va /video o'chiq, faqat matnli suhbat ishlaydi."
        )


_require_keys()

# Groq OpenAI-mos API ga ega, shuning uchun openai SDK'ni base_url bilan ishlatamiz
openai_client = AsyncOpenAI(api_key=GROQ_API_KEY, base_url=GROQ_BASE_URL, max_retries=3, timeout=120)
gemini_client = (
    genai.Client(
        api_key=GEMINI_API_KEY,
        http_options=genai_types.HttpOptions(timeout=VIDEO_TIMEOUT * 1000),
    )
    if GEMINI_API_KEY
    else None
)

GEMINI_MISSING_TEXT = (
    "⚠️ Bu funksiya hozircha o'chiq: rasm va video uchun Google (Gemini) API kaliti kerak.\n"
    "Bot egasi .env fayliga GEMINI_API_KEY qo'shishi kerak (aistudio.google.com/apikey)."
)

router = Router()

# --------------------------------------------------------------------------- #
# Holat (xotirada)
# --------------------------------------------------------------------------- #
histories: dict[int, deque] = {}
text_locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
busy_users: set[int] = set()
image_semaphore = asyncio.Semaphore(IMAGE_CONCURRENCY)
video_semaphore = asyncio.Semaphore(VIDEO_CONCURRENCY)


def get_history(user_id: int) -> deque:
    if user_id not in histories:
        if len(histories) >= 5000:  # xotira cheklovi: eng eskisini o'chiramiz
            histories.pop(next(iter(histories)))
        histories[user_id] = deque(maxlen=HISTORY_LIMIT * 2)
    return histories[user_id]


@asynccontextmanager
async def user_task(user_id: int):
    """Bir foydalanuvchi bir vaqtda bitta rasm/video so'rovi yuborishi uchun."""
    if user_id in busy_users:
        raise BusyError
    busy_users.add(user_id)
    try:
        yield
    finally:
        busy_users.discard(user_id)


class BusyError(Exception):
    pass


class MediaBlockedError(RuntimeError):
    """Model rasm/video qaytarmadi (odatda xavfsizlik filtri)."""


# --------------------------------------------------------------------------- #
# Yordamchi funksiyalar
# --------------------------------------------------------------------------- #
def split_text(text: str, limit: int = TG_MESSAGE_LIMIT) -> list[str]:
    """Uzun matnni Telegram limitiga mos bo'laklarga bo'ladi."""
    parts: list[str] = []
    text = text.strip()
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


_CODE_BLOCK = re.compile(r"```[\w+#.-]*\n?(.*?)```", re.S)
_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_BOLD = re.compile(r"\*\*(.+?)\*\*", re.S)
_HEADING = re.compile(r"^#{1,6}\s+(.+)$", re.M)
_BULLET = re.compile(r"^(\s*)[-*]\s+", re.M)
_PLACEHOLDER = re.compile(r"\x00(\d+)\x00")


def md_to_html(text: str) -> str:
    """ChatGPT markdown javobini Telegram HTML'iga o'giradi."""
    stash: list[str] = []

    def keep(value: str) -> str:
        stash.append(value)
        return f"\x00{len(stash) - 1}\x00"

    text = text.replace("\x00", "")
    text = _CODE_BLOCK.sub(lambda m: keep(f"<pre>{html.escape(m.group(1).strip(chr(10)), quote=False)}</pre>"), text)
    text = _INLINE_CODE.sub(lambda m: keep(f"<code>{html.escape(m.group(1), quote=False)}</code>"), text)
    text = html.escape(text, quote=False)
    text = _HEADING.sub(r"<b>\1</b>", text)
    text = _BOLD.sub(r"<b>\1</b>", text)
    text = _BULLET.sub(r"\1• ", text)
    return _PLACEHOLDER.sub(lambda m: stash[int(m.group(1))], text)


async def answer_formatted(message: Message, text: str) -> None:
    """Javobni chiroyli (HTML) formatda yuboradi; xato bo'lsa oddiy matn bilan."""
    for chunk in split_text(text, 3500):
        converted = md_to_html(chunk)
        try:
            if len(converted) > TG_MESSAGE_LIMIT:
                raise ValueError("html too long")
            await message.answer(converted, parse_mode=ParseMode.HTML)
        except (TelegramBadRequest, ValueError):
            await message.answer(chunk, parse_mode=None)


def image_extension(data: bytes) -> str:
    if data.startswith(b"\x89PNG"):
        return "png"
    if data.startswith(b"\xff\xd8"):
        return "jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return "png"


def friendly_error(e: Exception) -> str:
    """Foydalanuvchiga tushunarli xato matni (texnik tafsilotlarsiz)."""
    if isinstance(e, MediaBlockedError):
        return str(e)
    if isinstance(e, (TimeoutError, asyncio.TimeoutError)):
        return "Kutish vaqti tugadi. Birozdan so'ng qayta urinib ko'ring."
    if isinstance(e, openai.AuthenticationError):
        return "Groq API kaliti noto'g'ri. Bot egasi .env faylini tekshirishi kerak."
    if isinstance(e, openai.RateLimitError):
        return "Groq so'rov limiti tugadi. Bir ozdan so'ng qayta urinib ko'ring."
    if isinstance(e, genai_errors.APIError):
        code = getattr(e, "code", None)
        if code == 429:
            return "Google API limiti tugadi. Birozdan so'ng qayta urinib ko'ring."
        if code in (401, 403):
            return "Gemini API kaliti noto'g'ri yoki bu model uchun ruxsat (billing) yoqilmagan."
        if code == 404:
            return "Gemini modeli topilmadi. Bot egasi .env dagi model nomini tekshirishi kerak."
        if code == 400:
            return "So'rov qabul qilinmadi. Tavsifni o'zgartirib qayta urinib ko'ring."
        return "Google serverida vaqtinchalik xatolik. Birozdan so'ng urinib ko'ring."
    return "Kutilmagan xatolik yuz berdi. Birozdan so'ng qayta urinib ko'ring."


# --------------------------------------------------------------------------- #
# Groq (OpenAI-mos API): matn
# --------------------------------------------------------------------------- #
_chat_models: list[str] = [m for m in dict.fromkeys([CHAT_MODEL, CHAT_FALLBACK_MODEL]) if m]
_MODEL_ERRORS = (openai.NotFoundError, openai.BadRequestError, openai.PermissionDeniedError)


async def chat_completion(messages: list[dict]) -> str:
    """Asosiy model ishlamasa, zaxira modelga o'tadi (model o'chirilgan bo'lishi mumkin)."""
    last_exc: Exception | None = None
    for model in list(_chat_models):
        kwargs: dict = {"model": model, "messages": messages}
        if CHAT_REASONING_EFFORT and model.startswith("openai/gpt-oss"):
            kwargs["reasoning_effort"] = CHAT_REASONING_EFFORT
        try:
            response = await openai_client.chat.completions.create(**kwargs)
        except _MODEL_ERRORS as e:
            log.warning("Model '%s' ishlamadi (%s), keyingisini sinayman", model, type(e).__name__)
            last_exc = e
            continue
        if _chat_models[0] != model:  # ishlagan modelni oldinga olamiz
            _chat_models.remove(model)
            _chat_models.insert(0, model)
        return (response.choices[0].message.content or "").strip()
    assert last_exc is not None
    raise last_exc


async def enhance_prompt(prompt: str, kind: str) -> str:
    """Tavsifni (o'zbekcha ham bo'lishi mumkin) batafsil inglizcha promptga aylantiradi."""
    if not IMPROVE_PROMPT:
        return prompt
    system = IMAGE_ENHANCER_PROMPT if kind == "image" else VIDEO_ENHANCER_PROMPT
    try:
        improved = await chat_completion(
            [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
        )
        improved = improved.strip().strip('"').strip()
        return improved[:1200] if improved else prompt
    except Exception:
        log.exception("Promptni yaxshilab bo'lmadi, asl matn ishlatiladi")
        return prompt


# --------------------------------------------------------------------------- #
# Google Gemini: rasm (Nano Banana) va video (Omni Flash)
# --------------------------------------------------------------------------- #
_RETRYABLE_CODES = {429, 500, 502, 503, 504}


def find_media(interaction, kind: str):
    """Javobdan rasm/video blokini topadi (convenience property yoki steps orqali)."""

    def usable(block) -> bool:
        return block is not None and bool(getattr(block, "data", None) or getattr(block, "uri", None))

    block = getattr(interaction, f"output_{kind}", None)
    if usable(block):
        return block
    for step in reversed(getattr(interaction, "steps", None) or []):
        if getattr(step, "type", None) != "model_output":
            continue
        for item in reversed(getattr(step, "content", None) or []):
            if getattr(item, "type", None) == kind and usable(item):
                return item
    return None


def _blocked_error(interaction, kind: str) -> MediaBlockedError:
    label = "Rasm" if kind == "image" else "Video"
    reason = (getattr(interaction, "output_text", None) or "").strip()
    msg = f"{label} yaratilmadi: model so'rovni bajarmadi (xavfsizlik filtri bo'lishi mumkin). Tavsifni o'zgartirib ko'ring."
    if reason:
        msg += f"\n\nModel javobi: {reason[:300]}"
    return MediaBlockedError(msg)


def _image_sync(prompt: str, model: str) -> bytes:
    interaction = gemini_client.interactions.create(
        model=model,
        input=prompt,
        response_format={
            "type": "image",
            "aspect_ratio": IMAGE_ASPECT_RATIO,
            "image_size": IMAGE_SIZE,
        },
    )
    block = find_media(interaction, "image")
    if block is None:
        raise _blocked_error(interaction, "image")
    data = getattr(block, "data", None)
    if data:
        return base64.b64decode(data)
    raise MediaBlockedError("Rasm ma'lumoti olinmadi. Qayta urinib ko'ring.")


def _download_gemini_file(uri: str) -> bytes:
    match = re.search(r"files/([A-Za-z0-9_\-]+)", uri)
    if match:
        name = f"files/{match.group(1)}"
        deadline = time.monotonic() + VIDEO_TIMEOUT
        while True:
            info = gemini_client.files.get(name=name)
            state_obj = getattr(info, "state", None)
            state = str(getattr(state_obj, "name", state_obj) or "").upper()
            if state.endswith("ACTIVE"):
                break
            if state.endswith("FAILED"):
                raise MediaBlockedError("Video yaratilmadi (server xatosi). Qayta urinib ko'ring.")
            if time.monotonic() > deadline:
                raise TimeoutError
            time.sleep(5)

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "video.mp4"
        try:
            gemini_client.files.download(file=uri, destination=str(path))
            return path.read_bytes()
        except TypeError:  # eski SDK: destination qo'llab-quvvatlanmaydi, bytes qaytaradi
            data = gemini_client.files.download(file=uri)
            if isinstance(data, (bytes, bytearray)):
                return bytes(data)
            raise


def _video_sync(prompt: str, model: str) -> bytes:
    response_format = {
        "type": "video",
        "aspect_ratio": VIDEO_ASPECT_RATIO,
        "resolution": VIDEO_RESOLUTION,
    }
    if VIDEO_DELIVERY == "uri":
        response_format["delivery"] = "uri"
    interaction = gemini_client.interactions.create(
        model=model,
        input=prompt,
        response_format=response_format,
    )
    block = find_media(interaction, "video")
    if block is None:
        raise _blocked_error(interaction, "video")
    data = getattr(block, "data", None)
    if data:
        return base64.b64decode(data)
    return _download_gemini_file(block.uri)


async def _gemini_run(fn, models: list[str]) -> tuple[bytes, str]:
    """Qayta urinish (429/5xx) va zaxira modelga o'tish bilan Gemini chaqiruvi."""
    models = [m for m in dict.fromkeys(models) if m]
    last_exc: Exception | None = None
    for index, model in enumerate(models):
        is_last_model = index == len(models) - 1
        for attempt in range(GEMINI_RETRIES):
            try:
                return await asyncio.to_thread(fn, model), model
            except genai_errors.APIError as e:
                last_exc = e
                code = getattr(e, "code", None)
                log.warning("Gemini '%s' xato kodi=%s (urinish %d)", model, code, attempt + 1)
                if code in _RETRYABLE_CODES and attempt < GEMINI_RETRIES - 1:
                    await asyncio.sleep(3 * (attempt + 1))
                    continue
                if not is_last_model:
                    break
                raise
    assert last_exc is not None
    raise last_exc


async def generate_image(prompt: str) -> tuple[bytes, str]:
    prompt = await enhance_prompt(prompt, "image")
    async with image_semaphore:
        return await _gemini_run(lambda model: _image_sync(prompt, model), [IMAGE_MODEL, IMAGE_FALLBACK_MODEL])


async def generate_video(prompt: str) -> tuple[bytes, str]:
    prompt = await enhance_prompt(prompt, "video")
    async with video_semaphore:
        return await _gemini_run(lambda model: _video_sync(prompt, model), [VIDEO_MODEL])


# --------------------------------------------------------------------------- #
# Ruxsat (ixtiyoriy): ALLOWED_USER_IDS berilsa, faqat ular foydalana oladi
# --------------------------------------------------------------------------- #
class AccessMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = getattr(event, "from_user", None)
        if user is not None and user.id in ALLOWED_USER_IDS:
            return await handler(event, data)
        await event.answer("⛔ Sizga bu botdan foydalanishga ruxsat berilmagan.")
        return None


if ALLOWED_USER_IDS:
    router.message.outer_middleware(AccessMiddleware())


# --------------------------------------------------------------------------- #
# Buyruqlar
# --------------------------------------------------------------------------- #
@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        "👋 Salom! Men sun'iy intellekt botman.\n\n"
        "💬 Menga istalgan savol yozing — ChatGPT kabi javob beraman.\n"
        "🎨 /rasm [tavsif] — rasm yaratish (Nano Banana)\n"
        "🎬 /video [tavsif] — video yaratish\n"
        "🧹 /clear — suhbat tarixini tozalash\n\n"
        "Masalan: /rasm kosmosda uchayotgan mushuk"
    )


@router.message(Command("id"))
async def cmd_id(message: Message) -> None:
    await message.answer(f"Sizning Telegram ID: {message.from_user.id}")


@router.message(Command("clear"))
async def cmd_clear(message: Message) -> None:
    histories.pop(message.from_user.id, None)
    await message.answer("🧹 Suhbat tarixi tozalandi.")


def _check_prompt(prompt: str, example: str) -> str | None:
    if not prompt:
        return f"❗ Tavsifni kiriting.\nMasalan: {example}"
    if len(prompt) > MAX_PROMPT_LEN:
        return f"❗ Tavsif juda uzun ({len(prompt)} belgi). Eng ko'pi bilan {MAX_PROMPT_LEN} belgi."
    return None


async def _safe_delete(message: Message) -> None:
    try:
        await message.delete()
    except Exception:
        pass


@router.message(Command("rasm"))
async def cmd_image(message: Message, command: CommandObject) -> None:
    prompt = (command.args or "").strip()
    if gemini_client is None:
        await message.answer(GEMINI_MISSING_TEXT)
        return
    problem = _check_prompt(prompt, "/rasm tog'lar orasidagi go'zal ko'l")
    if problem:
        await message.answer(problem)
        return

    try:
        async with user_task(message.from_user.id):
            status = await message.answer("🎨 Rasm yaratilmoqda, biroz kuting...")
            try:
                async with ChatActionSender(
                    bot=message.bot, chat_id=message.chat.id, action=ChatAction.UPLOAD_PHOTO
                ):
                    image_bytes, used_model = await generate_image(prompt)
                log.info("Rasm tayyor (model=%s, %d bayt)", used_model, len(image_bytes))
                file = BufferedInputFile(image_bytes, filename=f"image.{image_extension(image_bytes)}")
                caption = f"🎨 {prompt}"[:TG_CAPTION_LIMIT]
                if len(image_bytes) > TG_PHOTO_MAX_BYTES:
                    await message.answer_document(document=file, caption=caption)
                else:
                    await message.answer_photo(photo=file, caption=caption)
            except Exception as e:
                log.exception("Rasm yaratishda xatolik")
                await message.answer(f"❌ {friendly_error(e)}")
            finally:
                await _safe_delete(status)
    except BusyError:
        await message.answer("⏳ Oldingi so'rovingiz hali bajarilmoqda. Tugashini kuting.")


@router.message(Command("video"))
async def cmd_video(message: Message, command: CommandObject) -> None:
    prompt = (command.args or "").strip()
    if gemini_client is None:
        await message.answer(GEMINI_MISSING_TEXT)
        return
    problem = _check_prompt(prompt, "/video dengiz bo'yida to'lqinlar")
    if problem:
        await message.answer(problem)
        return

    try:
        async with user_task(message.from_user.id):
            status = await message.answer(
                "🎬 Video yaratilmoqda. Bu 1–3 daqiqa olishi mumkin, iltimos kuting..."
            )
            try:
                async with ChatActionSender(
                    bot=message.bot, chat_id=message.chat.id, action=ChatAction.UPLOAD_VIDEO
                ):
                    video_bytes, used_model = await generate_video(prompt)
                log.info("Video tayyor (model=%s, %d bayt)", used_model, len(video_bytes))
                if len(video_bytes) > TG_VIDEO_MAX_BYTES:
                    await message.answer("❌ Video Telegram limitidan (50 MB) katta chiqdi. Qisqaroq tavsif bering.")
                else:
                    await message.answer_video(
                        video=BufferedInputFile(video_bytes, filename="video.mp4"),
                        caption=f"🎬 {prompt}"[:TG_CAPTION_LIMIT],
                        supports_streaming=True,
                    )
            except Exception as e:
                log.exception("Video yaratishda xatolik")
                await message.answer(f"❌ {friendly_error(e)}")
            finally:
                await _safe_delete(status)
    except BusyError:
        await message.answer("⏳ Oldingi so'rovingiz hali bajarilmoqda. Tugashini kuting.")


# --------------------------------------------------------------------------- #
# Oddiy matn — ChatGPT kabi suhbat
# --------------------------------------------------------------------------- #
@router.message(F.text, ~F.text.startswith("/"))
async def chat_handler(message: Message) -> None:
    user_id = message.from_user.id
    async with text_locks[user_id]:
        history = get_history(user_id)
        history.append({"role": "user", "content": message.text})
        messages = [{"role": "system", "content": SYSTEM_PROMPT}, *history]
        try:
            async with ChatActionSender.typing(bot=message.bot, chat_id=message.chat.id):
                answer = await chat_completion(messages)
            if not answer:
                answer = "Kechirasiz, javob olinmadi. Qayta urinib ko'ring."
            history.append({"role": "assistant", "content": answer})
            await answer_formatted(message, answer)
        except Exception as e:
            log.exception("Matnli javobda xatolik")
            if history and history[-1]["role"] == "user":
                history.pop()
            await message.answer(f"❌ {friendly_error(e)}")


@router.message()
async def fallback_handler(message: Message) -> None:
    await message.answer("📝 Iltimos, matn yuboring yoki /rasm, /video buyruqlaridan foydalaning.")


# --------------------------------------------------------------------------- #
# Ishga tushirish
# --------------------------------------------------------------------------- #
async def main() -> None:
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Botni boshlash"),
            BotCommand(command="rasm", description="Rasm yaratish: /rasm [tavsif]"),
            BotCommand(command="video", description="Video yaratish: /video [tavsif]"),
            BotCommand(command="clear", description="Suhbat tarixini tozalash"),
        ]
    )
    me = await bot.get_me()
    log.info(
        "Bot ishga tushdi: @%s | matn=%s | rasm=%s | video=%s",
        me.username,
        _chat_models,
        IMAGE_MODEL if gemini_client else "o'chiq",
        VIDEO_MODEL if gemini_client else "o'chiq",
    )
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("Bot to'xtatildi")
