# main.py - Your Local FastAPI Backend Server (REFACTORED LOGIC)
import base64
import re
import uvicorn
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import numpy as np
import pandas as pd
import joblib
import tensorflow as tf
import cv2
import librosa
import json
import os
import requests
from pathlib import Path
import uuid
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple, Optional
from dotenv import load_dotenv

# --- Configuration ---
BASE_DIR = Path(__file__).parent.resolve()
ROOT_DIR = BASE_DIR.parent
load_dotenv(ROOT_DIR / ".env")
load_dotenv(BASE_DIR / ".env")
MODELS_DIR = Path(os.getenv("MODELS_DIR", str(BASE_DIR / "saved_models"))).resolve()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
MEMORY_FILE = BASE_DIR / "memory_store.json"
MAX_MEMORY_ITEMS = 20
APP_ENV = os.getenv("APP_ENV", "production").lower()
REQUIRE_MODELS = os.getenv("REQUIRE_MODELS", "false").lower() == "true"

def _parse_allowed_origins() -> List[str]:
    origins = os.getenv("CORS_ORIGINS", "https://mind-state-siborg.netlify.app")
    return [o.strip() for o in origins.split(",") if o.strip()]

ALLOWED_ORIGINS = _parse_allowed_origins()

MIND_STATE_SIBORG_SYSTEM_PROMPT = """
You are Mind-state-siborg, an emotionally intelligent AI companion designed to support users based on real-time multimodal data.

CORE BEHAVIOR RULES:
1. Always respond with empathy first.
2. Keep responses short, natural, and human-like.
3. Do not sound robotic or clinical.
4. Do not mention technical data unless necessary.
5. Focus on emotional support, not diagnosis.
6. Never give medical advice.
7. Adapt tone based on user's emotional state.

EMOTION HANDLING:
- If user is stressed/distressed: be calm, reassuring, grounding; suggest tiny actions.
- If mildly stressed: be supportive and encouraging; suggest light reset actions.
- If calm: be positive and engaging.
- If happy: match energy and celebrate.

OUTPUT STYLE:
- Use conversational tone.
- 1–3 sentences max.
- Optional gentle suggestion.
- Avoid long explanations.

SAFETY:
- If user sounds unsafe or in crisis, gently encourage reaching trusted people or local emergency support immediately.
""".strip()

# --- App Initialization ---
app = FastAPI()

# --- CORS Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=("*" not in ALLOWED_ORIGINS),
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Model Loading ---
def _load_keras_model(label: str, candidates: List[str]):
    for filename in candidates:
        path = MODELS_DIR / filename
        if not path.exists():
            continue
        try:
            model = tf.keras.models.load_model(path)
            print(f"✅ Loaded {label}: {path.name}")
            return model
        except Exception as e:
            print(f"⚠️ Failed loading {label} from {path.name}: {e}")
    print(f"⚠️ {label} not found in {MODELS_DIR}")
    return None


def _load_joblib_file(label: str, candidates: List[str]) -> Optional[Any]:
    for filename in candidates:
        path = MODELS_DIR / filename
        if not path.exists():
            continue
        try:
            obj = joblib.load(path)
            print(f"✅ Loaded {label}: {path.name}")
            return obj
        except Exception as e:
            print(f"⚠️ Failed loading {label} from {path.name}: {e}")
    print(f"⚠️ {label} not found in {MODELS_DIR}")
    return None


print(f"📦 Model search directory: {MODELS_DIR}")
facial_model = _load_keras_model("facial_model", ["facial_model.h5"])
audio_model = _load_keras_model("audio_model", ["audio_model.h5"])
dass21_model = _load_keras_model("survey_model", ["dass211_model.h5", "dass21_model.h5", "survey_model.h5"])
physio_model = _load_keras_model("physio_model", ["physio_model.h5"])

