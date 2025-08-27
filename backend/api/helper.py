from flask import Flask, request, jsonify
import os
import json

app = Flask(__name__)

ALBUM_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../cache/users/admin/albums'))

def load_album(album_name):
    album_file = os.path.join(ALBUM_PATH, f"{album_name}.json")
    if not os.path.exists(album_file):
        return None
    with open(album_file, "r", encoding="utf-8") as f:
        return json.load(f)

def save_album(album_name, data):
    os.makedirs(ALBUM_PATH, exist_ok=True)
    album_file = os.path.join(ALBUM_PATH, f"{album_name}.json")
    with open(album_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

@app.route("/album", methods=["POST"])
def create_album():
    album_data = request.get_json()
    if not album_data or "album_name" not in album_data:
        return jsonify({"error": "Fehlende Albumdaten"}), 400

    os.makedirs(ALBUM_PATH, exist_ok=True)
    album_file = os.path.join(ALBUM_PATH, f"{album_data['album_name']}.json")
    with open(album_file, "w", encoding="utf-8") as f:
        json.dump(album_data, f, ensure_ascii=False, indent=2)
    return jsonify({"status": "Album gespeichert"}), 200

@app.route("/album/<album_name>", methods=["GET"])
def get_album(album_name):
    album = load_album(album_name)
    if album is None:
        return jsonify({"error": "Album nicht gefunden"}), 404
    return jsonify(album)


@app.route("/album/<album_name>/add_card", methods=["POST"])
def add_card_to_album(album_name):
    card_data = request.get_json()
    if not card_data or "card_id" not in card_data:
        return jsonify({"error": "Keine Karte angegeben"}), 400
    
    album = load_album(album_name)
    if album is None:
        album = {"album_name": album_name, "cards": []}
    if "cards" not in album:
        album["cards"] = []

    if card_data["card_id"] not in album["cards"]:
        album["cards"].append(card_data["card_id"])
        save_album(album_name, album)

    return jsonify({"status": "Karte hinzugefügt"}), 200

@app.route("/album/<album_name>/cards", methods=["GET"])
def get_album_cards(album_name):
    album = load_album(album_name)
    if album is None or "cards" not in album:
        return jsonify({"cards": []})
    return jsonify({"cards": album["cards"]})

if __name__ == "__main__":
    app.run(debug=True, port=5000)
