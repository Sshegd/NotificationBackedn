from fastapi import FastAPI
import firebase_admin
from firebase_admin import credentials, db, messaging
import requests
from datetime import datetime, timedelta

# --------------------------
#  INIT FIREBASE
# --------------------------
cred = credentials.Certificate("credentials.json")
firebase_admin.initialize_app(cred, {
    "databaseURL": "https://krishisakhi-fc477-default-rtdb.firebaseio.com"
})

app = FastAPI()


# --------------------------
#  UTILITY: PUSH NOTIFICATION
# --------------------------
def send_push(uid: str, title: str, body: str):
    token_ref = db.reference(f"Users/{uid}/fcmToken").get()
    if not token_ref:
        return False

    message = messaging.Message(
        notification=messaging.Notification(title=title, body=body),
        token=token_ref
    )
    response = messaging.send(message)
    return response


# --------------------------
#  UTILITY: SAVE NOTIF NODE
# --------------------------
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


# --------------------------
#  WEATHER API FETCHER
# --------------------------
def get_weather(city):
    API_KEY = "YOUR_OPENWEATHER_API_KEY"
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={API_KEY}&units=metric"
    res = requests.get(url).json()

    temp = res["main"]["temp"]
    humidity = res["main"]["humidity"]
    rain_chance = 80 if "rain" in res else 10

    return temp, humidity, rain_chance


# --------------------------
#  WEATHER ALERT ENGINE
# --------------------------
def process_weather_alert(uid, lang, city):
    temp, humidity, rain = get_weather(city)

    alerts = []

    if rain > 60:
        alerts.append({
            "en": "🌧 Rain expected. Protect your crops.",
            "kn": "🌧 ಮಳೆ ಸಾಧ್ಯತೆ. ನಿಮ್ಮ ಬೆಳೆಗಳನ್ನು ರಕ್ಷಿಸಿ."
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

    # Save + notify
    for alert in alerts:
        msg = alert[lang]
        title = "Weather Alert" if lang == "en" else "ಹವಾಮಾನ ಎಚ್ಚರಿಕೆ"

        save_notification(uid, title, msg, "weather", lang)
        send_push(uid, title, msg)


# --------------------------
#  FERTILIZER REMINDER ENGINE
# --------------------------
def process_fertilizer_alert(uid, logs, lang):
    for cropKey in logs:
        cropLogs = logs[cropKey]

        for logId in cropLogs:
            entry = cropLogs[logId]

            if entry.get("subActivity") == "nutrient_management":
                app = entry["applications"][0]
                last_date = datetime.strptime(app["applicationDate"], "%Y-%m-%d")
                next_date = last_date + timedelta(days=app["gapDays"])

                if datetime.now().date() >= next_date.date():
                    msg = "Time for next fertilizer dose." if lang == "en" else "ಮುಂದಿನ ಗೊಬ್ಬರದ ಡೋಸ್ ಸಮಯ ಬಂದಿದೆ."
                    title = "Fertilizer Alert" if lang == "en" else "ಗೊಬ್ಬರ ಎಚ್ಚರಿಕೆ"

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
