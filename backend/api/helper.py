from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import json
from rapidfuzz import process, fuzz

app = Flask(__name__)
CORS(app)

ALBUM_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../cache/users/admin/albums'))

def load_set_mapping(mapping_path=None):
    if mapping_path is None:
        mapping_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../set_mapping.json"))
    with open(mapping_path, "r", encoding="utf-8") as f:
        return json.load(f)

def load_cards():
    cards = []
    base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../cache'))
    set_mapping = load_set_mapping()  # Set-Mapping laden

    for filename in os.listdir(base_path):
        if filename.endswith(".json"):
            set_key = filename.split('.')[0]
            set_name = set_mapping.get(set_key, None)  # Gemappten Setnamen holen, falls vorhanden
            path = os.path.join(base_path, filename)
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    for card in data:
                        card["set"] = set_name
                        cards.append(card)
    return cards

cards = load_cards()

def normalize_card(raw):
    print(f"Normalizing card: {raw.get('name')}")
    low = raw.get("cardmarket", {}).get("prices", {}).get("lowPrice", 0) or 0
    reverse = raw.get("cardmarket", {}).get("prices", {}).get("reverseHolo", 0) or None
    return {
        "id": raw.get("id"),
        "name": raw.get("name"),
        "set": raw.get("set") or raw.get("setName"),
        "number": raw.get("number"),
        "rarity": raw.get("rarity"),
        "image": raw.get("images", {}).get("small") if raw.get("images") else None,
        "priceLow": low,
        "priceReverse": reverse,
        "updatedAt": raw.get("cardmarket", {}).get("updatedAt"),
    }

normalized_cards = [normalize_card(c) for c in cards]

@app.route("/search", methods=["GET"])
def search_cards():
    query = request.args.get("q", "").strip()
    print(f"[DEBUG] Search query received: '{query}'")
    if not query:
        print("[DEBUG] Empty query, returning empty list")
        return jsonify([])

    # TODO: Suche auf Set etc erweitern
    # Suche nur anhand des Namens, setzt Score per partial_ratio (ähnlich Fuse.js)
    names = [c["name"] or "" for c in normalized_cards]

    results = process.extract(
        query, names, scorer=fuzz.partial_ratio, limit=50
    )
    print(f"[DEBUG] Number of matches found: {len(results)}")

    # Map Ergebnisse zurück auf Kartenobjekte + Score
    filtered = []
    for match in results:
        name_match, score, idx = match
        card = normalized_cards[idx]
        filtered.append({**card, "_score": score})
    print(f"[DEBUG] Number of filtered cards before sorting: {len(filtered)}")

    # Sortiere absteigend nach Score
    filtered.sort(key=lambda x: x["_score"], reverse=True)

    return jsonify(filtered)

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