dass21_scaler = _load_joblib_file("survey_scaler", ["dass211_scaler.pkl", "dass21_scaler.pkl", "survey_scaler.pkl"])
physio_scaler = _load_joblib_file("physio_scaler", ["physio_scaler.pkl", "physiological_scaler.pkl"])

if all([facial_model, audio_model, dass21_model, physio_model, dass21_scaler, physio_scaler]):
    print("✅ All models and scalers loaded successfully.")
else:
    print("⚠️ Some model artifacts are missing. Backend will use hybrid fallback where needed.")

MODELS_READY = all([
    facial_model is not None,
    audio_model is not None,
    dass21_model is not None,
    physio_model is not None,
    dass21_scaler is not None,
    physio_scaler is not None,
])

INFERENCE_MODE = "ml-models" if MODELS_READY else "heuristic-fallback"

# --- Transcription Function ---
def transcribe_audio_with_deepgram(audio_file_path):
    if not DEEPGRAM_API_KEY:
        print("⚠️ Deepgram API key not found. Skipping transcription.")
        return "[Transcription Disabled: API key not set]"
    try:
        with open(audio_file_path, 'rb') as audio:
            headers = {'Authorization': f'Token {DEEPGRAM_API_KEY}', 'Content-Type': 'audio/wav'}
            url = "https://api.deepgram.com/v1/listen?model=nova-2&smart_format=true"
            response = requests.post(url, headers=headers, data=audio)
            response.raise_for_status()
            result = response.json()
            return result['results']['channels'][0]['alternatives'][0]['transcript']
    except Exception as e:
        print(f"❌ Deepgram Transcription Error: {e}")
        return "[Transcription failed due to an error]"

# --- Helper & Prediction Functions ---

# 🗑️ REMOVED: The confusing get_stress_confidence function is no longer needed.
def generate_deepgram_tts(text):
    if not DEEPGRAM_API_KEY:
        return None
    
    # Remove markdown like ** or * so the AI doesn't read them out loud
    clean_text = re.sub(r'[*_#]', '', text)
    
    url = "https://api.deepgram.com/v1/speak?model=aura-asteria-en"
    headers = {
        "Authorization": f"Token {DEEPGRAM_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {"text": clean_text}
    
    try:
        # Request the audio file from Deepgram
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        response.raise_for_status()
        
        # Convert the raw audio file into a Base64 text string to send to the frontend
        audio_b64 = base64.b64encode(response.content).decode('utf-8')
        return audio_b64
    except Exception as e:
        print(f"❌ Deepgram TTS Error: {e}")
        return None
def agreement_fusion(confidences):
    valid_confidences = [c for c in confidences if c != 0.5]
    if not valid_confidences: return 0.5
    if len(valid_confidences) == 1: return valid_confidences[0]
    M = len(valid_confidences)
    agree_scores = [sum(1 - abs(valid_confidences[i] - valid_confidences[j]) for j in range(M) if i != j) / (M - 1) for i in range(M)]
    sum_agree = sum(agree_scores)
    if sum_agree < 1e-9: return np.mean(valid_confidences)
    return float(np.sum(np.array(agree_scores) * np.array(valid_confidences)) / sum_agree)

# ✅ CHANGED: All predict functions now return a single float (stress probability).
def predict_facial(photo_path):
    if not facial_model:
        # Heuristic fallback: lower brightness + high texture variance can indicate strain.
        try:
            img = cv2.imread(str(photo_path))
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            brightness = float(np.mean(gray))
            contrast = float(np.std(gray))
            brightness_score = np.clip((140.0 - brightness) / 100.0, 0.0, 1.0)
            contrast_score = np.clip((contrast - 35.0) / 55.0, 0.0, 1.0)
            return float(0.6 * brightness_score + 0.4 * contrast_score)
        except Exception:
            return 0.5
    try:
        img = cv2.imread(str(photo_path))
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        resized = cv2.resize(gray, (48, 48))
        input_img = (resized / 255.0).reshape(1, 48, 48, 1)
        prediction = facial_model.predict(input_img, verbose=0)
        # The model outputs [P(Not Stressed), P(Stressed)], so we always return the second value.
        return float(prediction[0][1])
    except Exception as e:
        print(f"Facial prediction error: {e}"); return 0.5

def predict_audio(audio_file):
    if not audio_model:
        # Heuristic fallback delegates to voice tone stress estimator.
        return predict_voice_tone_stress(audio_file)
    try:
        y, sr = librosa.load(audio_file, sr=22050)
        mfccs = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=38)
        target_length = 98
        if mfccs.shape[1] < target_length:
            mfccs = np.pad(mfccs, ((0, 0), (0, target_length - mfccs.shape[1])))
        else:
            mfccs = mfccs[:, :target_length]
        mfccs = np.expand_dims(mfccs, axis=(0, -1))
        # The model directly outputs the stress probability.
        prediction = audio_model.predict(mfccs, verbose=0)[0][0]
        return float(prediction)
    except Exception as e:
        print(f"Audio prediction error: {e}"); return 0.5

