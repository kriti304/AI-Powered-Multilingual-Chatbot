



import os
import uuid
import json
import hashlib
import hmac
from typing import Optional
from pathlib import Path
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

try:
    import pandas as pd
    from rapidfuzz import process, fuzz
    import numpy as np
    HAS_CENSUS = True
except ImportError:
    HAS_CENSUS = False

try:
    from googletrans import Translator
    from gtts import gTTS
    HAS_TRANSLATION = True
    translator = Translator()
except ImportError:
    HAS_TRANSLATION = False

load_dotenv()

# ----- Configuration -----
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_NAME = os.getenv("DB_NAME", "cdac")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "Papa@304")
DB_PORT = os.getenv("DB_PORT", "5432")
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-this")

BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)

HISTORY_FILE = "session_history.json"
SESSIONS_FILE = "sessions.json"
API_CACHE = {}

CENSUS_DF = None
STATES = []
FIELDS = []

if HAS_CENSUS:
    try:
        CENSUS_DF = pd.read_excel("census_data.xls")
        STATES = list(CENSUS_DF['State'].unique())
        FIELDS = [col for col in CENSUS_DF.columns if col.lower() != 'state']
    except FileNotFoundError:
        print("⚠️  Warning: census_data.xls not found. Census features disabled.")
        HAS_CENSUS = False

app = FastAPI(title="Census Chatbot Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ----- Password hashing (PBKDF2) -----
def hash_password(password: str) -> str:
    """Hash password using PBKDF2"""
    salt = os.urandom(32).hex()
    pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000).hex()
    return f"{salt}${pwd_hash}"

def verify_password(password: str, hash_str: str) -> bool:
    """Verify password against hash"""
    try:
        if '$' not in hash_str:
            # Legacy plain text (backward compatibility)
            return password == hash_str
        
        salt, pwd_hash = hash_str.split('$')
        new_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000).hex()
        return hmac.compare_digest(new_hash, pwd_hash)
    except:
        return False

def get_db_connection():
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            port=DB_PORT,
        )
        return conn
    except Exception as e:
        print("❌ DB connection error:", e)
        return None

