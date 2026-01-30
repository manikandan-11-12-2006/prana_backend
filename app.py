import os
import smtplib
from email.message import EmailMessage
from urllib.parse import quote

import joblib
import numpy as np
from dotenv import load_dotenv
from flask import Flask, request, jsonify, Response, send_from_directory
from flask_cors import CORS

from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

# -------------------------------
# Load environment variables
# -------------------------------
load_dotenv()

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(BASE_DIR, "models")

# -------------------------------
# ENV SETTINGS
# -------------------------------
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_FROM = os.getenv("TWILIO_FROM")   # +1xxxx
PUBLIC_URL = os.getenv("PUBLIC_URL")     # https://yourapp.onrender.com

twilio_client = None
if all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM, PUBLIC_URL]):
    twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# -------------------------------
# PWA / FRONTEND ROUTES
# -------------------------------
@app.route("/")
def ui():
    return send_from_directory(BASE_DIR, "index.html")

@app.route("/manifest.json")
def manifest():
    return send_from_directory(BASE_DIR, "manifest.json")

@app.route("/sw.js")
def sw():
    return send_from_directory(BASE_DIR, "sw.js")

@app.route("/logo.png")
def logo():
    return send_from_directory(BASE_DIR, "logo.png")

@app.route("/n_logo.png")
def nlogo():
    return send_from_directory(BASE_DIR, "n_logo.png")

@app.route("/s.png")
def spng():
    return send_from_directory(BASE_DIR, "s.png")

@app.route("/health")
def health():
    return jsonify({"ok": True, "message": "Nayaruvi backend running ✅"})

# -------------------------------
# Helpers
# -------------------------------
def to_e164_india(phone: str) -> str:
    """
    Accepts '8925137065', '+918925137065', '91xxxxxxxxxx' and returns E.164 '+91xxxxxxxxxx'.
    """
    if not phone:
        return phone
    p = phone.strip().replace(" ", "").replace("-", "")
    if p.startswith("+"):
        return p
    if len(p) == 12 and p.startswith("91") and p.isdigit():
        return "+" + p
    if len(p) == 10 and p.isdigit():
        return "+91" + p
    return p

def require_email_env():
    if not all([EMAIL_USER, EMAIL_PASS]):
        return False
    return True

def require_twilio_env():
    return twilio_client is not None and all([TWILIO_FROM, PUBLIC_URL])

