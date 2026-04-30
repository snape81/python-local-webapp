from flask import Flask, jsonify, request
import random
import time

app = Flask(__name__)

state = {
    "temperature": 22.5,
    "humidity": 50,
    "enabled": True
}

@app.route("/api/status")
def status():
    # Simula variazione sensori
    state["temperature"] += random.uniform(-0.5, 0.5)
    state["humidity"] += random.uniform(-1, 1)

    return jsonify({
        "timestamp": time.time(),
        "sensors": {
            "temperature": round(state["temperature"], 2),
            "humidity": round(state["humidity"], 2)
        },
        "enabled": state["enabled"]
    })

@app.route("/api/config", methods=["POST"])
def config():
    data = request.json

    if "enabled" in data:
        state["enabled"] = data["enabled"]

    return jsonify({
        "ok": True,
        "new_state": state
    })

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=True)