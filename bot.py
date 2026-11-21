"""DodaPlayAiBot: approved-user movie lookup, private + Telegram inline mode."""
import asyncio
import html
import logging
import os
import re
import sqlite3
import time
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Optional

import aiohttp
from aiogram import Bot, Dispatcher, F, Router, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultArticle,
    InputTextMessageContent, InlineQueryResultsButton,
)
from aiogram.exceptions import TelegramBadRequest
from psycopg import connect as pg_connect

logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger("dodaplay")
ROUTER = Router()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
TMDB_KEY = os.getenv("TMDB_API_KEY", "").strip()
OMDB_KEY = os.getenv("OMDB_API_KEY", "").strip()
KP_KEY = os.getenv("KINOPOISK_API_KEY", "").strip()
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
SQLITE_PATH = os.getenv("SQLITE_PATH", "access.sqlite3").strip()
ADMINS = {int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()}
TMDB_API = "https://api.themoviedb.org/3"
CACHE: dict[tuple, tuple[float, Any]] = {}
CACHE_MAX = 800

# Faqat bir xil film ekanligi foydalanuvchi yuborgan rasm/havolalar bilan
# tasdiqlangan istisnolar. Qolgan barcha filmlar API orqali aniqlanadi.
VERIFIED_EXTERNAL_IDS = {
    1384514: {"imdb": "tt34498564", "kinopoisk": 14246389},
}

COUNTRIES = {
    "AQSH": ("US", "AQSH"), "USA": ("US", "AQSH"),
    "US": ("US", "AQSH"), "UNITED STATES": ("US", "AQSH"),
    "AMERICA": ("US", "AQSH"), "США": ("US", "AQSH"),
    "UK": ("GB", "Buyuk Britaniya"), "GB": ("GB", "Buyuk Britaniya"),
    "UNITED KINGDOM": ("GB", "Buyuk Britaniya"),
    "BUYUK BRITANIYA": ("GB", "Buyuk Britaniya"),
    "ROSSIYA": ("RU", "Rossiya"), "RUSSIA": ("RU", "Rossiya"),
    "РОССИЯ": ("RU", "Rossiya"),
    "HINDISTON": ("IN", "Hindiston"), "INDIA": ("IN", "Hindiston"),
    "ИНДИЯ": ("IN", "Hindiston"),
    "JANUBIY KOREYA": ("KR", "Janubiy Koreya"),
    "SOUTH KOREA": ("KR", "Janubiy Koreya"),
    "ЮЖНАЯ КОРЕЯ": ("KR", "Janubiy Koreya"),
    "KOREA": ("KR", "Janubiy Koreya"),
    "FRANCE": ("FR", "Fransiya"), "FRANSIYA": ("FR", "Fransiya"),
    "GERMANY": ("DE", "Germaniya"), "GERMANIYA": ("DE", "Germaniya"),
    "CANADA": ("CA", "Kanada"), "KANADA": ("CA", "Kanada"),
    "JAPAN": ("JP", "Yaponiya"), "YAPONIYA": ("JP", "Yaponiya"),
    "CHINA": ("CN", "Xitoy"), "XITOY": ("CN", "Xitoy"),
    "TURKEY": ("TR", "Turkiya"), "TURKIYA": ("TR", "Turkiya"),
    "ЯПОНИЯ": ("JP", "Yaponiya"), "КИТАЙ": ("CN", "Xitoy"),
    "ГЕРМАНИЯ": ("DE", "Germaniya"), "ФРАНЦИЯ": ("FR", "Fransiya"),
    "ВЕЛИКОБРИТАНИЯ": ("GB", "Buyuk Britaniya"),
    "КАНАДА": ("CA", "Kanada"), "АВСТРАЛИЯ": ("AU", "Avstraliya"),
    "ИТАЛИЯ": ("IT", "Italiya"), "ИСПАНИЯ": ("ES", "Ispaniya"),
    "БРАЗИЛИЯ": ("BR", "Braziliya"), "МЕКСИКА": ("MX", "Meksika"),
    "ТУРЦИЯ": ("TR", "Turkiya"), "ИНДОНЕЗИЯ": ("ID", "Indoneziya"),
    "ТАИЛАНД": ("TH", "Tailand"),
}
COUNTRY_BY_ISO = {
    "US": "AQSH", "GB": "Buyuk Britaniya", "RU": "Rossiya",
    "IN": "Hindiston", "KR": "Janubiy Koreya", "FR": "Fransiya",
    "DE": "Germaniya", "CA": "Kanada", "JP": "Yaponiya",
    "CN": "Xitoy", "TR": "Turkiya", "IT": "Italiya", "ES": "Ispaniya",
    "AU": "Avstraliya", "MX": "Meksika", "BR": "Braziliya",
    "NZ": "Yangi Zelandiya", "UZ": "O‘zbekiston", "IR": "Eron",
    "ID": "Indoneziya", "TH": "Tailand",
}
GENRES = {
    "Action": "jangari", "Adventure": "sarguzasht",
    "Animation": "animatsiya", "Comedy": "komediya",
    "Crime": "jinoyat", "Documentary": "hujjatli",
    "Drama": "drama", "Family": "oilaviy", "Fantasy": "fantastika",
    "History": "tarixiy", "Horror": "qo‘rqinchli",
    "Music": "musiqa", "Mystery": "detektiv",
    "Romance": "romantik", "Science Fiction": "fantastika",
    "TV Movie": "telefilm", "Thriller": "triller",
    "War": "urush", "Western": "vestern",
    "комедия": "komediya", "боевик": "jangari",
    "ужасы": "qo‘rqinchli", "триллер": "triller",
    "драма": "drama", "детектив": "detektiv",
    "криминал": "jinoyat", "фантастика": "fantastika",
    "фэнтези": "fantastika", "семейный": "oilaviy",
    "приключения": "sarguzasht", "мелодрама": "melodrama",
    "романтика": "romantik", "история": "tarixiy",
    "военный": "urush", "война": "urush",
    "документальный": "hujjatli", "биография": "biografiya",
    "музыка": "musiqa", "мультфильм": "animatsiya",
    "мультфильмы": "animatsiya", "аниме": "anime",
    "спорт": "sport", "вестерн": "vestern",
    "детский": "bolalar uchun", "короткометражка": "qisqa metrajli",
    "короткометражный": "qisqa metrajli", "мюзикл": "musiqali",
    "фильм-нуар": "nuar", "биографический": "biografiya",
}
RATING_AGES = {
    "G": "0+", "TV-Y": "0+", "TV-G": "0+",
    "PG": "7+", "TV-Y7": "7+", "TV-PG": "12+",
    "PG-13": "13+", "TV-14": "14+", "R": "17+",
    "NC-17": "18+", "TV-MA": "18+",
}

