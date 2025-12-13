from fastapi import FastAPI
import firebase_admin
import os, json
from firebase_admin import credentials, db, messaging
import requests
from datetime import datetime, timedelta


app = FastAPI()


# ----------------------------------------------------------
# 1. LOAD ENV VARIABLES FROM RENDER
# ----------------------------------------------------------

firebase_credentials_str = os.environ["FIREBASE_CREDENTIALS"]
firebase_credentials = json.loads(firebase_credentials_str)

databaseURL = os.environ["FIREBASE_DB_URL"]
WEATHER_API_KEY = os.environ["WEATHER_API_KEY"]
WEATHER_API_URL = os.environ["WEATHER_API_URL"]

# ----------------------------------------------------------
# 2. INITIALIZE FIREBASE USING ENV VARIABLES
# ----------------------------------------------------------

cred = credentials.Certificate(firebase_credentials)

if not firebase_admin._apps:
    firebase_admin.initialize_app(cred, {
        "databaseURL": databaseURL
    })

# ----------------------------------------------------------
# SEND PUSH NOTIFICATION TO USER
# ----------------------------------------------------------
def send_push(uid: str, title: str, body: str):
    token = db.reference(f"Users/{uid}/fcmToken").get()

    if not token:
        return
    
    message = messaging.Message(
        notification=messaging.Notification(title=title, body=body),
        token=token
    )
    messaging.send(message)


# ----------------------------------------------------------
# SAVE NOTIFICATION IN FIREBASE
# ----------------------------------------------------------
def save_notification(uid, title, message, notif_type, lang):
    notif_ref = db.reference(f"Users/{uid}/notifications").push()
    notif_ref.set({
        "title": title,
        "message": message,
        "timestamp": int(datetime.now().timestamp() * 1000),
        "type": notif_type,
        "lang": lang,
        "read": False
    })


# ----------------------------------------------------------
# WEATHER FETCH FUNCTION
# ----------------------------------------------------------
def get_weather(city):
    url = f"{WEATHER_API_URL}?q={city}&appid={WEATHER_API_KEY}&units=metric"
    res = requests.get(url).json()

    temp = res["main"]["temp"]
    humidity = res["main"]["humidity"]
    rain_chance = 80 if "rain" in res else 20
    return temp, humidity, rain_chance


# ----------------------------------------------------------
# WEATHER ALERT ENGINE
# ----------------------------------------------------------
def process_weather(uid, lang, city):
    temp, humidity, rain = get_weather(city)

    alerts = []

    if rain > 60:
        alerts.append({
            "en": "🌧 Rain expected soon. Protect your crops.",
            "kn": "🌧 ಶೀಘ್ರದಲ್ಲೇ ಮಳೆ ಸಾಧ್ಯತೆ. ನಿಮ್ಮ ಬೆಳೆಗಳನ್ನು ರಕ್ಷಿಸಿ."
        })

    if temp > 34:
        alerts.append({
            "en": "🔥 High temperature! Provide irrigation.",
            "kn": "🔥 ಹೆಚ್ಚು ತಾಪಮಾನ! ನೀರಾವರಿ ನೀಡಿ."
        })

    if humidity > 75:
        alerts.append({
            "en": "🐛 High pest risk due to humidity.",
            "kn": "🐛 ಆರ್ದ್ರತೆಯಿಂದ ಕೀಟದ ಅಪಾಯ."
        })

    for alert in alerts:
        message = alert[lang]
        title = "Weather Alert" if lang == "en" else "ಹವಾಮಾನ ಎಚ್ಚರಿಕೆ"

        save_notification(uid, title, message, "weather", lang)
        send_push(uid, title, message)


# ----------------------------------------------------------
# FERTILIZER REMINDER ENGINE
# ----------------------------------------------------------
def process_fertilizer(uid, logs, lang):
    for cropKey in logs:
        for logId, entry in logs[cropKey].items():
            if entry.get("subActivity") == "nutrient_management":
                app = entry["applications"][0]

                last = datetime.strptime(app["applicationDate"], "%Y-%m-%d")
                next_date = last + timedelta(days=app["gapDays"])

                if datetime.now().date() >= next_date.date():
                    title = "Fertilizer Alert" if lang == "en" else "ಗೊಬ್ಬರ ಎಚ್ಚರಿಕೆ"
                    msg = "Time for the next fertilizer dose." if lang == "en" else "ಮುಂದಿನ ಗೊಬ್ಬರದ ಡೋಸ್ ಸಮಯ ಬಂದಿದೆ."

                    save_notification(uid, title, msg, "fertilizer", lang)
                    send_push(uid, title, msg)


# --------------------------
#  IRRIGATION REMINDER ENGINE
# --------------------------
def process_irrigation_alert(uid, logs, lang):
    for cropKey in logs:
        cropLogs = logs[cropKey]

        for logId in cropLogs:
            entry = cropLogs[logId]

            if entry.get("subActivity") == "water_management":
                last = datetime.strptime(entry["lastIrrigationDate"], "%Y-%m-%d")
                next_irrigation = last + timedelta(days=entry["frequencyDays"])

                if datetime.now().date() >= next_irrigation.date():
                    msg = "Irrigation needed today." if lang == "en" else "ಇಂದು ನೀರಾವರಿ ಅಗತ್ಯವಿದೆ."
                    title = "Irrigation Alert" if lang == "en" else "ನೀರಾವರಿ ಎಚ್ಚರಿಕೆ"

                    save_notification(uid, title, msg, "irrigation", lang)
                    send_push(uid, title, msg)

@app.get("/test/{uid}")
def test_notification(uid: str):
    title = "Test Notification"
    msg = "If you see this in Firebase, backend works."

    save_notification(uid, title, msg, "test", "en")
    send_push(uid, title, msg)

    return {"status": "Notification test sent"}

# --------------------------
#  MAIN SCHEDULER ENDPOINT
# --------------------------
@app.get("/run-alerts")
def run_alerts():

    users = db.reference("Users").get()

    for uid, user in users.items():
        lang = user.get("preferredLanguage", "en")
        city = user.get("location", "Sirsi")
        logs = user.get("farmActivityLogs", {})

        process_weather_alert(uid, lang, city)
        process_fertilizer_alert(uid, logs, lang)
        process_irrigation_alert(uid, logs, lang)

    return {"status": "alerts processed successfully!"}


