"""
Language configuration for 16 Indian languages.
Maps language names to language codes used by translation services.
"""

# 16 Indian languages with their ISO 639-1 codes
SUPPORTED_LANGUAGES = {
    "hindi": {"code": "hi", "name": "Hindi", "native": "हिन्दी"},
    "english": {"code": "en", "name": "English", "native": "English"},
    "bengali": {"code": "bn", "name": "Bengali", "native": "বাংলা"},
    "telugu": {"code": "te", "name": "Telugu", "native": "తెలుగు"},
    "marathi": {"code": "mr", "name": "Marathi", "native": "मराठी"},
    "tamil": {"code": "ta", "name": "Tamil", "native": "தமிழ்"},
    "gujarati": {"code": "gu", "name": "Gujarati", "native": "ગુજરાતી"},
    "kannada": {"code": "kn", "name": "Kannada", "native": "ಕನ್ನಡ"},
    "malayalam": {"code": "ml", "name": "Malayalam", "native": "മലയാളം"},
    "odia": {"code": "or", "name": "Odia", "native": "ଓଡ଼ିଆ"},
    "punjabi": {"code": "pa", "name": "Punjabi", "native": "ਪੰਜਾਬੀ"},
    "assamese": {"code": "as", "name": "Assamese", "native": "অসমীয়া"},
    "urdu": {"code": "ur", "name": "Urdu", "native": "اردو"},
    "sanskrit": {"code": "sa", "name": "Sanskrit", "native": "संस्कृतम्"},
    "kashmiri": {"code": "ks", "name": "Kashmiri", "native": "कश्मीरी"},
    "nepali": {"code": "ne", "name": "Nepali", "native": "नेपाली"}
}

# Language codes list for easy access
LANGUAGE_CODES = [lang["code"] for lang in SUPPORTED_LANGUAGES.values()]

# Language names list
LANGUAGE_NAMES = [lang["name"] for lang in SUPPORTED_LANGUAGES.values()]

def get_language_code(language_input):
    """
    Get language code from various input formats.
    Accepts: language name, language code, or case variations.
    """
    if not language_input:
        return "en"  # Default to English
    
    language_input = language_input.lower().strip()
    
    # Check if it's already a code
    if language_input in LANGUAGE_CODES:
        return language_input
    
    # Check if it's a language name
    if language_input in SUPPORTED_LANGUAGES:
        return SUPPORTED_LANGUAGES[language_input]["code"]
    
    # Try to find by partial match
    for key, value in SUPPORTED_LANGUAGES.items():
        if language_input in key or key in language_input:
            return value["code"]
    
    # Default to English if not found
    return "en"

def get_language_info(language_code):
    """Get language information by code"""
    for lang_info in SUPPORTED_LANGUAGES.values():
        if lang_info["code"] == language_code:
            return lang_info
    return {"code": "en", "name": "English", "native": "English"}

def is_supported_language(language_input):
    """Check if a language is supported"""
    code = get_language_code(language_input)
    return code in LANGUAGE_CODES