def esc(value: Any) -> str:
    return html.escape(str(value if value not in (None, "") else "Mavjud emas"), quote=False)

def norm(text: Any) -> str:
    clean = unicodedata.normalize("NFKD", str(text or "")).casefold()
    clean = "".join(c for c in clean if not unicodedata.combining(c))
    return re.sub(r"[^\w]+", "", clean)

def cache_get(key: tuple) -> Any:
    entry = CACHE.get(key)
    if not entry:
        return None
    if entry[0] < time.monotonic():
        CACHE.pop(key, None)
        return None
    return entry[1]

def cache_put(key: tuple, obj: Any, ttl: int = 600) -> Any:
    if len(CACHE) >= CACHE_MAX:
        CACHE.pop(next(iter(CACHE)), None)
    CACHE[key] = (time.monotonic() + ttl, obj)
    return obj

def parse_search(query: str) -> tuple[str, Optional[int], Optional[str]]:
    raw = re.sub(r"\s+", " ", query.strip())
    country = None
    for alias in sorted(COUNTRIES, key=len, reverse=True):
        if raw.upper() == alias or raw.upper().endswith(" " + alias):
            country = COUNTRIES[alias][0]
            raw = raw[:-len(alias)].strip()
            break
    year = None
    year_match = re.search(r"(?:\s+|\s*\()((?:18|19|20)\d{2})\)?$", raw)
    if year_match:
        year = int(year_match.group(1))
        raw = raw[:year_match.start()].strip()
    # Accept both "Knives Out 2019 USA" and "Knives Out USA 2019".
    if country is None:
        for alias in sorted(COUNTRIES, key=len, reverse=True):
            if raw.upper().endswith(" " + alias):
                country = COUNTRIES[alias][0]
                raw = raw[:-len(alias)].strip()
                break
    return raw.strip(), year, country

class AccessDB:
    def __init__(self) -> None:
        self.pg = bool(DATABASE_URL)
        if not self.pg:
            path = Path(SQLITE_PATH)
            path.parent.mkdir(parents=True, exist_ok=True)
            LOG.warning("SQLite in use: configure Railway persistent volume or DATABASE_URL.")
        self._execute(
            "CREATE TABLE IF NOT EXISTS approvals (user_id BIGINT PRIMARY KEY, status TEXT NOT NULL, updated_at BIGINT NOT NULL)",
            (), write=True,
        )

    def _execute(self, sql: str, args: tuple = (), write: bool = False) -> Optional[str]:
        if self.pg:
            with pg_connect(DATABASE_URL, connect_timeout=8) as conn:
                with conn.cursor() as cur:
                    cur.execute(sql.replace("?", "%s"), args)
                    row = cur.fetchone() if not write else None
                    return str(row[0]) if row else None
        with sqlite3.connect(SQLITE_PATH, timeout=10) as conn:
            cur = conn.execute(sql, args)
            row = cur.fetchone() if not write else None
            return str(row[0]) if row else None

    def status(self, uid: int) -> str:
        if uid in ADMINS:
            return "yes"
        return self._execute("SELECT status FROM approvals WHERE user_id=?", (uid,)) or "none"

    def put(self, uid: int, status: str) -> None:
        self._execute(
            "INSERT INTO approvals (user_id,status,updated_at) VALUES (?,?,?) "
            "ON CONFLICT (user_id) DO UPDATE SET status=excluded.status, updated_at=excluded.updated_at",
            (uid, status, int(time.time())), write=True,
        )

    def approved_count(self) -> int:
        return int(self._execute(
            "SELECT COUNT(*) FROM approvals WHERE status=?", ("yes",)
        ) or 0)

    def approved_users(self, page: int, size: int = 8) -> list[tuple[int, int]]:
        """Doimiy bazadan faqat ruxsatli foydalanuvchilarni olish."""
        sql = ("SELECT user_id, updated_at FROM approvals WHERE status=? "
               "ORDER BY updated_at DESC, user_id DESC LIMIT ? OFFSET ?")
        args = ("yes", size, max(0, page) * size)
        if self.pg:
            with pg_connect(DATABASE_URL, connect_timeout=8) as conn:
                with conn.cursor() as cur:
                    cur.execute(sql.replace("?", "%s"), args)
                    return [(int(uid), int(ts)) for uid, ts in cur.fetchall()]
        with sqlite3.connect(SQLITE_PATH, timeout=10) as conn:
            return [(int(uid), int(ts)) for uid, ts in conn.execute(sql, args).fetchall()]

    def delete_approved_user(self, uid: int) -> bool:
        """Foydalanuvchini bazadan o‘chirish uning oddiy va inline ruxsatini bekor qiladi."""
        if uid in ADMINS:
            return False
        sql = "DELETE FROM approvals WHERE user_id=? AND status=?"
        args = (uid, "yes")
        if self.pg:
            with pg_connect(DATABASE_URL, connect_timeout=8) as conn:
                with conn.cursor() as cur:
                    cur.execute(sql.replace("?", "%s"), args)
                    return cur.rowcount > 0
        with sqlite3.connect(SQLITE_PATH, timeout=10) as conn:
            cur = conn.execute(sql, args)
            return cur.rowcount > 0