def predict_voice_tone_stress(audio_file):
    """
    Heuristic score from voice tone dynamics (0 to 1).
    Higher score ~= higher stress tendency based on pitch variability + vocal energy.
    """
    try:
        y, sr = librosa.load(audio_file, sr=22050)
        if y is None or len(y) == 0:
            return 0.5

        # RMS energy (voice intensity)
        rms = librosa.feature.rms(y=y)[0]
        mean_rms = float(np.mean(rms)) if len(rms) else 0.0

        # Pitch estimation via piptrack
        pitches, mags = librosa.piptrack(y=y, sr=sr)
        f0_vals = []
        for t in range(pitches.shape[1]):
            idx = np.argmax(mags[:, t])
            f0 = pitches[idx, t]
            if 60 <= f0 <= 450:
                f0_vals.append(float(f0))

        if len(f0_vals) < 5:
            return 0.5

        pitch_std = float(np.std(f0_vals))
        pitch_var_score = min(max((pitch_std - 10.0) / 90.0, 0.0), 1.0)
        energy_score = min(max((mean_rms - 0.02) / 0.12, 0.0), 1.0)

        return float(0.65 * pitch_var_score + 0.35 * energy_score)
    except Exception as e:
        print(f"Voice tone prediction error: {e}")
        return 0.5

def predict_dass21(q_responses):
    if not all([dass21_model, dass21_scaler]):
        try:
            vals = np.array([float(r) for r in q_responses])
            # DASS-like 0..3 responses -> normalized stress tendency
            return float(np.clip(np.mean(vals) / 3.0, 0.0, 1.0))
        except Exception:
            return 0.5
    try:
        X = np.array([float(r) for r in q_responses]).reshape(1, -1)
        X_scaled = dass21_scaler.transform(X)
        # The model directly outputs the stress probability.
        pred_prob = dass21_model.predict(X_scaled, verbose=0)[0][0]
        return float(pred_prob)
    except Exception as e:
        print(f"DASS-21 prediction error: {e}"); return 0.5

