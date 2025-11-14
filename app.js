import React, { useState, useRef, useEffect } from "react";
import axios from "axios";
import SpeechRecognition, { useSpeechRecognition } from "react-speech-recognition";
import "./App.css";
import Login from "./Login";

const App = () => {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [languages, setLanguages] = useState([]);
  const [selectedLanguage, setSelectedLanguage] = useState("en");
  const [audioUrl, setAudioUrl] = useState(null);
  const [sessionId, setSessionId] = useState("");
  const [userId, setUserId] = useState("");
  const [histories, setHistories] = useState([]);
  const audioRef = useRef(null);
  const messagesEndRef = useRef(null);

  const BASE_URL = "http://localhost:8000"; // change to your deployed backend later

  // 🧠 On mount, restore user and create new session
  useEffect(() => {
    const storedUser = localStorage.getItem("user_id");
    if (storedUser) {
      handleLogin({ user_id: storedUser });
    }
  }, []);
  const handleLogin = async ({ user_id }) => {
    try {
      const res = await axios.post(`${BASE_URL}/login`, { user_id });
      const { user_id: uid, session_id: sid } = res.data;
      setUserId(uid);
      setSessionId(sid);
      localStorage.setItem("user_id", uid);
      localStorage.setItem("session_id", sid);
      // Load user history
      const histRes = await axios.get(`${BASE_URL}/user_history/${uid}`);
      setHistories(histRes.data.histories || []);
    } catch (e) {
      console.error("Login failed", e);
    }
  };

  const handleLogout = () => {
    setUserId("");
    setSessionId("");
    setHistories([]);
    localStorage.removeItem("user_id");
    localStorage.removeItem("session_id");
  };


  // 🌐 Fetch supported languages dynamically from backend
  useEffect(() => {
    const fetchLanguages = async () => {
      try {
        const res = await axios.get(`${BASE_URL}/languages`);
        setLanguages(res.data.languages || []);
      } catch (err) {
        console.error("Error fetching languages:", err);
        // fallback if backend route not available
        setLanguages([
          { code: "en", name: "English" },
          { code: "hi", name: "Hindi" },
          { code: "ta", name: "Tamil" },
          { code: "bn", name: "Bengali" },
          { code: "pa", name: "Punjabi" },
          { code: "mr", name: "Marathi" },
        ]);
      }
    };
    fetchLanguages();
  }, []);

  // 🧏 Speech recognition setup
  const { transcript, listening, resetTranscript, browserSupportsSpeechRecognition } =
    useSpeechRecognition({
      lang: selectedLanguage,
      continuous: true,
      interimResults: true,
    });

  useEffect(() => {
    if (transcript) setInput(transcript);
  }, [transcript]);

  // 🔽 Auto-scroll chat
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // 🔊 Play TTS audio
  const playAudio = (url) => {
    if (audioRef.current) audioRef.current.pause();
    const audio = new Audio(url);
    audio.play().catch((e) => console.error("Playback error:", e));
    audioRef.current = audio;
  };

  // 💬 Send chat message
  const sendMessage = async (msg = input) => {
    if (!msg.trim()) return;

    const userMessage = { text: msg, isUser: true };
    setMessages((prev) => [...prev, userMessage]);

    try {
      // Step 1: Chat response
      const chatRes = await axios.post(`${BASE_URL}/chat`, {
        message: msg,
        language: selectedLanguage,
        session_id: sessionId,
      });

      const botText = chatRes.data.response || "⚠️ No response received.";
      const botResponse = { text: botText, isUser: false };
      setMessages((prev) => [...prev, botResponse]);

      // Step 2: TTS (text-to-speech)
      const ttsRes = await axios.post(
        `${BASE_URL}/tts`,
        { text: botText, language: selectedLanguage },
        { responseType: "json" }
      );

      if (ttsRes.data.audio_url) {
        const fullAudioUrl = `${BASE_URL}${ttsRes.data.audio_url}`;
        setAudioUrl(fullAudioUrl);
        playAudio(fullAudioUrl);
      }
    } catch (error) {
      console.error("Chat/TTS Error:", error);
      const botResponse = { text: "⚠️ Sorry, something went wrong.", isUser: false };
      setMessages((prev) => [...prev, botResponse]);
    }

    setInput("");
    resetTranscript();
  };

  // 🎤 Toggle speech input
  const toggleListening = () => {
    if (listening) SpeechRecognition.stopListening();
    else SpeechRecognition.startListening({ continuous: true, language: selectedLanguage });
  };

  // ⌨️ Enter key send
  const handleKeyPress = (e) => {
    if (e.key === "Enter") sendMessage();
  };

  if (!browserSupportsSpeechRecognition) {
    return <div>Your browser doesn’t support speech recognition.</div>;
  }

  if (!userId) {
    return <Login onLogin={handleLogin} />;
  }

  return (
    <div className="app">
      <header className="header">
        <h1>🇮🇳 Indian Census Chatbot</h1>
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 12 }}>
          <span>Signed in as: <strong>{userId}</strong></span>
          <button onClick={handleLogout}>Logout</button>
        </div>

        <div className="language-selector">
          <label htmlFor="language">Language:</label>
          <select
            id="language"
            value={selectedLanguage}
            onChange={(e) => setSelectedLanguage(e.target.value)}
          >
            {languages.map((lang) => (
              <option key={lang.code} value={lang.code}>
                {lang.name}
              </option>
            ))}
          </select>
        </div>
      </header>

      <div className="chat-container">
        <div className="sidebar" style={{ width: 280, padding: 12, borderRight: "1px solid #ddd" }}>
          <h3>Previous queries</h3>
          {histories.length === 0 ? (
            <div style={{ color: "#666" }}>No previous queries</div>
          ) : (
            <div className="history-list" style={{ maxHeight: 300, overflow: "auto" }}>
              {histories.map((s) => (
                <div key={s.session_id} style={{ marginBottom: 12 }}>
                  <div style={{ fontWeight: 600, fontSize: 12 }}>Session: {s.session_id.slice(0,8)}...</div>
                  <ul style={{ marginTop: 6 }}>
                    {s.history.map((h, idx) => (
                      <li key={idx} style={{ fontSize: 12 }}>
                        {h.user}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          )}
        </div>
        <div className="messages">
          {messages.length === 0 ? (
            <div className="welcome">👋 Ask about Indian Census data in any language!</div>
          ) : (
            messages.map((msg, index) => (
              <div key={index} className={`message ${msg.isUser ? "user" : "bot"}`}>
                {msg.text}
              </div>
            ))
          )}
          <div ref={messagesEndRef} />
        </div>

        <div className="input-container">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="Type your question..."
            className="input-field"
          />
          <button onClick={() => sendMessage()} className="send-btn">
            Send
          </button>
          <button
            onClick={toggleListening}
            className={`mic-btn ${listening ? "listening" : ""}`}
          >
            {listening ? "🛑 Stop" : "🎤 Speak"}
          </button>
        </div>
      </div>

      {audioUrl && <audio ref={audioRef} src={audioUrl} autoPlay controls />}
    </div>
  );
};

export default App;