DB: Optional[AccessDB] = None

async def authorized(uid: int) -> bool:
    return bool(DB and await asyncio.to_thread(DB.status, uid) == "yes")

@dataclass
class MovieOption:
    tmdb_id: int
    title: str
    original_title: str
    year: str
    date: str
    popularity: float
    vote_count: int = 0

    @property
    def label(self) -> str:
        return f"{self.title} ({self.year})"

class MovieAPI:
    def __init__(self) -> None:
        self.http: Optional[aiohttp.ClientSession] = None
        self.limit = asyncio.Semaphore(5)

    async def get(self, url: str, params: Optional[dict] = None,
                  headers: Optional[dict] = None) -> dict:
        if not self.http:
            raise RuntimeError("HTTP session is not initialized")
        key = ("get", url, tuple(sorted((params or {}).items())))
        cached = cache_get(key)
        if cached is not None:
            return cached
        async with self.limit:
            try:
                async with self.http.get(
                    url, params=params, headers=headers,
                    timeout=aiohttp.ClientTimeout(total=12),
                ) as res:
                    if res.status != 200:
                        LOG.warning("API HTTP %s for %s", res.status, url.split("?")[0])
                        # Xato javobni juda qisqa muddatga keshlash: API
                        # vaqtincha ishdan chiqqanda tez-tez urib turmaymiz.
                        return cache_put(key, {}, 45)
                    data = await res.json(content_type=None)
                    return cache_put(key, data if isinstance(data, dict) else {})
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
                LOG.warning("API request failed: %s", type(exc).__name__)
                return {}

    async def tmdb(self, path: str, params: Optional[dict] = None) -> dict:
        data = {"api_key": TMDB_KEY, "language": "en-US"}
        data.update(params or {})
        return await self.get(TMDB_API + path, data)

    async def details(self, movie_id: int) -> dict:
        return await self.tmdb(f"/movie/{movie_id}", {
            "append_to_response": "external_ids,release_dates",
        })

    async def search(self, text: str) -> list[MovieOption]:
        title, year, country = parse_search(text)
        if not title:
            return []
        params: dict[str, Any] = {"query": title, "include_adult": "false"}
        if year:
            params["year"] = year

        # TMDB qidiruvi mashhur trilogiya qismlarini birinchi sahifada
        # bermasligi mumkin. Yilsiz keng qidiruvda faqat 2 sahifa tekshiriladi.
        first = await self.tmdb("/search/movie", params)
        raw = list(first.get("results") or [])
        if not year and int(first.get("total_pages") or 1) > 1:
            second = await self.tmdb("/search/movie", dict(params, page=2))
            raw.extend(second.get("results") or [])

        items = []
        seen: set[int] = set()
        for x in raw:
            if not isinstance(x, dict) or not x.get("id"):
                continue
            movie_id = int(x["id"])
            if movie_id in seen:
                continue
            seen.add(movie_id)
            date = str(x.get("release_date") or "")
            # Noto‘g‘ri yoki to‘liq bo‘lmagan sanaga aniq yil bermaymiz.
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
                date = ""
            if year and not date.startswith(str(year)):
                continue
            items.append(MovieOption(
                tmdb_id=movie_id, title=str(x.get("title") or ""),
                original_title=str(x.get("original_title") or ""),
                year=date[:4] or "—", date=date,
                popularity=float(x.get("popularity") or 0),
                vote_count=int(x.get("vote_count") or 0),
            ))

        target = norm(title)
        def score(m: MovieOption) -> tuple:
            names = (norm(m.title), norm(m.original_title))
            exact = target in names
            # Nomdan keyin bo‘lim/qo‘shimcha nom bo‘lsa, uni tegishli davom
            # sifatida ko‘ramiz; qisqa fanfilmni reytingga ko‘tarib yubormaymiz.
            prefix = any(n.startswith(target) for n in names if n)
            similarity = max(SequenceMatcher(None, target, n).ratio()
                             for n in names if n) if any(names) else 0.0
            year_known = bool(m.date)
            return (int(exact), int(prefix), int(year_known),
                    m.vote_count, similarity, m.popularity)

        # Mamlakat filt­ridan oldin ham relevant nomlar saralanadi.
        items.sort(key=score, reverse=True)
        if country:
            async def in_country(opt: MovieOption) -> bool:
                d = await self.details(opt.tmdb_id)
                codes = {str(z.get("iso_3166_1") or "").upper()
                         for z in d.get("production_countries") or []}
                return country in codes
            relevant = items[:18]
            matched = await asyncio.gather(*(in_country(item) for item in relevant))
            items = [item for item, yes in zip(relevant, matched) if yes]
        # Taklif variantlari qat'iy yangi yildan eski yilga qarab chiqadi.
        # Sana topilmagan natija eng oxirida ko'rsatiladi.
        items.sort(key=lambda item: item.date or "0000-00-00", reverse=True)
        return items[:5]

    async def imdb(self, imdb_id: Optional[str]) -> dict:
        if not imdb_id or not OMDB_KEY:
            return {}
        data = await self.get("https://www.omdbapi.com/", {"apikey": OMDB_KEY, "i": imdb_id})
        if data.get("Response") != "True":
            LOG.info("OMDb has no record for IMDb %s (or API unavailable).", imdb_id)
            return {}
        # An explicit ID lookup must return the requested title.
        if data.get("imdbID") and data["imdbID"] != imdb_id:
            return {}
        return data

    async def imdb_rating_fallback(self, imdb_id: Optional[str]) -> Optional[float]:
        """IMDb rasmiy ochiq reyting datasetidan olingan Agregarr keshli API."""
        if not imdb_id or not re.fullmatch(r"tt\d{7,10}", imdb_id):
            return None
        key = ("imdb-rating", imdb_id)
        cached = cache_get(key)
        if cached is not None:
            return cached if isinstance(cached, float) else None
        if not self.http:
            return None
        try:
            async with self.limit:
                async with self.http.get(
                    "https://api.agregarr.org/api/ratings",
                    params={"id": imdb_id},
                    timeout=aiohttp.ClientTimeout(total=6),
                ) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json(content_type=None)
                    if not isinstance(data, list):
                        return None
                    for item in data:
                        if not isinstance(item, dict) or item.get("imdbId") != imdb_id:
                            continue
                        value = item.get("rating")
                        if value is None:
                            return None
                        rating = float(value)
                        if 0 < rating <= 10:
                            return cache_put(key, rating, 3600)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, TypeError):
            LOG.info("Secondary IMDb rating lookup unavailable for %s", imdb_id)
        return None

    async def kinopoisk(self, title: str, original: str,
                       year: str, imdb_id: Optional[str],
                       known_id: Optional[int] = None) -> tuple[dict, Optional[int]]:
        if not KP_KEY:
            return {}, None
        headers = {"X-API-KEY": KP_KEY, "Accept": "application/json"}
        base = "https://kinopoiskapiunofficial.tech"
        expected = {norm(title), norm(original)} - {""}

        async def validated(film_id: int) -> tuple[dict, Optional[int]]:
            detail = await self.get(f"{base}/api/v2.2/films/{film_id}", headers=headers)
            if not detail or not detail.get("kinopoiskId"):
                return {}, None
            found_imdb = str(detail.get("imdbId") or "")
            if imdb_id and found_imdb and found_imdb != imdb_id:
                return {}, None
            if year != "—" and str(detail.get("year") or "") != year:
                return {}, None
            names = {norm(detail.get(k)) for k in ("nameEn", "nameOriginal", "nameRu")} - {""}
            # ISBN kabi IDga emas, tasdiqlangan IMDb ID yoki yaqin nomga ishonamiz.
            same_imdb = bool(imdb_id and found_imdb == imdb_id)
            similarity = max((SequenceMatcher(None, a, b).ratio()
                              for a in expected for b in names), default=0)
            if not (same_imdb or similarity >= 0.84 or (known_id and film_id == known_id)):
                return {}, None
            return detail, film_id

        if known_id:
            detail, matched_id = await validated(known_id)
            if detail:
                return detail, matched_id

        # Eng aniq usul — IMDb ID; nom bir tilda boshqacha bo‘lsa ham topiladi.
        if imdb_id:
            filtered = await self.get(f"{base}/api/v2.2/films",
                                      {"imdbId": imdb_id, "page": 1}, headers)
            for item in (filtered.get("items") or [])[:10]:
                film_id = item.get("kinopoiskId")
                if film_id:
                    detail, matched_id = await validated(int(film_id))
                    if detail:
                        return detail, matched_id

        # Eski keyword endpoint 500 qaytarishi mumkin: yangi endpointni sinaymiz.
        for lookup_title in dict.fromkeys(v for v in (original, title) if v):
            search = await self.get(f"{base}/api/v2.2/films",
                                    {"keyword": lookup_title, "page": 1}, headers)
            candidates = search.get("items") or []
            ranked = []
            for item in candidates:
                film_id = item.get("kinopoiskId")
                if not film_id:
                    continue
                if year != "—" and str(item.get("year") or "") != year:
                    continue
                names = {norm(item.get(k)) for k in ("nameEn", "nameOriginal", "nameRu")} - {""}
                exact = bool(names & expected)
                similarity = max((SequenceMatcher(None, a, b).ratio()
                                  for a in expected for b in names), default=0)
                if exact or similarity >= 0.82:
                    ranked.append((int(exact), similarity, int(film_id)))
            ranked.sort(reverse=True)
            for _, _, film_id in ranked[:4]:
                detail, matched_id = await validated(film_id)
                if detail:
                    return detail, matched_id
        return {}, None

