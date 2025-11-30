import React, { useState, useRef, useEffect } from "react";
import axios from "axios";
import SpeechRecognition, { useSpeechRecognition } from "react-speech-recognition";
import "./App.css";
import Login from "./Login";


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



export default App;