def init_db():
    """Create tables if they do not exist."""
    conn = get_db_connection()
    if not conn:
        raise RuntimeError("Database connection failed")
    cur = conn.cursor()
    
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
      uid SERIAL PRIMARY KEY,
      email VARCHAR(255) UNIQUE NOT NULL,
      password VARCHAR(255) NOT NULL,
      created_at TIMESTAMP DEFAULT now()
    );
    """)
    
    # Sessions table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
      session_id VARCHAR(128) PRIMARY KEY,
      user_id VARCHAR(255) REFERENCES users(email) ON DELETE CASCADE,
      created_at TIMESTAMP DEFAULT now()
    );
    """)
    
    # Histories table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS histories (
      id SERIAL PRIMARY KEY,
      session_id VARCHAR(128) REFERENCES sessions(session_id) ON DELETE CASCADE,
      role VARCHAR(16) NOT NULL,
      message TEXT NOT NULL,
      created_at TIMESTAMP DEFAULT now()
    );
    """)
    
    conn.commit()
    cur.close()
    conn.close()

try:
    init_db()
    print("✅ Database initialized successfully")
except Exception as e:
    print("❌ Could not initialize DB:", e)

# ----- Pydantic models -----
class SignupRequest(BaseModel):
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: Optional[str] = None

class SimpleLoginRequest(BaseModel):
    user_id: str

class ChatRequest(BaseModel):
    message: str
    language: Optional[str] = "en"
    session_id: Optional[str] = None

class TTSRequest(BaseModel):
    text: str
    language: Optional[str] = "en"

# ----- Field synonyms (Census) -----
FIELD_SYNONYMS = {
    'male population': 'Total Population Male',
    'female population': 'Total Population Female',
    'total population': 'Total Population Person',
    'population person': 'Total Population Person',
    'males': 'Total Population Male',
    'male': 'Total Population Male',
    'females': 'Total Population Female',
    'female': 'Total Population Female',
    'population': 'Total Population Person',
    'households': 'No of Households',
    'household': 'No of Households',
    'number of households': 'No of Households',
    'literates population': 'Literates Population Person',
    'literates': 'Literates Population Person',
    'literacy': 'Literates Population Person',
    'literate population': 'Literates Population Person',
    'male literates': 'Literates Population Male',
    'female literates': 'Literates Population Female',
    'illiterates': 'Illiterate Persons',
    'illiterate population': 'Illiterate Persons',
    'illiteracy': 'Illiterate Persons',
    'illiterate persons': 'Illiterate Persons',
    'male illiterates': 'Illiterate Male',
    'female illiterates': 'Illiterate Female',
    'workers': 'Total Worker Population Person',
    'worker': 'Total Worker Population Person',
    'male workers': 'Total Worker Population Male',
    'female workers': 'Total Worker Population Female',
}

# ----- History helpers -----
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

def save_history_db(session_id, role, message):
    """Save to database (preferred)"""
    conn = get_db_connection()
    if not conn:
        return
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO histories (session_id, role, message) VALUES (%s, %s, %s)",
                    (session_id, role, message))
        conn.commit()
    finally:
        cur.close()
        conn.close()

# ----- Session helpers -----
def load_sessions():
    try:
        with open(SESSIONS_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_sessions(sessions):
    with open(SESSIONS_FILE, 'w') as f:
        json.dump(sessions, f, indent=2)

def create_session_for_user(user_email: str) -> str:
    conn = get_db_connection()
    if not conn:
        return str(uuid.uuid4())
    cur = conn.cursor()
    session_id = str(uuid.uuid4())
    try:
        cur.execute("INSERT INTO sessions (session_id, user_id) VALUES (%s, %s)", 
                    (session_id, user_email))
        conn.commit()
    finally:
        cur.close()
        conn.close()
    return session_id

# ----- Census NLP helpers (if available) -----
def get_best_state_match(query: str):
    if not HAS_CENSUS or not STATES:
        return None
    query_lower = query.lower()
    state_mapping = {state.lower(): state for state in STATES}
    
    if query_lower in state_mapping:
        return state_mapping[query_lower]
    
    for state_lower, original_state in state_mapping.items():
        if state_lower in query_lower or query_lower in state_lower:
            return original_state
    
    try:
        match, score, _ = process.extractOne(query_lower, state_mapping.keys(), 
                                             scorer=fuzz.partial_ratio)
        if score > 60:
            return state_mapping[match]
    except:
        pass
    
    return None

def get_best_field_match(query: str):
    if not HAS_CENSUS or not FIELDS:
        return None
    query_lower = query.lower()
    sorted_synonyms = sorted(FIELD_SYNONYMS.items(), key=lambda x: len(x[0]), reverse=True)
    
    for synonym, actual_field in sorted_synonyms:
        synonym_lower = synonym.lower()
        if synonym_lower in query_lower:
            return actual_field
    
    field_mapping = {col.lower(): col for col in FIELDS}
    if query_lower in field_mapping:
        return field_mapping[query_lower]
    
    try:
        match, score, _ = process.extractOne(query_lower, field_mapping.keys(), 
                                             scorer=fuzz.partial_ratio)
        if score > 50:
            return field_mapping[match]
    except:
        pass
    
    return None

def parse_query_for_filters(query: str):
    state = get_best_state_match(query)
    field = get_best_field_match(query)
    return {"state": state, "field": field}

def get_census_data(state, field):
    if not HAS_CENSUS or CENSUS_DF is None:
        return {"error": "Census data not available"}
    
    if state and field:
        state_rows = CENSUS_DF[CENSUS_DF['State'].str.lower() == state.lower()]
        if state_rows.empty:
            return {"error": f"No data found for state '{state}'."}
        
        if 'TRU' in CENSUS_DF.columns:
            total_row = state_rows[state_rows['TRU'] == 'Total']
            if not total_row.empty:
                row = total_row.iloc[0]
            else:
                row = state_rows.iloc[0]
        else:
            row = state_rows.iloc[0]
        
        if field not in row.index:
            return {"error": f"Field '{field}' not found in dataset."}
        
        value = row[field]
        if pd.isna(value):
            value = None
        elif isinstance(value, (np.integer, np.int64)):
            value = int(value)
        
        return {"state": state, "attribute": field, "value": value}
    
    elif field:
        if field in CENSUS_DF.columns:
            total = CENSUS_DF[field].sum()
            if pd.isna(total):
                total = "N/A"
            else:
                total = int(total) if isinstance(total, (np.integer, np.int64)) else total
        else:
            total = "N/A"
        return {"state": "India", "attribute": field, "value": total}
    
    return {"error": "Please specify both state and field."}

# ----- Routes: Auth -----
@app.post("/signup")
def signup(req: SignupRequest):
    """Register a new user"""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="DB connection failed")
    cur = conn.cursor()
    hashed = hash_password(req.password)
    try:
        cur.execute("INSERT INTO users (email, password) VALUES (%s, %s)", 
                    (req.email, hashed))
        conn.commit()
        return {"success": True, "message": "User registered successfully"}
    except psycopg2.Error as e:
        conn.rollback()
        if e.pgcode == "23505":
            raise HTTPException(status_code=400, detail="Email already registered")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@app.post("/login")
def login(req: LoginRequest):
    """Login user and create session"""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="DB connection failed")
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT email, password FROM users WHERE email = %s", (req.email,))
        user = cur.fetchone()
        if not user:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        # Verify password if provided
        if req.password:
            if not verify_password(req.password, user['password']):
                raise HTTPException(status_code=401, detail="Invalid credentials")
        
        # Create session
        session_id = create_session_for_user(user['email'])
        return {"success": True, "user_id": user['email'], "session_id": session_id}
    finally:
        cur.close()
        conn.close()

@app.post("/simple-login")
def simple_login(payload: SimpleLoginRequest):
    """Quick login with just user_id (email)"""
    email = payload.user_id
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="DB connection failed")
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT email FROM users WHERE email = %s", (email,))
        user = cur.fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        session_id = create_session_for_user(email)
        return {"success": True, "user_id": email, "session_id": session_id}
    finally:
        cur.close()
        conn.close()

# ----- Routes: Languages -----
@app.get("/languages")
def languages():
    """Get supported languages"""
    return {
        "languages": [
            {"code": "en", "name": "English"},
            {"code": "hi", "name": "Hindi"},
            {"code": "ta", "name": "Tamil"},
            {"code": "bn", "name": "Bengali"},
            {"code": "pa", "name": "Punjabi"},
            {"code": "mr", "name": "Marathi"},
            {"code": "te", "name": "Telugu"},
            {"code": "gu", "name": "Gujarati"},
            {"code": "kn", "name": "Kannada"},
            {"code": "ml", "name": "Malayalam"},
        ]
    }





@app.post("/chat")
def chat(req: ChatRequest):
    """Process user message and return chatbot response"""
    if not req.message:
        raise HTTPException(status_code=400, detail="Message required")
    
    # Create/ensure session
    session_id = req.session_id
    if not session_id:
        session_id = str(uuid.uuid4())
    
    # Ensure session exists in database
    conn = get_db_connection()
    if conn:
        cur = conn.cursor()
        try:
            # Check if session exists
            cur.execute("SELECT session_id FROM sessions WHERE session_id = %s", (session_id,))
            if not cur.fetchone():
                # Session doesn't exist, create it
                cur.execute("INSERT INTO sessions (session_id, user_id) VALUES (%s, %s)",
                            (session_id, None))
                conn.commit()
        except Exception as e:
            print(f"Session creation error: {e}")
            conn.rollback()
        finally:
            cur.close()
            conn.close()
    
    # Save user message
    save_history_db(session_id, "user", req.message)
    
    # Try census chatbot if enabled
    bot_response = None
    if HAS_CENSUS:
        filters = parse_query_for_filters(req.message)
        if filters["state"] and filters["field"]:
            data = get_census_data(filters["state"], filters["field"])
            if "error" not in data:
                value = data["value"]
                if isinstance(value, int):
                    value = f"{value:,}"
                bot_response = f"The {data['attribute']} of {data['state']} is {value}."
    
    # Fallback response
    if not bot_response:
        bot_response = f"I heard: {req.message}"
    
    # Translate if needed
    if HAS_TRANSLATION and req.language != "en":
        try:
            bot_response = translator.translate(bot_response, src='en', 
                                               dest=req.language).text
        except:
            pass
    
    # Save bot response
    save_history_db(session_id, "bot", bot_response)
    
    return {"response": bot_response, "session_id": session_id}


    
# ----- Routes: TTS -----
@app.post("/tts")
def tts(req: TTSRequest):
    """Generate text-to-speech audio"""
    if not HAS_TRANSLATION:
        return {"audio_url": None, "message": "TTS not available"}
    
    try:
        tts_lang_map = {
            "hi": "hi", "en": "en", "bn": "bn", "te": "te", "mr": "mr",
            "ta": "ta", "gu": "gu", "kn": "kn", "ml": "ml", "or": "or", "ur": "ur",
        }
        tts_lang = tts_lang_map.get(req.language, "en")
        
        tts = gTTS(text=req.text, lang=tts_lang)
        filename = f"tts_{uuid.uuid4().hex}.mp3"
        filepath = STATIC_DIR / filename
        tts.save(str(filepath))
        
        return {"audio_url": f"/static/{filename}"}
    except Exception as e:
        print(f"TTS error: {e}")
        return {"audio_url": None, "error": str(e)}

# ----- Routes: History -----
@app.get("/user_history/{user_id}")
def user_history(user_id: str):
    """Get all sessions and histories for a user"""
    conn = get_db_connection()
    if not conn:
        return {"histories": []}
    
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
          SELECT s.session_id,
                 json_agg(json_build_object('role', h.role, 'message', h.message, 
                          'created_at', h.created_at)) AS history
          FROM sessions s
          LEFT JOIN histories h ON h.session_id = s.session_id
          WHERE s.user_id = %s
          GROUP BY s.session_id
          ORDER BY s.created_at DESC
        """, (user_id,))
        
        rows = cur.fetchall()
        results = []
        for r in rows:
            hist = [
                {
                    'role': h['role'],
                    'message': h['message'],
                    'created_at': str(h['created_at'])
                }
                for h in (r['history'] or [])
            ]
            results.append({"session_id": r['session_id'], "history": hist})
        
        return {"histories": results}
    finally:
        cur.close()
        conn.close()

# ----- Routes: Static Files -----
@app.get("/static/{file_path:path}")
def static_files(file_path: str):
    """Serve static files (audio, etc.)"""
    file_full = STATIC_DIR / file_path
    if not file_full.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path=str(file_full))

# ----- Routes: Health -----
@app.get("/health")
def health():
    """Health check endpoint"""
    return {
        "status": "ok",
        "time": str(datetime.utcnow()),
        "census_enabled": HAS_CENSUS,
        "translation_enabled": HAS_TRANSLATION
    }

# ----- Run -----
if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting Census Chatbot Backend on port 8000...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