API = MovieAPI()

def local_country(name: str) -> str:
    raw = str(name or "").strip()
    if not raw:
        return ""
    key = re.sub(r"\s+", " ", raw).upper()
    return COUNTRY_BY_ISO.get(key) or COUNTRIES.get(key, (None, raw))[1] or raw


def country_list(value: str) -> str:
    parts = [local_country(part) for part in str(value or "").split(",") if part.strip()]
    return ", ".join(dict.fromkeys(parts)) if parts else "Mavjud emas"


def country_line(items: list[dict], key: str) -> str:
    names = []
    for x in items:
        code = str(x.get("iso_3166_1") or x.get("countryCode") or "").upper()
        name = COUNTRY_BY_ISO.get(code) or local_country(x.get(key) or "")
        if name and name not in names:
            names.append(name)
    return ", ".join(names) if names else "Mavjud emas"

def local_genre(raw: str) -> str:
    """Janrni faqat o‘zbekcha ma’noda ko‘rsatish; begona atamani uzatmaslik."""
    name = re.sub(r"\s+", " ", str(raw or "").strip())
    if not name:
        return ""
    if name in GENRES:
        return GENRES[name]
    mapped = {key.casefold(): value for key, value in GENRES.items()}
    # API ba'zan vergul bilan yoki katta harfda qaytaradi.
    return mapped.get(name.casefold(), "")


