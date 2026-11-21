# DodaPlay — kino ma'lumot boti

Telegram: https://t.me/DodaPlayAiBot

Kino original nomi, ixtiyoriy yili yoki davlati bilan TMDB'dan izlanadi. 1 ta aniq moslik topilsa ma'lumot yuboriladi; aks holda 5 tagacha mos natija inline tugmalar bilan tanlanadi. Bot Telegram'ning inline rejimida ham ishlaydi. Foydalanish uchun admin ruxsati zarur.

## Railway

1. Repository'ni Railway'dagi yangi **DodaPlay** servisi bilan ulang, branch: `main`.
2. PostgreSQL xizmatini (yoki doimiy volume) ulang: ruxsatlar restartda yo'qolmasin.
3. Railway **Variables** bo'limida quyidagilarni kiriting. Bot tokenlari va kalitlarni GitHub'ga yozmang:

| Variable | Talab |
| --- | --- |
| `BOT_TOKEN` | Majburiy — @BotFather orqali olingan token |
| `ADMIN_IDS` | Majburiy — Telegram raqamli IDlari, vergul bilan |
| `TMDB_API_KEY` | Majburiy — TMDB API key |
| `OMDB_API_KEY` | IMDb reytingi uchun — OMDb API key |
| `KINOPOISK_API_KEY` | Kinopoisk reytingi/film havolasi uchun — kinopoiskapiunofficial.tech kaliti |
| `DATABASE_URL` | Tavsiya etiladi — Railway PostgreSQL connection string |
| `SQLITE_PATH` | PostgreSQL bo'lmasa — doimiy volume ichidagi SQLite fayl yo'li (masalan `/data/access.sqlite3`) |

**Muhim:** PostgreSQL ham, doimiy volume ham bo'lmasa SQLite fayl konteyner yangilanganda yo'qolishi mumkin. Bunda foydalanuvchi ruxsatlari saqlanmaydi.

Bot `python bot.py` buyrug'i bilan polling rejimida ishlaydi. HTTP port kerak emas. Faqat bitta nusxa ishga tushsin.

## BotFather

`/setinline` orqali inline mode'ni yoqing, ixtiyoriy placeholder: `Kino nomini yozing...`. Botni istalgan chatdan `@DodaPlayAiBot Knives Out 2019` deb chaqiring.

## Ruxsat

Foydalanuvchi `/start` yuboradi. Adminlarga Yes/No tugmalari bilan so'rov boradi. Qaror database'da saqlanadi; adminlar avtomatik ruxsatli. Ruxsatsiz foydalanuvchilar qidiruvdan yoki inline mode'dan foydalana olmaydi.

## Manbalar

TMDB ID, mamlakat, janr va sertifikat TMDB API'dan olinadi. IMDb havolasi TMDB `external_ids.imdb_id` orqali, IMDb reytingi va yosh chegarasi OMDb orqali olinadi. Kinopoisk ma'lumoti Kinopoisk Unofficial API'dan mustaqil tekshirilgan moslik bo'yicha olinadi. Ishonchli moslik bo'lmasa uydirma havola yoki reyting chiqarilmaydi.

API cheklovlari yoki film ma'lumoti yo'qligida `Mavjud emas` ko'rsatiladi. Har bir manbaning yoshi/reytigi mustaqil va bir-biridan farq qilishi mumkin.

## Texnik

Python 3.11; aiogram 3; aiohttp; psycopg 3. Qidiruvlar va tayyor javoblar qisqa muddatli RAM keshda saqlanadi. LLM/OpenAI chaqiruvlari yo'q — token sarfi nol.