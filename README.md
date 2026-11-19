# Telegram AI Bot (aiogram 3 + Groq + Gemini)

| Funksiya | Qanday ishlaydi | Model |
|---|---|---|
| 💬 Matn | Oddiy xabar yozing — ChatGPT kabi javob, suhbat xotirasi bilan | Groq `openai/gpt-oss-120b` (zaxira: `openai/gpt-oss-20b`) |
| 🎨 `/rasm [tavsif]` | Rasm yaratadi | Google **Nano Banana 2.1** (`gemini-nano-banana-2.1`) |
| 🎬 `/video [tavsif]` | Ovozli video yaratadi | Google **Gemini Omni Flash** (`gemini-omni-1.1-flash`) |
| 🧹 `/clear` | Suhbat tarixini tozalaydi | — |

O'zbekcha tavsif avtomatik ravishda batafsil inglizcha promptga aylantirib yuboriladi (`IMPROVE_PROMPT=true`) — natija sifatli chiqadi.

## O'rnatish

Python 3.10+ kerak.

```bash
git clone <repo-url> && cd telegram-ai-bot
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # kalitlarni kiriting
python check_apis.py               # kalit va modellarni tekshirish
python bot.py
```

## Kalitlar
- `BOT_TOKEN` — Telegram `@BotFather`
- `GROQ_API_KEY` — https://console.groq.com/keys (matn uchun)
- `GEMINI_API_KEY` — https://aistudio.google.com/apikey (ixtiyoriy, **faqat `/rasm` va `/video` uchun**).  
  Groq rasm va video yarata olmaydi, shuning uchun bu kalitsiz bot faqat matn bilan ishlaydi.
  Rasm/video modellari uchun Google hisobida billing (pullik tarif) yoqilgan bo'lishi kerak bo'lishi mumkin.

## Tekshirish
`python check_apis.py` — Telegram tokenni, Groq matnni va (kalit bo'lsa) rasmni haqiqiy so'rov bilan tekshiradi.  
`python check_apis.py --video` — videoni ham tekshiradi (pullik, 1–3 daqiqa).  
Natijalar `check_output/` papkasiga saqlanadi.

## Docker
```bash
docker build -t ai-bot .
docker run -d --env-file .env --name ai-bot ai-bot
```

## Muhim eslatmalar
- **Sora API o'chirilgan** (2026-09-24), shuning uchun video Google modeli orqali ishlaydi.
- Groq'da `llama-3.3-70b-versatile` bepul/developer tarifdan o'chirilgan (2026-08-16), shuning uchun `openai/gpt-oss-120b` ishlatiladi; u ishlamasa bot avtomatik `openai/gpt-oss-20b` ga o'tadi.
- Model nomlari tez eskiradi: kerak bo'lsa `.env` dagi `*_MODEL` qiymatlarini yangilang.
- Xarajatni cheklash uchun `ALLOWED_USER_IDS` ni to'ldiring (o'z ID'ingizni botda `/id` bilan bilib oling).
- Hamma rasm/videolarda Google SynthID suv belgisi bo'ladi.
- `.env` faylini hech qachon GitHub'ga yuklamang.
