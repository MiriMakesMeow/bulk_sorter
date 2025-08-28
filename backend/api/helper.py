import os
import json

ALBUM_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../cache/users/admin/albums'))

def load_set_mapping(mapping_path=None):
    if mapping_path is None:
        mapping_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../set_mapping.json"))
    with open(mapping_path, "r", encoding="utf-8") as f:
        return json.load(f)

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

def normalize_card(raw):
    #print(f"Normalizing card: {raw.get('name')}")
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

def lookup_card_by_id(card_id, normalized_cards=None):
    for card in normalized_cards:
        if card["id"] == card_id:
            return card
    return None