def predict_physio_from_line(line):
    if not all([physio_model, physio_scaler]):
        # Heuristic fallback for BLE payload values.
        try:
            data = json.loads(line)
            eda = float(data.get("eda_uS", data.get("eda_raw", 0)))
            hrv = float(data.get("hrv_rmssd", data.get("bvp_ir_raw", 0)))
            temp = float(data.get("temp_c", 0))
            acc_x = float(data.get("acc_x_g", data.get("acc_x_raw", 0)))
            acc_y = float(data.get("acc_y_g", data.get("acc_y_raw", 0)))
            acc_z = float(data.get("acc_z_g", data.get("acc_z_raw", 0)))
            motion = float(np.sqrt(acc_x * acc_x + acc_y * acc_y + acc_z * acc_z))

            eda_score = np.clip((eda - 2.0) / 12.0, 0.0, 1.0)
            # Higher HRV generally means lower stress.
            hrv_score = np.clip((45.0 - hrv) / 45.0, 0.0, 1.0)
            temp_score = np.clip(abs(temp - 36.5) / 2.0, 0.0, 1.0)
            motion_score = np.clip((motion - 1.0) / 1.5, 0.0, 1.0)

            return float(0.4 * eda_score + 0.35 * hrv_score + 0.15 * temp_score + 0.1 * motion_score)
        except Exception:
            return 0.5
    try:
        data = json.loads(line)
        if all(value == 0 for value in data.values()):
            print("🧠 Detected dummy physiological data. Returning neutral 0.5 score.")
            return 0.5

        # Supports both raw training keys and frontend BLE payload keys.
        feature_names = ["eda_raw", "bvp_ir_raw", "temp_c", "acc_x_raw", "acc_y_raw", "acc_z_raw"]
        normalized = {
            "eda_raw": float(data.get("eda_raw", data.get("eda_uS", 0))),
            "bvp_ir_raw": float(data.get("bvp_ir_raw", data.get("hrv_rmssd", 0))),
            "temp_c": float(data.get("temp_c", 0)),
            "acc_x_raw": float(data.get("acc_x_raw", data.get("acc_x_g", 0))),
            "acc_y_raw": float(data.get("acc_y_raw", data.get("acc_y_g", 0))),
            "acc_z_raw": float(data.get("acc_z_raw", data.get("acc_z_g", 0))),
        }

        input_df = pd.DataFrame([[normalized[k] for k in feature_names]], columns=feature_names)
        input_scaled = physio_scaler.transform(input_df)
        # The model directly outputs the stress probability.
        prediction = physio_model.predict(input_scaled, verbose=0)[0][0]
        return float(prediction)
    except Exception as e:
        print(f"Physio prediction error: {e}"); return 0.5

def predict_question_heartbeat_stress(question_physio_payload: Any) -> Tuple[float, Dict[str, Any]]:
    """
    Uses calibration baseline + during-question heart dynamics.
    Returns (score_0_to_1, meta_info).
    """
    default_meta: Dict[str, Any] = {
        "used": False,
        "calibrated": False,
        "baseline_bpm": 0.0,
        "baseline_hrv": 0.0,
        "during_avg_bpm": 0.0,
        "during_avg_hrv": 0.0,
        "during_avg_spo2": 0.0,
        "samples": 0,
    }

    if not question_physio_payload:
        return 0.5, default_meta

    try:
        data_any: Any = json.loads(question_physio_payload) if isinstance(question_physio_payload, str) else question_physio_payload
        if not isinstance(data_any, dict):
            return 0.5, default_meta

        data: Dict[str, Any] = dict(data_any)
        baseline_raw = data.get("baseline", {})
        during_raw = data.get("during", {})
        baseline: Dict[str, Any] = baseline_raw if isinstance(baseline_raw, dict) else {}
        during: Dict[str, Any] = during_raw if isinstance(during_raw, dict) else {}

        calibrated = bool(data.get("calibrated", False))
        baseline_bpm = float(baseline.get("bpm", 0) or 0)
        baseline_hrv = float(baseline.get("hrv_rmssd", 0) or 0)
        during_avg_bpm = float(during.get("avg_bpm", 0) or 0)
        during_avg_hrv = float(during.get("avg_hrv", 0) or 0)
        during_avg_spo2 = float(during.get("avg_spo2", 0) or 0)
        samples = int(during.get("samples", 0) or 0)

        meta = {
            "used": samples >= 3,
            "calibrated": calibrated,
            "baseline_bpm": round(baseline_bpm, 1),
            "baseline_hrv": round(baseline_hrv, 1),
            "during_avg_bpm": round(during_avg_bpm, 1),
            "during_avg_hrv": round(during_avg_hrv, 1),
            "during_avg_spo2": round(during_avg_spo2, 1),
            "samples": samples,
        }

        if samples < 3:
            return 0.5, meta

        # If calibrated, compare against user baseline.
        if calibrated and baseline_bpm > 0:
            bpm_rise = max(0.0, during_avg_bpm - baseline_bpm)
            bpm_score = float(np.clip(bpm_rise / 30.0, 0.0, 1.0))
        else:
            bpm_score = float(np.clip((during_avg_bpm - 70.0) / 45.0, 0.0, 1.0))

        # HRV drop during questions may indicate stress load.
        if calibrated and baseline_hrv > 0:
            hrv_drop = max(0.0, baseline_hrv - during_avg_hrv)
            hrv_score = float(np.clip(hrv_drop / 25.0, 0.0, 1.0))
        else:
            hrv_score = float(np.clip((45.0 - during_avg_hrv) / 45.0, 0.0, 1.0))

        spo2_score = 0.0
        if during_avg_spo2 > 0:
            spo2_score = float(np.clip((96.0 - during_avg_spo2) / 8.0, 0.0, 1.0))

        score = float(0.5 * bpm_score + 0.4 * hrv_score + 0.1 * spo2_score)
        return score, meta
    except Exception as e:
        print(f"Question heartbeat scoring error: {e}")
        return 0.5, default_meta

