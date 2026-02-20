import json
import sqlite3
import time
from pathlib import Path
from datetime import date

from autoscrape.playwrightPy import scrape_with_playwright_sync
from autoscrape.cardmarket_parser import CardmarketPricePlugin

# Pfade
DB_PATH = "cache/db/cards.db"
CACHE_DIR = Path("cache")
SET_MAPPING_PATH = "backend/set_mapping-v2.json"


def normalize_mapping_entry(value):
    """value = 'sv9' oder ['sv9', 'JTG'] -> (main_code, short_code)"""
    if isinstance(value, list):
        main_code = value[0]
        short_code = value[1] if len(value) > 1 else None
    else:
        main_code = value
        short_code = None
    return main_code, short_code


def build_cardmarket_url(base_url: str, lang_code: str, isreverse: bool) -> str:
    language_map = {
        "en": 1,
        "fr": 2,
        "de": 3,
        "es": 4,
        "it": 5,
        "jp": 7,
        "pt": 8,
        "ko": 10,
        "cn": 11,
        "in": 16,
        "th": 17, # Thai
    }
    lang_param = language_map.get(lang_code.lower(), 3)  # default de=3

    url = base_url
    if isreverse:
        # Reverse-Holo-Filter
        if "?" in url:
            url += "&isReverseHolo=Y"
        else:
            url += "?isReverseHolo=Y"

    if "?" in url:
        return url + f"&language={lang_param}"
    else:
        return url + f"?language={lang_param}"


