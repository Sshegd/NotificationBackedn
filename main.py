from fastapi import FastAPI
import firebase_admin
import os, json, requests
from firebase_admin import credentials, db, messaging
from datetime import datetime, timedelta

app = FastAPI()

# ----------------------------------------------------------
# LOAD ENV VARIABLES
# ----------------------------------------------------------
cred_json = json.loads(os.environ["FIREBASE_CREDENTIALS"])
DB_URL = os.environ["FIREBASE_DB_URL"]
WEATHER_API_KEY = os.environ["WEATHER_API_KEY"]
WEATHER_API_URL = os.environ["WEATHER_API_URL"]

# ----------------------------------------------------------
# FIREBASE INIT
# ----------------------------------------------------------
if not firebase_admin._apps:
    firebase_admin.initialize_app(
        credentials.Certificate(cred_json),
        {"databaseURL": DB_URL}
    )

# ----------------------------------------------------------
# COMMON FUNCTIONS
# ----------------------------------------------------------
def save_notification(uid, title, msg, ntype, lang):
    db.reference(f"Users/{uid}/notifications").push().set({
        "title": title,
        "message": msg,
        "type": ntype,
        "lang": lang,
        "timestamp": int(datetime.now().timestamp() * 1000),
        "read": False
    })

def send_push(uid, title, msg):
    token = db.reference(f"Users/{uid}/fcmToken").get()
    if not token:
        return
    messaging.send(
        messaging.Message(
            notification=messaging.Notification(title=title, body=msg),
            token=token
        )
    )

def notify(uid, title, msg, ntype, lang):
    save_notification(uid, title, msg, ntype, lang)
    send_push(uid, title, msg)

# ----------------------------------------------------------
# WEATHER SERVICE
# ----------------------------------------------------------
def get_weather(city):
    res = requests.get(
        f"{WEATHER_API_URL}?q={city}&appid={WEATHER_API_KEY}&units=metric"
    ).json()
    return {
        "temp": res["main"]["temp"],
        "humidity": res["main"]["humidity"],
        "rain": "rain" in res
    }

# ----------------------------------------------------------
# WEATHER BASED ALERTS
# ----------------------------------------------------------
def weather_alerts(uid, lang, city):
    w = get_weather(city)

    if w["temp"] > 35:
        notify(uid,
            "Water Alert" if lang == "en" else "ನೀರಾವರಿ ಎಚ್ಚರಿಕೆ",
            "High temperature – irrigate crops today" if lang == "en"
            else "ಹೆಚ್ಚು ತಾಪಮಾನ – ಇಂದು ನೀರಾವರಿ ನೀಡಿ",
            "weather", lang)

    if not w["rain"] and w["temp"] < 32:
        notify(uid,
            "Spray Advisory" if lang == "en" else "ಸಿಂಪಡಣೆ ಸಲಹೆ",
            "Sunny weather – you can spray pesticide today" if lang == "en"
            else "ಸೂರ್ಯಪ್ರಕಾಶ – ಇಂದು ಕೀಟನಾಶಕ ಸಿಂಪಡಿಸಬಹುದು",
            "weather", lang)

    if w["humidity"] > 75:
        notify(uid,
            "Pest Risk Alert" if lang == "en" else "ಕೀಟ ಅಪಾಯ ಎಚ್ಚರಿಕೆ",
            "High humidity – pest and disease risk" if lang == "en"
            else "ಹೆಚ್ಚು ಆರ್ದ್ರತೆ – ಕೀಟ ಮತ್ತು ರೋಗ ಅಪಾಯ",
            "pest", lang)

# ----------------------------------------------------------
# ACTIVITY BASED ALERTS
# ----------------------------------------------------------
def activity_alerts(uid, logs, lang):
    today = datetime.now().date()

    for crop in logs.values():
        for entry in crop.values():

            # Fertilizer reminder
            if entry.get("subActivity") == "nutrient_management":
                app = entry["applications"][0]
                due = datetime.strptime(
                    app["applicationDate"], "%Y-%m-%d"
                ).date() + timedelta(days=app["gapDays"])

                if today >= due:
                    notify(uid,
                        "Fertilizer Reminder" if lang == "en" else "ಗೊಬ್ಬರ ಜ್ಞಾಪನೆ",
                        "Time for next fertilizer dose" if lang == "en"
                        else "ಮುಂದಿನ ಗೊಬ್ಬರದ ಡೋಸ್ ಸಮಯ ಬಂದಿದೆ",
                        "fertilizer", lang)

            # Water reminder
            if entry.get("subActivity") == "water_management":
                due = datetime.strptime(
                    entry["lastIrrigationDate"], "%Y-%m-%d"
                ).date() + timedelta(days=entry["frequencyDays"])

                if today >= due:
                    notify(uid,
                        "Irrigation Reminder" if lang == "en" else "ನೀರಾವರಿ ಜ್ಞಾಪನೆ",
                        "Irrigation required today" if lang == "en"
                        else "ಇಂದು ನೀರಾವರಿ ಅಗತ್ಯವಿದೆ",
                        "water", lang)

            # Pesticide schedule
            if entry.get("subActivity") == "pest_management":
                due = datetime.strptime(
                    entry["lastSprayDate"], "%Y-%m-%d"
                ).date() + timedelta(days=entry["sprayInterval"])

                if today >= due:
                    notify(uid,
                        "Pesticide Reminder" if lang == "en" else "ಕೀಟನಾಶಕ ಜ್ಞಾಪನೆ",
                        "Time for pesticide spray" if lang == "en"
                        else "ಕೀಟನಾಶಕ ಸಿಂಪಡಣೆ ಸಮಯ",
                        "pest", lang)

# ----------------------------------------------------------
# MAIN SCHEDULER
# ----------------------------------------------------------
@app.get("/run-alerts")
def run_alerts():
    users = db.reference("Users").get()

    for uid, user in users.items():
        lang = user.get("preferredLanguage", "en")
        city = user.get("location", "Sirsi")
        logs = user.get("farmActivityLogs", {})

        weather_alerts(uid, lang, city)
        activity_alerts(uid, logs, lang)

    return {"status": "alerts sent"}

# ----------------------------------------------------------
# TEST ENDPOINT
# ----------------------------------------------------------
@app.get("/test/{uid}")
def test(uid: str):
    notify(uid, "Test", "Backend working successfully", "test", "en")
    return {"status": "ok"}
