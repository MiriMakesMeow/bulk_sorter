from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import json
from rapidfuzz import process, fuzz
from helper import load_set_mapping, load_cards, normalize_card, lookup_card_by_id, load_album, save_album, ALBUM_PATH

# Initialisiere Flask-App
app = Flask(__name__)
CORS(app, supports_credentials=True)
# Setup Sets
cards = load_cards()
normalized_cards = [normalize_card(c) for c in cards]

@app.before_request
def handle_options():
    if request.method == 'OPTIONS':
        return '', 200

@app.route("/search", methods=["GET"])
def search_cards():
    query = request.args.get("q", "").strip()
    #print(f"[DEBUG] Search query received: '{query}'")
    if not query:
        print("[DEBUG] Empty query, returning empty list")
        return jsonify([])

    # TODO: Suche auf Set etc erweitern
    # Suche nur anhand des Namens, setzt Score per partial_ratio (ähnlich Fuse.js)
    names = [c["name"] or "" for c in normalized_cards]

    results = process.extract(
        query, names, scorer=fuzz.partial_ratio, limit=50
    )
    #print(f"[DEBUG] Number of matches found: {len(results)}")

    # Map Ergebnisse zurück auf Kartenobjekte + Score
    filtered = []
    for match in results:
        name_match, score, idx = match
        card = normalized_cards[idx]
        filtered.append({**card, "_score": score})
    #print(f"[DEBUG] Number of filtered cards before sorting: {len(filtered)}")

    # Sortiere absteigend nach Score
    filtered.sort(key=lambda x: x["_score"], reverse=True)

    return jsonify(filtered)

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


@app.route("/album/<album_name>/add_cards", methods=["POST"])
def add_card_to_album(album_name):
    print("Called add_card_to_album")
    card_data = request.get_json()
    if not card_data or "card_id" not in card_data:
        print("No card_id provided in request")
        return jsonify({"error": "Keine Karte angegeben"}), 400

    normal = card_data.get("count_normal", 1)
    reverse = card_data.get("count_reverse", 0)
    print(f"Adding card {card_data['card_id']} to album {album_name} (normal: {normal}, reverse: {reverse})")

    album = load_album(album_name)
    if album is None:
        album = {"album_name": album_name, "cards": []}
    if "cards" not in album:
        album["cards"] = []

    # Suche, ob Karte schon existiert (via card_id)
    existing = next((c for c in album["cards"] if c["card_id"] == card_data["card_id"]), None)
    card_id = card_data["card_id"]
    card_set = card_id.split("-")[0] if "-" in card_id else "Unknown"
    print(f"Card ID: {card_id}, Set: {card_set}")

    if existing:
        # Counter erhöhen
        existing["count_normal"] = existing.get("count_normal", 0) + normal
        existing["count_reverse"] = existing.get("count_reverse", 0) + reverse
    else:
        # Neue Karte mit Counter anlegen
        album["cards"].append({
            "card_id": card_id,
            "set": card_set,
            "count_normal": normal,
            "count_reverse": reverse
        })

    save_album(album_name, album)
    return jsonify({"status": "Karte hinzugefügt"}), 200

@app.route("/album/<album_name>/cards", methods=["GET"])
def get_album_cards(album_name):
    album = load_album(album_name)
    if album is None or "cards" not in album:
        return jsonify({"cards": [], "total_cards": 0})

    cards = album["cards"]
    total_count = sum(c.get("count_normal", 0) + c.get("count_reverse", 0) for c in cards)

    return jsonify({"cards": cards, "total_cards": total_count})

@app.route("/cards/details", methods=["GET"])
def get_card_details():
    card_id = request.args.get("card_id", "").strip()
    if not card_id:
        return jsonify({"error": "Keine card_id angegeben"}), 400

    card = lookup_card_by_id(card_id, normalized_cards)
    if card is None:
        return jsonify({"error": "Karte nicht gefunden"}), 404

    return jsonify(card)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
