# 🧠 Mind-state-siborg

Mind-state-siborg is a multimodal **emotional support companion system** that combines physiological signals, facial expressions, voice input, and psychological assessment to provide stress-aware insights and empathetic support.

---

## 🚀 Overview

Mind-state-siborg is designed as a **privacy-first digital wellness system** that enables users to perform a guided “check-in” using multiple data sources.

The system analyzes:

* Facial expressions
* Voice recordings
* Physiological signals (EDA, HRV, Temperature, Accelerometer)
* DASS-21 psychological questionnaire

These inputs are fused using intelligent algorithms to generate:

* Stress score
* Stress classification (context-aware)
* Personalized AI companion responses

---

## ✨ Key Features

### 🧠 Multimodal Stress Detection

* Combines multiple inputs for higher accuracy
* Reduces bias compared to single-source systems

### 📡 Physiological Signal Integration

* Real-time sensor data (ESP32-based)
* EDA, HRV, temperature, motion tracking

### 📸 Facial Expression Analysis

* CNN-based emotion detection model
* Detects stress-related facial cues

### 🎤 Voice Emotion Analysis

* Audio processing using MFCC features
* Deep learning model for stress inference
* Pitch/tone heuristic blended with model output

### ⚡ Live Reaction (New)

* During voice recording, the UI shows real-time mic intensity
* Mind-state-siborg gives gentle live supportive reactions while user speaks

### 🧠 Memory Tracking (New)

* Each check-in is tracked by `user_id`
* Backend stores recent check-ins and trend summary
* Report now shows check-in count, average score, last score, and trend

### 🎬 Production Flow (Updated)

* Full guided flow enforced (sensor → photo → voice → DASS → reveal)
* DASS remains part of the required check-in journey
* Consistent user journey for real-world deployment

### 📝 Psychological Assessment (DASS-21)

* Standardized questionnaire
* Provides mental health context

### 🤖 Mind-state-siborg Companion (LLM Integration)

* Empathy-first response behavior
* Short, natural, human-like responses (1–3 sentences)
* Emotion-adaptive tone (distressed, mild stress, calm, happy)
* No diagnosis or medical advice output

### 🔊 Voice Feedback (TTS)

* AI-generated spoken suggestions using Deepgram

### 🌐 Web-Based Interface

* Clean, modern UI deployed on Netlify
* Fully responsive and interactive

---

## 🏗️ System Architecture

```
User Input →
    ├── Facial Image → CNN Model
    ├── Audio Input → Audio Model
    ├── DASS-21 → ML Model
    ├── Sensor Data → Physiological Model
            ↓
    Multimodal Fusion Algorithm
            ↓
    Stress Score + Classification
            ↓
    LLM (Groq API)
            ↓
    Personalized Suggestions + Voice Output
```

---

## 🛠️ Tech Stack

### Frontend

* HTML, CSS, JavaScript
* Responsive UI
* Web APIs (Camera, Mic, Bluetooth)

### Backend

* FastAPI (Python)
* REST API for processing

### Machine Learning

* TensorFlow / Keras
* OpenCV (image processing)
* Librosa (audio processing)
* Scikit-learn (scaling & preprocessing)

### AI & APIs

* Groq API (LLM)
* Deepgram (Speech-to-Text + Text-to-Speech)

### Hardware

* ESP32 (sensor interface)
* Physiological sensors (EDA, HRV, Temp, ACC)

### Deployment

* Frontend: Static hosting (Netlify/Vercel/GitHub Pages)
* Backend: FastAPI host (local server / cloud)

---

## ⚙️ Setup Instructions

### 1. Clone Repository

```bash
git clone https://github.com/<your-username>/Mind-state-siborg.git
cd Mind-state-siborg
```

### 2. Create Environment File

```bash
GROQ_API_KEY=your_api_key
DEEPGRAM_API_KEY=your_api_key
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Run Backend

```bash
uvicorn main:app --reload
```

### 5. Frontend Backend URL

The frontend default API endpoint is local:

```js
http://127.0.0.1:8000/analyze
```

If deployed, set one of these before app init:

- `window.MIND_STATE_SIBORG_BACKEND_BASE_URL` (example: `https://your-backend.com`)
- or `window.MIND_STATE_SIBORG_BACKEND_URL` (full analyze endpoint)

Backend production environment variables:

- `APP_ENV=production`
- `CORS_ORIGINS=https://your-frontend-domain.com`

### 6. New Endpoints

- `GET /ai-questions` → AI-generated voice check-in prompts
- `POST /analyze` → full multimodal analysis + memory update
- `GET /memory/{user_id}` → latest memory summary/history

---

## 📦 Models

Trained models are not included in this repository due to size constraints and ongoing research work.
Add your own trained models inside `BACKEND/saved_models/`.

Required model files:

- `facial_model.h5`
- `audio_model.h5`
- `dass211_model.h5`
- `physio_model.h5`
- `dass211_scaler.pkl`
- `physio_scaler.pkl`

---

## ✅ What You Need To Provide (Important)

To fully complete and run at production level, you need to provide:

1. **API keys**
        - `GROQ_API_KEY` (for AI questions + companion replies)
        - `DEEPGRAM_API_KEY` (for transcription + coach voice output)

2. **Model artifacts** in `BACKEND/saved_models/`
        - all `.h5` and `.pkl` files listed above

3. **Backend deployment URL**
        - Set `window.MIND_STATE_SIBORG_BACKEND_BASE_URL` in frontend if not local

4. **HTTPS deployment** (required for browser camera/mic/Bluetooth permissions)

5. **Your branding/contact**
        - update email + LinkedIn placeholders in this README and privacy page

6. **Optional hardware for full multimodal production setup**
        - ESP32 firmware flashed
        - BLE device name: `Mind-state-siborg_Device`

---

## 🔐 Security & Privacy

* No API keys stored in repository
* Uses environment variables
* No user data stored permanently
* Designed as a privacy-first system

Modern AI systems emphasize privacy and secure handling of user data, especially in sensitive applications like emotional wellness.

---

## 🎯 Use Cases

* Mental health monitoring
* Student stress analysis
* Workplace well-being systems
* Smart healthcare applications

---

## 📌 Project Type

Research Project

---

## 🙏 Acknowledgements

* Open-source ML libraries
* Deepgram API
* Groq LLM API

---

## 📬 Contact

For queries or collaboration:
Email : your-email@example.com
LinkedIn : https://www.linkedin.com/in/your-profile/

---

## ⭐ Future Improvements

* Mobile app integration
* Real-time wearable sync
* Improved model accuracy
* Personalized long-term tracking

---