# -------------------------------
# Registration Email
# -------------------------------
@app.route("/send-email", methods=["POST"])
def send_email():
    if not require_email_env():
        return jsonify({"success": False, "error": "EMAIL_USER / EMAIL_PASS not set in Render env"}), 500

    data = request.get_json() or {}
    name = data.get("name")
    email = data.get("email")
    pincode = data.get("pincode")

    if not all([name, email, pincode]):
        return jsonify({"success": False, "error": "Missing fields"}), 400

    try:
        msg = EmailMessage()
        msg["Subject"] = "Nayaruvi – Air Quality Alert Registration Successful"
        msg["From"] = EMAIL_USER
        msg["To"] = email
        msg.set_content(f"""
Dear {name},

✅ You have been successfully registered for Nayaruvi Air Quality Alerts.

📍 Registered PIN Code: {pincode}

You will now receive alerts whenever air quality in your area becomes unsafe.

🌱 Stay informed. Stay safe.

Regards,
Team Nayaruvi
        """)

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_USER, EMAIL_PASS)
            server.send_message(msg)

        return jsonify({"success": True, "message": "Registration email sent"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# -------------------------------
# Send Current AQI Status Email
# -------------------------------
@app.route("/send-aqi-status", methods=["POST"])
def send_aqi_status():
    if not require_email_env():
        return jsonify({"success": False, "error": "EMAIL_USER / EMAIL_PASS not set in Render env"}), 500

    data = request.get_json() or {}
    email = data.get("email")
    location = data.get("location")
    aqi = data.get("aqi")
    status = data.get("status")
    advice = data.get("advice")

    if not all([email, location, aqi, status, advice]):
        return jsonify({"success": False, "error": "Missing AQI data"}), 400

    try:
        msg = EmailMessage()
        msg["Subject"] = "Nayaruvi – Live Air Quality Status Update"
        msg["From"] = EMAIL_USER
        msg["To"] = email
        msg.set_content(f"""
Dear Citizen,

🌍 Nayaruvi – Real-Time Air Quality Update

📍 Location : {location}
📊 AQI Value : {aqi}
⚠ AQI Status: {status}

🛡 Health Advisory:
{advice}

Regards,
Team Nayaruvi
        """)

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_USER, EMAIL_PASS)
            server.send_message(msg)

        return jsonify({"success": True, "message": "AQI email sent successfully"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# -------------------------------
# Twilio Voice (TwiML)
# -------------------------------
@app.route("/twilio-voice")
def twilio_voice():
    message = request.args.get("msg", "Air quality warning from Nayaruvi.")
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say>{message}</Say>
</Response>
"""
    return Response(xml, mimetype="text/xml")

def make_twilio_call(to_number: str, message: str) -> str:
    twiml_url = f"{PUBLIC_URL}/twilio-voice?msg={quote(message)}"
    call = twilio_client.calls.create(
        to=to_number,
        from_=TWILIO_FROM,
        url=twiml_url
    )
    return call.sid

@app.route("/call-user", methods=["POST"])
def call_user():
    if not require_twilio_env():
        return jsonify({
            "status": "failed",
            "error": "Twilio env vars not set (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM, PUBLIC_URL)"
        }), 500

    data = request.get_json() or {}
    phone = data.get("phone")
    city = data.get("location", "your area")
    aqi = data.get("aqi", "unknown")

    if not phone:
        return jsonify({"success": False, "error": "phone is required"}), 400

    phone_e164 = to_e164_india(phone)
    message = f"Warning. Air quality in {city} is dangerous. Current AQI is {aqi}. Please wear a mask and avoid outdoor activity. This alert is from Nayaruvi."

    try:
        sid = make_twilio_call(phone_e164, message)
        return jsonify({"status": "calling", "twilio_call_sid": sid, "to": phone_e164})
    except TwilioRestException as e:
        return jsonify({
            "status": "failed",
            "error": e.msg,
            "code": e.code,
            "more_info": e.more_info,
            "to": phone_e164
        }), 400
    except Exception as e:
        return jsonify({"status": "failed", "error": str(e), "to": phone_e164}), 500

# -------------------------------
# ML MODELS (AQI Prediction)
# -------------------------------
def load_models():
    models = {}

    # required ones
    models["2h"] = joblib.load(os.path.join(MODELS_DIR, "aqi_2h.pkl"))
    models["6h"] = joblib.load(os.path.join(MODELS_DIR, "aqi_6h.pkl"))
    models["24h"] = joblib.load(os.path.join(MODELS_DIR, "aqi_24h.pkl"))
    models["7d"] = joblib.load(os.path.join(MODELS_DIR, "aqi_7d.pkl"))

    # optional 3h if exists
    p3 = os.path.join(MODELS_DIR, "aqi_3h.pkl")
    models["3h"] = joblib.load(p3) if os.path.exists(p3) else None

    return models

try:
    MODELS = load_models()
except Exception as e:
    # Don't crash the whole server if models fail; show error in /predict-aqi
    MODELS = {}
    MODEL_LOAD_ERROR = str(e)
else:
    MODEL_LOAD_ERROR = None

latest_aqi = None

@app.route("/store-aqi", methods=["POST"])
def store_aqi():
    global latest_aqi
    data = request.get_json() or {}
    latest_aqi = data.get("aqi")
    return jsonify({"status": "AQI stored", "aqi": latest_aqi})

@app.route("/predict-aqi", methods=["GET", "POST"])
def predict_aqi():
    if MODEL_LOAD_ERROR:
        return jsonify({"success": False, "error": f"Model load failed: {MODEL_LOAD_ERROR}"}), 500

    if not MODELS:
        return jsonify({"success": False, "error": "Models not loaded"}), 500

    horizon = request.args.get("horizon")
    if horizon is None and request.is_json:
        horizon = (request.get_json() or {}).get("horizon")

    if latest_aqi is None:
        return jsonify({"success": False, "error": "No AQI data yet. Call /store-aqi first"}), 400

    if horizon not in MODELS or MODELS[horizon] is None:
        return jsonify({"success": False, "error": f"Invalid horizon: {horizon}. Use 2h, 3h, 6h, 24h, 7d"}), 400

    try:
        model = MODELS[horizon]
        # Make feature vector size match model feature count
        n = getattr(model, "n_features_in_", 1)
        X = np.array([[float(latest_aqi)] * int(n)], dtype=float)
        pred = float(model.predict(X)[0])

        return jsonify({
            "success": True,
            "horizon": horizon,
            "current_aqi": latest_aqi,
            "predicted_aqi": round(pred, 2),
            "model": "XGBoost Multi-Horizon"
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# -------------------------------
# Run Server (Render-ready)
# -------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