def load_memory_store():
    if not MEMORY_FILE.exists():
        return {}
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Memory load error: {e}")
        return {}

def save_memory_store(store):
    try:
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(store, f, indent=2)
    except Exception as e:
        print(f"Memory save error: {e}")

def summarize_memory(entries):
    if not entries:
        return {"has_memory": False, "message": "No previous check-ins yet."}

    scores = [float(e.get("stress_score_percent", 0)) for e in entries]
    avg_score = round(float(np.mean(scores)))
    last_score = round(scores[-1])
    trend = "stable"
    if len(scores) >= 2:
        if scores[-1] > scores[0] + 6:
            trend = "up"
        elif scores[-1] < scores[0] - 6:
            trend = "down"

    return {
        "has_memory": True,
        "checkins": len(entries),
        "avg_stress_score": avg_score,
        "last_stress_score": last_score,
        "trend": trend,
    }

def build_memory_context(user_id):
    if not user_id:
        return "No memory available."

    store = load_memory_store()
    entries = store.get(user_id, [])
    if not entries:
        return "No previous check-ins for this user."

    summary = summarize_memory(entries)
    last = entries[-1]
    return (
        f"Previous check-ins: {summary.get('checkins', 0)}; "
        f"average stress score: {summary.get('avg_stress_score', 0)}%; "
        f"trend: {summary.get('trend', 'stable')}; "
        f"last score: {last.get('stress_score_percent', 0)}%."
    )

def append_user_memory(user_id, stress_score_percent, stress_level, voice_tone_score, transcript):
    if not user_id:
        return {"has_memory": False, "message": "No user id provided."}

    store = load_memory_store()
    history = store.get(user_id, [])
    history.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stress_score_percent": int(stress_score_percent),
        "stress_level": stress_level,
        "voice_tone_score": int(voice_tone_score),
        "transcript_preview": (transcript or "")[:160],
    })
    history = history[-MAX_MEMORY_ITEMS:]
    store[user_id] = history
    save_memory_store(store)
    return summarize_memory(history)