def genre_list(raw: str) -> str:
    items = [local_genre(part) for part in str(raw or "").split(",")]
    unique = list(dict.fromkeys(value for value in items if value))
    return ", ".join(unique) if unique else "Mavjud emas"


def genre_line(items: list[dict], field: str = "name") -> str:
    return genre_list(", ".join(str(x.get(field) or "") for x in items if isinstance(x, dict)))

def age_from_rating(raw: Any) -> str:
    text = str(raw or "").strip().upper()
    if not text or text in ("N/A", "NR", "NOT RATED", "UNRATED"):
        return "Mavjud emas"
    if text in RATING_AGES:
        return RATING_AGES[text]
    m = re.search(r"(?:^|[^0-9])(0|6|7|12|13|14|16|17|18|21)\+?(?:$|[^0-9])", text)
    return f"{m.group(1)}+" if m else "Mavjud emas"

def tmdb_age(details: dict) -> str:
    releases = (details.get("release_dates") or {}).get("results") or []
    for iso in ("US", "GB", "IN"):
        for item in releases:
            if item.get("iso_3166_1") != iso:
                continue
            for rel in item.get("release_dates") or []:
                value = age_from_rating(rel.get("certification"))
                if value != "Mavjud emas":
                    return value
    return "Mavjud emas"

def rating_str(value: Any) -> str:
    if value in (None, "", "N/A", "null"):
        return "Mavjud emas"
    try:
        v = float(value)
        return f"{v:g} / 10" if v > 0 else "Mavjud emas"
    except (ValueError, TypeError):
        return "Mavjud emas"

