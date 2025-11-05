from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import speech_recognition as sr
from gtts import gTTS
import googletrans
import requests
import json
import os
from datetime import datetime
import base64

# Load env vars
load_dotenv()
app = FastAPI()
translator = googletrans.Translator()

# Allow CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Config
CENSUS_API_URL = "https://api.data.gov.in/resource/1d369aae-155a-4cc8-b7a8-04d4cd5a4a96"
API_KEY = os.getenv("DATA_GOV_IN_API_KEY")
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")
HISTORY_FILE = "session_history.json"

# Models
class ChatRequest(BaseModel):
    message: str
    language: str
    session_id: str

class VoiceRequest(BaseModel):
    audio_data: str
    language: str

class TTSRequest(BaseModel):
    text: str
    language: str

# Helpers
def load_history(session_id):
    try:
        with open(HISTORY_FILE, 'r') as f:
            data = json.load(f)
            return data.get(session_id, [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_history(session_id, history):
    try:
        with open(HISTORY_FILE, 'r') as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}
    data[session_id] = history
    with open(HISTORY_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def parse_query_for_filters(query):
    states = [
        "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh",
        "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka",
        "Kerala", "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya", "Mizoram",
        "Nagaland", "Odisha", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu",
        "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal", "Delhi"
    ]
    fields = {"population": "population", "literacy": "literacy_rate", "sex ratio": "sex_ratio"}
    state_match = next((s for s in states if s.lower() in query.lower()), None)
    field_match = next((f for k, f in fields.items() if k in query.lower()), "population")
    return {"state": state_match, "field": field_match}

# Routes
@app.get("/history/{session_id}")
async def get_history(session_id: str):
    return load_history(session_id)

@app.post("/chat")
async def chat(request: ChatRequest):
    translated_msg = translator.translate(request.message, src=request.language, dest='en').text
    filters = parse_query_for_filters(translated_msg)
    params = {"api-key": API_KEY, "format": "json", "limit": 1}
    if filters["state"]:
        params["filters[state]"] = filters["state"]

    try:
        response = requests.get(CENSUS_API_URL, params=params)
        data = response.json() if response.status_code == 200 else {}
        records = data.get("records", [])
        if records:
            record = records[0]
            census_data = {
                "state": record.get("state", "N/A"),
                "population": record.get("population", "N/A"),
                "literacy_rate": record.get("literacy_rate", "N/A"),
                "sex_ratio": record.get("sex_ratio", "N/A"),
            }
        else:
            census_data = {"error": "No data found."}
    except Exception as e:
        census_data = {
            "population": "1.4 billion (2021 est)",
            "states": 28,
            "note": f"API request failed: {e}"
        }

    bot_response = f"Based on Indian census data: {json.dumps(census_data, indent=2)}"
    translated_response = translator.translate(bot_response, src='en', dest=request.language).text

    history = load_history(request.session_id)
    history.append({
        "user": request.message,
        "bot": translated_response,
        "timestamp": str(datetime.now())
    })
    save_history(request.session_id, history)
    return {"response": translated_response, "history": history}

@app.post("/stt")
async def speech_to_text(request: VoiceRequest):
    recognizer = sr.Recognizer()
    audio_bytes = base64.b64decode(request.audio_data)
    audio = sr.AudioData(audio_bytes, sample_rate=16000, sample_width=2)
    try:
        text = recognizer.recognize_google(audio, language=request.language)
        return {"text": text}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Speech recognition failed: {e}")

@app.post("/tts")
async def text_to_speech(request: TTSRequest):
    try:
        tts = gTTS(text=request.text, lang=request.language)
        filename = f"response_{hash(request.text)}.mp3"
        filepath = os.path.join("static", filename)
        tts.save(filepath)
        return {"audio_url": f"/static/{filename}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS failed: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