def get_llm_suggestion(stress_score_percent, user_paragraph, memory_context="No memory available."):
    # Fallback when no key is configured.
    if not GROQ_API_KEY:
        if stress_score_percent >= 70:
            return "I’m here with you. Let’s pause for one slow breath together, then take one small step at a time."
        if stress_score_percent >= 40:
            return "You’re handling a lot right now. A short break and a few deep breaths might help you reset a little."
        return "You seem fairly steady right now, and that’s a good sign. Keep going gently, one step at a time."

    if not user_paragraph or user_paragraph.startswith("["):
        user_paragraph = "No spoken message was provided in this check-in."

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    user_context = f"""
Session context:
- Stress score: {stress_score_percent}%
- User spoken context: {user_paragraph}
- Memory context: {memory_context}

Reply as Mind-state-siborg using the system rules.
""".strip()

    payload = {
        "model": "llama-3.1-8b-instant",
        "messages": [
            {"role": "system", "content": MIND_STATE_SIBORG_SYSTEM_PROMPT},
            {"role": "user", "content": user_context}
        ],
        "temperature": 0.6,
        "max_tokens": 120
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)

        if response.status_code != 200:
            print(f"❌ Groq API Error ({response.status_code}): {response.text}")
            response.raise_for_status()

        suggestion = response.json()['choices'][0]['message']['content'].strip()

        # Enforce concise output if model returns extra text.
        lines = [ln.strip() for ln in suggestion.splitlines() if ln.strip()]
        if len(lines) > 3:
            suggestion = " ".join(lines[:3])

        return suggestion
    except Exception as e:
        print(f"❌ Python Error in get_llm_suggestion: {e}")
        return "I’m here with you. We had a small connection issue, but you can take one slow breath and go gently right now."

def get_ai_checkin_questions():
    defaults = [
        "How are you feeling in this moment, honestly?",
        "What felt heaviest for you today?",
        "Did anything make you feel safe, calm, or supported today?",
        "What is one small thing you need right now?",
    ]

    if not GROQ_API_KEY:
        return defaults

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "llama-3.1-8b-instant",
        "messages": [
            {
                "role": "system",
                "content": "You are Mind-state-siborg. Create 4 short, empathetic, conversational check-in questions for voice answers. Keep each under 14 words. Return plain lines only, no numbering."
            },
            {
                "role": "user",
                "content": "Generate the questions now."
            }
        ],
        "temperature": 0.7,
        "max_tokens": 120
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=20)
        response.raise_for_status()
        text = response.json()['choices'][0]['message']['content']
        lines = [re.sub(r'^[-*\d.\s]+', '', ln).strip() for ln in text.splitlines() if ln.strip()]
        lines = [ln for ln in lines if ln.endswith('?') or len(ln.split()) >= 4]
        return lines[:4] if len(lines) >= 2 else defaults
    except Exception as e:
        print(f"AI question generation error: {e}")
        return defaults