async def make_caption(movie_id: int) -> str:
    key = ("caption", movie_id)
    cached = cache_get(key)
    if cached:
        return cached
    d = await API.details(movie_id)
    if not d or not d.get("id"):
        return "TMDB ma’lumotlarini olib bo‘lmadi. Keyinroq qayta urinib ko‘ring."
    verified = VERIFIED_EXTERNAL_IDS.get(movie_id, {})
    imdb_id = ((d.get("external_ids") or {}).get("imdb_id")
               or d.get("imdb_id") or verified.get("imdb"))
    if not imdb_id:
        # TMDB ba'zan /movie/{id} bilan IMDb ID qaytarmaydi.
        external = await API.tmdb(f"/movie/{movie_id}/external_ids")
        imdb_id = external.get("imdb_id") or None
    date = str(d.get("release_date") or "")
    year = date[:4] or "—"
    omdb, kp_result = await asyncio.gather(
        API.imdb(imdb_id),
        API.kinopoisk(str(d.get("title") or ""), str(d.get("original_title") or ""),
                      year, imdb_id, verified.get("kinopoisk")),
    )
    kp, kp_id = kp_result
    tmdb_link = f'https://www.themoviedb.org/movie/{movie_id}'
    imdb_link = f"https://www.imdb.com/title/{imdb_id}/" if imdb_id else None
    kp_link = f"https://www.kinopoisk.ru/film/{kp_id}/" if kp_id else None

    tmdb_countries = country_line(d.get("production_countries") or [], "name")
    tmdb_genres = genre_line(d.get("genres") or [])
    omdb_country = country_list(omdb.get("Country") or "")
    omdb_genres = genre_list(omdb.get("Genre") or "")
    # Manba topilmasa IMDb bo‘limi havola/reytin'gi alohida ko‘rsatiladi.
    # Davlat, yosh va janrlarni boshqa manbadan IMDbniki deb ko‘chirmaymiz.
    kp_countries = country_line(kp.get("countries") or [], "country")
    kp_genres = genre_line(kp.get("genres") or [], "genre")
    kp_age = age_from_rating(kp.get("ratingAgeLimits"))
    imdb_rating = rating_str(omdb.get("imdbRating"))
    if imdb_rating == "Mavjud emas":
        # OMDb ayniqsa yangi filmlarni kech qo‘shishi mumkin.
        # Avval Kinopoisk beradigan IMDb reytingini tekshiramiz.
        imdb_rating = rating_str(kp.get("ratingImdb"))
        if imdb_rating == "Mavjud emas":
            imdb_rating = rating_str(await API.imdb_rating_fallback(imdb_id))
    kp_rating = rating_str(kp.get("ratingKinopoisk"))
    def heading(name: str, link: Optional[str]) -> str:
        return f'<b><a href="{link}">{name}</a></b>' if link else f'<b>{name}</b> (havola mavjud emas)'
    caption = (
        f'🎬 <b>{esc(d.get("title"))}</b> ({esc(year)})\n\n'
        f'{heading("TMDB", tmdb_link)}\n'
        f'Davlati: {esc(tmdb_countries)}\n'
        f'Yosh chegarasi: {esc(tmdb_age(d))}\n'
        f'Janri: {esc(tmdb_genres)}\n\n'
        f'{heading("IMDb", imdb_link)}\n'
        f'Davlati: {esc(omdb_country)}\n'
        f'Reytingi: {esc(imdb_rating)}\n'
        f'Yosh chegarasi: {esc(age_from_rating(omdb.get("Rated")))}\n'
        f'Janri: {esc(omdb_genres)}\n\n'
        f'{heading("KINOPOISK", kp_link)}\n'
        + (f'{esc(kp_link)}\n' if kp_link else "")
        + f'Davlati: {esc(kp_countries)}\n'
        f'Reytingi: {esc(kp_rating)}\n'
        f'Yosh chegarasi: {esc(kp_age)}\n'
        f'Janri: {esc(kp_genres)}'
    )
    return cache_put(key, caption, 1800)

def choice_keyboard(items: list[MovieOption]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=m.label[:60], callback_data=f"movie:{m.tmdb_id}")]
        for m in items[:5]
    ])

# ================== ADMIN ACCESS PANEL ==================
ADMIN_USERS_PAGE_SIZE = 8


def admin_panel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Foydalanuvchilar ro‘yxati", callback_data="admin:users:0")],
    ])


async def admin_users_view(page: int) -> tuple[str, InlineKeyboardMarkup]:
    assert DB is not None
    count = await asyncio.to_thread(DB.approved_count)
    max_page = max(0, (count - 1) // ADMIN_USERS_PAGE_SIZE)
    page = min(max(0, page), max_page)
    entries = await asyncio.to_thread(DB.approved_users, page, ADMIN_USERS_PAGE_SIZE)
    text = (f"👥 <b>Ruxsat berilgan foydalanuvchilar</b>\n"
            f"Jami: <b>{count}</b>\nSahifa: {page + 1}/{max_page + 1}\n\n")
    rows = []
    if entries:
        text += "\n".join(
            f"{page * ADMIN_USERS_PAGE_SIZE + i}. ID: <code>{uid}</code>"
            for i, (uid, _) in enumerate(entries, start=1)
        )
        for uid, _ in entries:
            rows.append([InlineKeyboardButton(
                text=f"🗑 {uid} — o‘chirish",
                callback_data=f"admin:remove:{uid}:{page}",
            )])
    else:
        text += "Hozircha ruxsat berilgan foydalanuvchilar yo‘q."
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(
            text="⬅️ Oldingi", callback_data=f"admin:users:{page - 1}"
        ))
    if page < max_page:
        nav.append(InlineKeyboardButton(
            text="Keyingi ➡️", callback_data=f"admin:users:{page + 1}"
        ))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="🏠 Admin panel", callback_data="admin:home")])
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


@ROUTER.message(Command("admin", "users"))
async def admin_panel(message: types.Message) -> None:
    if message.chat.type != "private" or not message.from_user or message.from_user.id not in ADMINS:
        await message.answer("⛔ Admin panel faqat admin uchun.")
        return
    await message.answer("🛡 <b>DodaPlay admin paneli</b>", reply_markup=admin_panel_kb())


