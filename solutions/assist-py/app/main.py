from fastapi import FastAPI
from pydantic import BaseModel
import os
import json
import redis
import httpx
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import declarative_base, sessionmaker

app = FastAPI(title="Personal Assistant")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CACHE_TTL = int(os.getenv("CACHE_TTL", "120"))
redis_client = redis.from_url(REDIS_URL, decode_responses=True)

OWNER = os.getenv("APP_OWNER", "anonymous")
SECRET_KEY = os.getenv("APP_SECRET", "default_secret")

# --- НАСТРОЙКА БАЗЫ ДАННЫХ ---
# Берем URL из окружения (который мы передаем через Docker)
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./notes.db")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Модель таблицы для заметок
class NoteDB(Base):
    __tablename__ = "notes"
    id = Column(Integer, primary_key=True, index=True)
    text = Column(String, index=True)

# Создаем таблицы в базе данных при запуске приложения
Base.metadata.create_all(bind=engine)
# -----------------------------

class Note(BaseModel):
    text: str

@app.get("/")
async def root():
    return {
        "message": f"👋 Привет, {OWNER}!",
        "service": "personal-assistant",
        "version": "1.0",
        "endpoints": ["/me", "/notes", "/weather/{city}", "/secret/{key}"],
    }

@app.get("/health")
async def health():
    return {"status": "healthy", "owner": OWNER}

@app.get("/me")
async def me():
    return {
        "owner": OWNER,
        "secret_prefix": SECRET_KEY[:6]
        if SECRET_KEY != "default_secret"
        else "NOT_SET",
    }

@app.get("/secret/{key}")
async def secret(key: str):
    if key == SECRET_KEY:
        return {
            "flag": f"LAB2_SUCCESS_{OWNER.upper()}",
            "message": "The secret key is correct!",
        }
    return {
        "error": "The secret key is incorrect",
        "hint": "Check the APP_SECRET environment variable",
    }

WEATHER_CODES: dict[int, str] = {
    0: "☀️ Ясно", 1: "🌤 Малооблачно", 2: "⛅ Переменная облачность",
    3: "☁️ Пасмурно", 45: "🌫 Туман", 48: "🌫 Изморозь",
    51: "🌦 Лёгкая морось", 53: "🌦 Морось", 55: "🌧 Сильная морось",
    61: "🌧 Небольшой дождь", 63: "🌧 Дождь", 65: "🌧 Сильный дождь",
    71: "🌨 Небольшой снег", 73: "🌨 Снег", 75: "❄️ Сильный снег",
    80: "🌦 Ливень", 81: "🌧 Сильный ливень", 82: "⛈ Штормовой ливень",
    95: "⛈ Гроза", 96: "⛈ Гроза с градом", 99: "⛈ Сильная гроза с градом",
}

@app.get("/cache/stats")
async def cache_stats():
    keys = redis_client.keys(f"weather:{OWNER}:*")
    return {
        "owner": OWNER,
        "ttl_seconds": CACHE_TTL,
        "cached_count": len(keys),
        "cached_cities": sorted(k.split(":")[-1] for k in keys),
    }

@app.get("/weather/{city}")
async def weather(city: str):
    cache_key = f"weather:{OWNER}:{city.lower()}"

    cached = redis_client.get(cache_key)
    if cached:
        data = json.loads(cached)
        data["source"] = "cache" 
        return data
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            geo_resp = await client.get(
                "https://geocoding-api.open-meteo.com/v1/search",
                params={"name": city, "count": 1, "language": "ru"},
            )
            geo_data = geo_resp.json()

            if not geo_data.get("results"):
                return {"error": f"City «{city}» not found"}

            location = geo_data["results"][0]
            lat = location["latitude"]
            lon = location["longitude"]
            city_name = location.get("name", city)
            country = location.get("country", "")

            weather_resp = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code",
                },
            )
            weather_data = weather_resp.json()["current"]

            code = weather_data.get("weather_code", -1)

            result = {
                "city": city_name,
                "country": country,
                "coordinates": {"lat": lat, "lon": lon},
                "temperature_c": weather_data["temperature_2m"],
                "humidity_pct": weather_data["relative_humidity_2m"],
                "wind_km_h": weather_data["wind_speed_10m"],
                "condition": WEATHER_CODES.get(code, f"Code {code}"),
                "source": "api"
            }
            redis_client.setex(cache_key, CACHE_TTL, json.dumps(result))

            return result
    except Exception as e:
        return {"error": f"Failed to get weather: {type(e).__name__}: {e}"}

# --- НОВЫЕ ЭНДПОИНТЫ ДЛЯ ЗАМЕТОК (С БАЗОЙ ДАННЫХ) ---
@app.post("/notes")
async def create_note(note: Note):
    db = SessionLocal()
    try:
        new_note = NoteDB(text=note.text)
        db.add(new_note)
        db.commit()
        db.refresh(new_note)
        return {"status": "saved", "note_id": new_note.id}
    finally:
        db.close()

@app.get("/notes")
async def list_notes():
    db = SessionLocal()
    try:
        notes = db.query(NoteDB).all()
        return {"notes": [n.text for n in notes], "count": len(notes)}
    finally:
        db.close()