@app.post("/analyze")
async def analyze_stress(
    dass_data: str = Form(...),
    physio_data: str = Form(...),
    image_file: UploadFile = File(...),
    audio_file: UploadFile = File(...),
    ai_questions: str = Form(None),
    question_physio_data: str = Form(None),
    user_id: str = Form(...)
):
    if not user_id or len(user_id.strip()) < 3:
        raise HTTPException(status_code=400, detail="Invalid user_id. A stable user identifier is required.")

    unique_id = uuid.uuid4()
    temp_dir = Path(tempfile.gettempdir())
    image_path = temp_dir / f"{unique_id}_image.jpg"
    audio_path = temp_dir / f"{unique_id}_audio.wav"

    try:
        with open(image_path, "wb") as f: f.write(await image_file.read())
        with open(audio_path, "wb") as f: f.write(await audio_file.read())
        
        transcribed_text = transcribe_audio_with_deepgram(audio_path)
        
        # ✅ CHANGED: Directly get the stress scores from each model.
        facial_score = predict_facial(image_path)
        audio_score = predict_audio(audio_path)
        voice_tone_score = predict_voice_tone_stress(audio_path)
        blended_audio_score = float(0.7 * audio_score + 0.3 * voice_tone_score)
        survey_score = predict_dass21(json.loads(dass_data)['responses'])
        physio_base_score = predict_physio_from_line(physio_data)
        question_heartbeat_score, heartbeat_meta = predict_question_heartbeat_stress(question_physio_data)
        if heartbeat_meta.get("used"):
            physio_score = float(0.65 * physio_base_score + 0.35 * question_heartbeat_score)
        else:
            physio_score = physio_base_score
        
        # ✅ CHANGED: The list of confidences is now a clean list of scores.
        confidences = [facial_score, blended_audio_score, survey_score, physio_score]
        
        fused_score = agreement_fusion(confidences)
        stress_score_percent = round(fused_score * 100)
        overall_label = "Stressed" if fused_score >= 0.5 else "Not Stressed"
        
        parsed_questions = []
        if ai_questions:
            try:
                maybe_list = json.loads(ai_questions)
                if isinstance(maybe_list, list):
                    parsed_questions = [str(q).strip() for q in maybe_list if str(q).strip()]
            except Exception:
                parsed_questions = []

        context_text = transcribed_text
        if ai_questions:
            question_text = " | ".join(parsed_questions) if parsed_questions else ai_questions
            context_text = f"Questions asked: {question_text}\nUser voice response: {transcribed_text}"

        if heartbeat_meta.get("used"):
            context_text += (
                f"\nQuestion-phase physiology: "
                f"calibrated={heartbeat_meta.get('calibrated')}, "
                f"baseline_bpm={heartbeat_meta.get('baseline_bpm')}, "
                f"during_avg_bpm={heartbeat_meta.get('during_avg_bpm')}, "
                f"baseline_hrv={heartbeat_meta.get('baseline_hrv')}, "
                f"during_avg_hrv={heartbeat_meta.get('during_avg_hrv')}"
            )

        memory_context = build_memory_context(user_id)
        llm_suggestion = get_llm_suggestion(stress_score_percent, context_text, memory_context)
        
        # --- NEW CODE: Generate the audio ---
        coach_audio_b64 = generate_deepgram_tts(llm_suggestion)
        memory_summary = append_user_memory(
            user_id=user_id,
            stress_score_percent=stress_score_percent,
            stress_level=overall_label,
            voice_tone_score=round(voice_tone_score * 100),
            transcript=transcribed_text,
        )
        
        # --- CHANGED: Add the audio to the dictionary ---
        return { 
            "stress_level": overall_label, 
            "stress_score_percent": stress_score_percent, 
            "transcribed_text": transcribed_text, 
            "llm_suggestion": llm_suggestion,
            "coach_audio_b64": coach_audio_b64,
            "voice_tone_score": round(voice_tone_score * 100),
            "memory_summary": memory_summary,
            "heartbeat_calibrated": heartbeat_meta.get("calibrated", False),
            "question_heartbeat_score": round(question_heartbeat_score * 100),
            "physio_base_score": round(physio_base_score * 100),
            "physio_final_score": round(physio_score * 100)
        }
    finally:
        if image_path.exists():
            image_path.unlink(missing_ok=True)
        if audio_path.exists():
            audio_path.unlink(missing_ok=True)

@app.get("/")
def read_root():
    return {"status": "Mind-state-siborg backend is running."}

@app.get("/health")
def health():
    configured_ok = bool(GROQ_API_KEY) and bool(DEEPGRAM_API_KEY)
    status = "ok"
    if REQUIRE_MODELS and not MODELS_READY:
        status = "degraded"
    elif not configured_ok:
        status = "degraded"

    return {
        "status": status,
        "env": APP_ENV,
        "require_models": REQUIRE_MODELS,
        "models_ready": MODELS_READY,
        "inference_mode": INFERENCE_MODE,
        "groq_key_configured": bool(GROQ_API_KEY),
        "deepgram_key_configured": bool(DEEPGRAM_API_KEY),
        "cors_origins": ALLOWED_ORIGINS,
    }

@app.get("/ai-questions")
def ai_questions():
    return {"questions": get_ai_checkin_questions()}

@app.get("/memory/{user_id}")
def user_memory(user_id: str):
    store = load_memory_store()
    entries = store.get(user_id, [])
    return {
        "user_id": user_id,
        "summary": summarize_memory(entries),
        "entries": entries[-7:]
    }