@ROUTER.callback_query(F.data.startswith("admin:"))
async def admin_actions(call: types.CallbackQuery, bot: Bot) -> None:
    if not call.from_user or call.from_user.id not in ADMINS:
        await call.answer("⛔ Faqat admin uchun.", show_alert=True)
        return
    if not call.message or call.message.chat.type != "private":
        await call.answer("⛔ Panel faqat shaxsiy chatda ishlaydi.", show_alert=True)
        return
    parts = (call.data or "").split(":")
    assert DB is not None
    try:
        action = parts[1]
        if action == "home" and len(parts) == 2:
            text, markup = "🛡 <b>DodaPlay admin paneli</b>", admin_panel_kb()
        elif action == "users" and len(parts) == 3:
            text, markup = await admin_users_view(int(parts[2]))
        elif action == "remove" and len(parts) == 4:
            uid, page = int(parts[2]), int(parts[3])
            if uid in ADMINS or await asyncio.to_thread(DB.status, uid) != "yes":
                await call.answer("Foydalanuvchi topilmadi yoki admin.", show_alert=True)
                return
            text = (f"⚠️ <b>Foydalanuvchini o‘chirishni tasdiqlaysizmi?</b>\n"
                    f"ID: <code>{uid}</code>\n\n"
                    "U bot va inline qidiruvdan foydalanish huquqini yo‘qotadi.")
            markup = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Ha, o‘chirish",
                                      callback_data=f"admin:confirm:{uid}:{page}")],
                [InlineKeyboardButton(text="↩️ Bekor qilish",
                                      callback_data=f"admin:users:{page}")],
            ])
        elif action == "confirm" and len(parts) == 4:
            uid, page = int(parts[2]), int(parts[3])
            deleted = await asyncio.to_thread(DB.delete_approved_user, uid)
            text, markup = await admin_users_view(page)
            text = (f"{'✅ Foydalanuvchi o‘chirildi.' if deleted else 'ℹ️ Foydalanuvchi avval o‘chirilgan.'}"
                    f"\nID: <code>{uid}</code>\n\n" + text)
            if deleted:
                try:
                    await bot.send_message(
                        uid, "⛔ Administrator DodaPlay botiga kirish ruxsatingizni bekor qildi."
                    )
                except Exception:
                    LOG.info("Removed user %s could not be notified.", uid)
        else:
            await call.answer("Noto‘g‘ri tugma.", show_alert=True)
            return
        await call.message.edit_text(text, reply_markup=markup)
        await call.answer()
    except (ValueError, IndexError):
        await call.answer("Noto‘g‘ri so‘rov.", show_alert=True)
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc).lower():
            await call.answer()
        else:
            LOG.exception("Admin panel Telegram edit failed")
            await call.answer("Panelni yangilab bo‘lmadi.", show_alert=True)
    except Exception:
        LOG.exception("Admin panel failed")
        await call.answer("Admin panelda xatolik yuz berdi.", show_alert=True)


@ROUTER.message(CommandStart())
async def start(message: types.Message, bot: Bot) -> None:
    user = message.from_user
    if not user:
        return
    if await authorized(user.id):
        welcome = ("✅ DodaPlay'ga xush kelibsiz! Film nomini yuboring.\n"
                   "Masalan: Knives Out 2019 AQSH\n\n"
                   "Inline rejim: @DodaPlayAiBot Knives Out 2019")
        if user.id in ADMINS:
            await message.answer(welcome + "\n\n🛡 Admin panel: /admin",
                                 reply_markup=admin_panel_kb())
        else:
            await message.answer(welcome)
        return
    assert DB is not None
    status = await asyncio.to_thread(DB.status, user.id)
    if status == "pending":
        await message.answer("⏳ Ruxsat so‘rovingiz admin ko‘rib chiqishini kutmoqda.")
        return
    if status == "no":
        await message.answer("⛔ Sizga botdan foydalanish uchun ruxsat berilmagan.")
        return
    await asyncio.to_thread(DB.put, user.id, "pending")
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Yes", callback_data=f"approve:yes:{user.id}"),
        InlineKeyboardButton(text="❌ No", callback_data=f"approve:no:{user.id}"),
    ]])
    admins_ok = 0
    for admin_id in ADMINS:
        try:
            await bot.send_message(
                admin_id,
                f"🛡 <b>Yangi foydalanuvchi ruxsat so‘rayapti</b>\n"
                f"ID: <code>{user.id}</code>\n"
                f"Foydalanuvchi: {esc(user.full_name)}",
                reply_markup=kb,
            )
            admins_ok += 1
        except Exception as exc:
            LOG.warning("Admin request notification failed: %s", type(exc).__name__)
    if admins_ok:
        await message.answer("⏳ So‘rov yuborildi. Admin tasdig‘ini kuting.")
    else:
        # Allow retry after admin opens the bot.
        await asyncio.to_thread(DB.put, user.id, "none")
        await message.answer("⚠️ Adminga xabar yuborilmadi. Keyinroq /start bosing.")

@ROUTER.callback_query(F.data.startswith("approve:"))
async def approve(call: types.CallbackQuery, bot: Bot) -> None:
    if not call.from_user or call.from_user.id not in ADMINS:
        await call.answer("Faqat admin tasdiqlaydi.", show_alert=True)
        return
    try:
        _, decision, target_raw = (call.data or "").split(":")
        uid = int(target_raw)
        if decision not in ("yes", "no"):
            raise ValueError("Invalid decision")
    except (ValueError, TypeError):
        await call.answer("Noto‘g‘ri so‘rov.", show_alert=True)
        return
    assert DB is not None
    status = await asyncio.to_thread(DB.status, uid)
    if status != "pending":
        await call.answer("Bu so‘rov avval ko‘rib chiqilgan.", show_alert=True)
        return
    await asyncio.to_thread(DB.put, uid, decision)
    if call.message:
        try:
            await call.message.edit_reply_markup(reply_markup=None)
        except TelegramBadRequest:
            pass
        await call.message.answer(
            f"ID: <code>{uid}</code> — {'✅ ruxsat berildi' if decision == 'yes' else '❌ rad etildi'}."
        )
    await call.answer("Saqlandi.")
    try:
        await bot.send_message(
            uid,
            "✅ Ruxsat berildi. Endi film nomini yozishingiz mumkin."
            if decision == "yes" else "⛔ Admin ruxsat so‘rovingizni rad etdi.",
        )
    except Exception:
        LOG.info("User %s cannot receive decision notification.", uid)

