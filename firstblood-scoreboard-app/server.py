# server.py (fixed TypeError with safe int conversion)
from flask import Flask, render_template, request
from flask_socketio import SocketIO
import threading

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# Global state
current_fb_data = None
showing_first_blood = False
latest_scoreboard = []  # Raw scoreboard from plugin
team_first_bloods = {}  # team_name -> count of first bloods

@app.route('/', methods=["GET"])
def home():
    global current_fb_data
    if showing_first_blood and current_fb_data:
        return render_template("firstblood.html", **current_fb_data)
    else:
        enhanced_scoreboard = []
        for entry in latest_scoreboard:
            entry_copy = entry.copy()
            score_val = entry_copy.get("score")
            if score_val is None or score_val == "null" or score_val == "":
                entry_copy["score"] = 0
            else:
                try:
                    entry_copy["score"] = int(score_val)
                except (ValueError, TypeError):
                    entry_copy["score"] = 0
            entry_copy["num_bloods"] = team_first_bloods.get(entry_copy["team"], 0)
            enhanced_scoreboard.append(entry_copy)
        return render_template("scoreboard.html", scoreboard=enhanced_scoreboard)

@app.route('/api/solve', methods=["POST"])
def solve():
    global current_fb_data, showing_first_blood, team_first_bloods
    data = request.get_json()
    if isinstance(data, list):
        data = data[0]

    if data.get("first_blood") == 1:
        team_name = data.get("team")
        team_first_bloods[team_name] = team_first_bloods.get(team_name, 0) + 1

        current_fb_data = {
            "team": team_name,
            "challenge": data.get("challenge")
        }
        showing_first_blood = True
        print(f"First blood by {team_name} on {current_fb_data['challenge']}")
        socketio.emit('new_first_blood', current_fb_data)
        threading.Timer(15.0, reset_first_blood).start()

    return {"status": "ok"}

@app.route('/api/scoreboard', methods=["POST"])
def scoreboard():
    global latest_scoreboard
    data = request.get_json()
    # Safely fix scores and add bloods for live updates
    for entry in data:
        score_val = entry.get("score")
        if score_val is None or score_val == "null" or score_val == "":
            entry["score"] = 0
        else:
            try:
                entry["score"] = int(score_val)
            except (ValueError, TypeError):
                entry["score"] = 0
        entry["num_bloods"] = team_first_bloods.get(entry["team"], 0)
    latest_scoreboard = data
    socketio.emit('scoreboard_update', data)
    return {"status": "ok"}

def reset_first_blood():
    global showing_first_blood
    showing_first_blood = False

if __name__ == "__main__":
    socketio.run(app, host='0.0.0.0', port=5000)