def init_db(conn: sqlite3.Connection):
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sets (
            code TEXT PRIMARY KEY,      -- z.B. sv9
            name TEXT,                  -- z.B. Journey-Together
            short_code TEXT             -- z.B. JTG
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS cards (
            id TEXT PRIMARY KEY,
            set_code TEXT,
            name TEXT,
            supertype TEXT,
            subtypes TEXT,
            number TEXT,
            rarity TEXT,
            image_small TEXT,
            image_large TEXT,
            cardmarket_url TEXT,
            FOREIGN KEY(set_code) REFERENCES sets(code)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS card_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            card_id TEXT,
            date TEXT,
            low_price REAL,
            reverse_holo_low REAL,
            avg7_normal REAL,
            avg30_normal REAL,
            avg7_reverse REAL,
            avg30_reverse REAL,
            FOREIGN KEY(card_id) REFERENCES cards(id)
        )
    """)
    conn.commit()
    print("✅ DB-Tabellen erstellt oder bestätigt")

def import_set_mapping(conn: sqlite3.Connection, mapping_path: str):
    cur = conn.cursor()

    with open(mapping_path, "r", encoding="utf-8") as f:
        mapping = json.load(f)

    for set_name, value in mapping.items():
        main_code, short_code = normalize_mapping_entry(value)
        cur.execute("""
            INSERT OR REPLACE INTO sets (code, name, short_code)
            VALUES (?, ?, ?)
        """, (main_code, set_name, short_code))

    conn.commit()
    print("✅ Set-Mapping importiert")


def import_cache_jsons(conn: sqlite3.Connection, cache_dir: Path, lang_code: str = "de"):
    cur = conn.cursor()
    plugin = CardmarketPricePlugin()
    today_str = date.today().isoformat()
    error_cards = []

    if not cache_dir.exists():
        print(f"⚠️ Cache-Verzeichnis '{cache_dir}' nicht gefunden")
        return

    json_files = list(cache_dir.glob("*.json"))
    print(f"🔍 Gefundene Cache-JSONs: {len(json_files)}")

    for json_file in json_files:
        set_code = json_file.stem  # z.B. sv9
        print(f"➡️ Importiere Set {set_code} aus {json_file}")

        with json_file.open("r", encoding="utf-8") as f:
            cards = json.load(f)

        for c in cards:
            card_id = c.get("id")
            name = c.get("name")
            supertype = c.get("supertype")
            subtypes = ",".join(c.get("subtypes", []))
            number = c.get("number")
            rarity = c.get("rarity")
            images = c.get("images", {})
            img_small = images.get("small")
            img_large = images.get("large")
            cardmarket = c.get("cardmarket", {})
            cm_url = cardmarket.get("url")
            updated_at = cardmarket.get("updatedAt") or today_str
            prices = cardmarket.get("prices", {}) or {}

            # 1) Stammdaten der Karte
            cur.execute("""
                INSERT OR REPLACE INTO cards
                (id, set_code, name, supertype, subtypes, number, rarity,
                 image_small, image_large, cardmarket_url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                card_id,
                set_code,
                name,
                supertype,
                subtypes,
                number,
                rarity,
                img_small,
                img_large,
                cm_url
            ))

            # 2) Basispreise aus JSON
            low_price = prices.get("lowPrice")
            reverse_holo_low = prices.get("reverseHoloLow")

            # 3) Zusatzpreise via Scraping (optional)
            avg_7_days = None
            avg_30d = None
            if cm_url:
                try:
                    lang_code = lang_code  
                    isreverse = False 
                    url = build_cardmarket_url(cm_url, lang_code, isreverse)

                    html = scrape_with_playwright_sync(
                        url,
                        engine="playwright-stealth",
                        headless=True
                    )
                    fields = plugin.parse(html)
                    print(f"[DEBUG] Scrape-Ergebnisse für {card_id}: {[f'{f.name}={f.value}' for f in fields]}")
                    if not fields:
                        error_cards.append(card_id)
                    for f in fields:
                        name_lower = f.name.lower()
                        if "avg_7_days" in name_lower or "7-day" in name_lower:
                            avg7_normal = f.value
                        elif "avg_30_days" in name_lower:
                            avg30_normal = f.value
                    try:        
                        # -------- Reverse ----------
                        url_reverse = build_cardmarket_url(cm_url, lang_code, isreverse=True)
                        html = scrape_with_playwright_sync(
                            url_reverse,
                            engine="playwright-stealth",
                            headless=True
                        )
                        fields = plugin.parse(html)

                        for f in fields:
                            name_lower = f.name.lower()
                            if "avg_7" in name_lower or "7-day" in name_lower:
                                avg7_reverse = f.value
                            elif "avg_30" in name_lower or "30-day" in name_lower:
                                avg30_reverse = f.value
                    except Exception as e:
                        print(f"   ⚠️ Reverse-Scrape-Fehler für {card_id}: {e}")
                        avg7_reverse = reverse_holo_low
                        avg30_reverse = None
                    print(f"   ✅ Scrape ok für {card_id}")

                except Exception as e:
                    print(f"   ⚠️ Scrape-Fehler für {card_id}: {e}")
                    avg7_normal = low_price
                    avg30_normal = None

                print("Waiting before scraping for not getting caught...")
                time.sleep(30)

            # 4) Snapshot in card_prices
            cur.execute("""
                INSERT INTO card_prices
                (card_id, date,
                low_price, reverse_holo_low,
                avg7_normal, avg30_normal,
                avg7_reverse, avg30_reverse)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                card_id,
                updated_at,
                low_price,
                reverse_holo_low,
                avg7_normal,
                avg30_normal,
                avg7_reverse,
                avg30_reverse
            ))

        conn.commit()
    with open("error_cards.json", "w", encoding="utf-8") as f:
        json.dump(error_cards, f, ensure_ascii=False, indent=4)
    print("✅ Alle Cache-JSONs importiert")


def main():
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    # Set-Mapping importieren (falls Datei existiert)
    if Path(SET_MAPPING_PATH).exists():
        import_set_mapping(conn, SET_MAPPING_PATH)
    else:
        print(f"⚠️ Set-Mapping-Datei '{SET_MAPPING_PATH}' nicht gefunden – überspringe Sets")

    import_cache_jsons(conn, CACHE_DIR)

    conn.close()
    print("🎉 DB-Setup abgeschlossen")


if __name__ == "__main__":
    main()