@ROUTER.message(Command("help"))
async def help_msg(message: types.Message) -> None:
    await message.answer("Namuna: Knives Out 2019 USA\n"
                         "Yoki @DodaPlayAiBot Knives Out 2019\n"
                         "Foydalanish uchun /start orqali ruxsat so‘rang.")

@ROUTER.message(F.text)
async def query_private(message: types.Message) -> None:
    if message.chat.type != "private" or not message.from_user:
        return
    if not await authorized(message.from_user.id):
        await message.answer("🔒 Avval /start bosing va admin ruxsatini oling.")
        return
    query = (message.text or "").strip()
    if len(query) > 180:
        await message.answer("Nom juda uzun. Film nomi, yili va davlatini yozing.")
        return
    title, _, _ = parse_search(query)
    if len(title) < 2:
        await message.answer("Film nomini yozing. Masalan: Knives Out 2019 AQSH")
        return
    try:
        items = await API.search(query)
        if not items:
            await message.answer("❌ Film topilmadi. Nomi, yili yoki davlatini tekshiring.")
            return
        # Single exact result even if partial/unrelated alternatives are present.
        exact = [m for m in items if norm(title) in (norm(m.title), norm(m.original_title))]
        if len(items) == 1 or len(exact) == 1:
            await message.answer(await make_caption((exact or items)[0].tmdb_id),
                                 parse_mode="HTML", disable_web_page_preview=True)
            return
        await message.answer(
            "🎬 Mos filmlardan birini tanlang:",
            reply_markup=choice_keyboard(items),
        )
    except Exception:
        LOG.exception("Movie search failed")
        await message.answer("⚠️ Qidiruvda xatolik. Keyinroq qayta urinib ko‘ring.")

@ROUTER.callback_query(F.data.startswith("movie:"))
async def choose_movie(call: types.CallbackQuery) -> None:
    if not call.from_user or not await authorized(call.from_user.id):
        await call.answer("Avval admin ruxsati kerak.", show_alert=True)
        return
    try:
        movie_id = int((call.data or "").split(":")[1])
    except (IndexError, ValueError):
        await call.answer("Variant noto‘g‘ri.", show_alert=True)
        return
    await call.answer("Ma’lumot olinmoqda...")
    try:
        caption = await make_caption(movie_id)
        if call.message:
            await call.message.edit_text(caption, parse_mode="HTML",
                                         disable_web_page_preview=True)
    except Exception:
        LOG.exception("Movie selection failed")
        if call.message:
            await call.message.answer("⚠️ Ma’lumot olinmadi, keyinroq qayta urinib ko‘ring.")

@ROUTER.inline_query()
async def inline_query(inline: types.InlineQuery) -> None:
    if not await authorized(inline.from_user.id):
        await inline.answer(
            [], is_personal=True, cache_time=3,
            button=InlineQueryResultsButton(
                text="🔒 Ruxsat olish uchun botga kiring",
                start_parameter="request",
            ),
        )
        return
    query = (inline.query or "").strip()
    if len(query) < 2:
        await inline.answer([], is_personal=True, cache_time=3)
        return
    try:
        items = await API.search(query[:180])
        # Telegram inline articles must contain the final message because the
        # inline selection happens outside the bot's private chat.
        captions = await asyncio.gather(
            *(make_caption(item.tmdb_id) for item in items[:5]),
            return_exceptions=True,
        )
        results = []
        for item, caption in zip(items, captions):
            if isinstance(caption, BaseException):
                LOG.warning("Inline result failed for TMDB %s", item.tmdb_id)
                continue
            results.append(InlineQueryResultArticle(
                id=f"movie-{item.tmdb_id}",
                title=item.label,
                description=f"TMDB • IMDb • Kinopoisk — {item.original_title}",
                input_message_content=InputTextMessageContent(
                    message_text=caption, parse_mode="HTML",
                    disable_web_page_preview=True,
                ),
            ))
        await inline.answer(results, is_personal=True, cache_time=15)
    except Exception:
        LOG.exception("Inline search failed")
        await inline.answer([], is_personal=True, cache_time=3)

async def main() -> None:
    global DB
    missing = [key for key, value in (
        ("BOT_TOKEN", BOT_TOKEN), ("TMDB_API_KEY", TMDB_KEY),
        ("ADMIN_IDS", ADMINS),
    ) if not value]
    if missing:
        raise RuntimeError("Railway Variables missing: " + ", ".join(missing))
    DB = AccessDB()
    dp = Dispatcher()
    dp.include_router(ROUTER)
    # Yagona HTML sozlama: send_message, answer va edit_text xabarlarida
    # <b>, <code>, <a> teglar oddiy matn sifatida chiqib qolmaydi.
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    async with aiohttp.ClientSession(
        headers={"User-Agent": "DodaPlayAiBot/1.0"},
    ) as session:
        API.http = session
        try:
            await bot.delete_webhook(drop_pending_updates=False)
            await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
        finally:
            await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
