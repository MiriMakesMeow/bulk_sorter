import json
import sqlite3
from pathlib import Path
import os
import time
import requests
from datetime import datetime


DB_PATH = "cache/db/cards.db"
CACHE_DIR = Path("cache")
BASE_URL = "https://api.tcgconnect.eu"
API_KEY = os.getenv("TCGCONNECT_API_KEY") or "-c9dDgy5XI4Yk0IRtIHYQl7axwBW7FguWkJiC8Hsdc4"


SET_MAPPING_PATH = "set_mapping-v2.json"

# ----------- CARDMARKET Scraping -------------------
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
    

# ---------- DB FUNCTIONS ----------------

def init_db_cache_JSON(conn: sqlite3.Connection):
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


def init_sets_table(conn):
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sets (
            code TEXT PRIMARY KEY,   -- z.B. sv9
            name TEXT,               -- z.B. Journey-Together
            short_code TEXT          -- z.B. JTG
        )
    """)
    conn.commit()

def init_db(conn: sqlite3.Connection):
    cur = conn.cursor()

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
            cardmarket_product_id INTEGER
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS card_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            card_id TEXT,
            cardmarket_product_id INTEGER,
            date TEXT,
            price_en_nm_de REAL,
            avg7_normal REAL,
            avg30_normal REAL,
            variant TEXT
        )
    """)

    conn.commit()

# --- TCGConnect API Helpers ----------------------------------------------


def tcg_headers():
    if not API_KEY:
        raise RuntimeError("TCGCONNECT_API_KEY nicht gesetzt")
    return {
        "x-api-key": API_KEY,
        "Accept": "application/json",
    }


def tcg_search_card(id_str: str, name: str, number: str, set_code: str, game: str = "pokemon"):
    """
    Sucht eine Karte in TCGConnect.
    q = 'Name Nummer', set_id = set_code (z.B. 'sv9').
    Fällt zurück auf q = id_str, falls die erste Suche nichts findet.
    """
    headers = tcg_headers()

    def _do_search(q):
        params = {
            "q": q,
            "game": game,
            "set_id": set_code,
            "limit": 1,
        }
        resp = requests.get(f"{BASE_URL}/cards/search", headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("items"):
            return data["items"][0]
        return None

    # Erst Name + Number
    q1 = f"{name} {number}".strip()
    card = _do_search(q1)
    if card:
        return card

    # Fallback: unsere interne ID
    card = _do_search(id_str)
    return card


def tcg_get_price_history(cardmarket_product_id: str, condition: int = 2, days: int = 7):
    """
    Holt Preis-Historie für Cardmarket-Produkt-ID, EN, NEAR_MINT, Seller Germany.
    condition = 2 (NEAR_MINT), country = 7 (GERMANY) gemäß deiner Beschreibung.
    """
    headers = tcg_headers()
    params = {
        "days": days,
        "country": 7,     # Germany
    }
    if condition is not None:
        params["condition"] = condition  # 2 = NEAR_MINT, sonst None => alle
    url = f"{BASE_URL}/cards/{cardmarket_product_id}/prices"
    resp = requests.get(url, headers=headers, params=params, timeout=20)
    resp.raise_for_status()
    return resp.json()

def tcg_get_price_history_generic(cardmarket_product_id: int, days: int, condition: int | None):
    """
    condition: 2 = NEAR_MINT, None = alle Conditions.
    """
    headers = tcg_headers()
    params = {
        "days": days,
        "country": 7,  # Germany
    }
    if condition is not None:
        params["condition"] = condition
    url = f"{BASE_URL}/cards/{cardmarket_product_id}/prices"
    resp = requests.get(url, headers=headers, params=params, timeout=20)
    resp.raise_for_status()
    return resp.json()


def compute_average_from_history(history):
    """
    Erwartet Liste von Einträgen mit 'price', 'date_time', 'card_condition'.
    Gibt (mean_price, latest_date, condition) zurück.
    Wenn unterschiedliche Conditions vorkommen, nimmt er die erste gefundene.
    """
    if not history:
        return None, None, None

    prices = []
    last_date = None
    condition = None

    for entry in history:
        p = entry.get("price")
        dt = entry.get("date_time")
        cond = entry.get("card_condition")

        if p is None:
            continue
        try:
            prices.append(float(p))
        except (TypeError, ValueError):
            continue

        if dt:
            last_date = dt
        if cond and condition is None:
            condition = cond

    if not prices:
        return None, last_date, condition

    avg = sum(prices) / len(prices)
    return avg, last_date, condition


def extract_en_nm_de_current_price(card_search_obj):
    """
    card_search_obj = erste Karte aus /cards/search.
    Nimmt prices_lowest.NEAR_MINT und filtert auf ENGLISH + GERMANY.
    """
    prices_lowest = card_search_obj.get("prices_lowest") or {}
    nm_entries = prices_lowest.get("NEAR_MINT") or []

    for e in nm_entries:
        if (
            e.get("card_language") == "ENGLISH"
            and e.get("cardmarket_country") == "GERMANY"
            and e.get("card_condition") == "NEAR_MINT"
        ):
            try:
                return float(e.get("price"))
            except (TypeError, ValueError):
                return None
    return None


# --- Import aus JSON + Füllen der DB -------------------------------------


def import_jsons_with_tcgconnect(conn: sqlite3.Connection, cache_dir: Path):
    cur = conn.cursor()

    json_files = list(cache_dir.glob("*.json"))
    print(f"Gefundene Cache-JSONs: {len(json_files)}")

    for json_file in json_files:
        set_code = json_file.stem  # z.B. 'sv9'
        print(f"➡️ Importiere Set {set_code} aus {json_file}")

        with json_file.open("r", encoding="utf-8") as f:
            cards = json.load(f)

        for c in cards:
            card_id = c.get("id")          # z.B. 'sv9-1'
            name = c.get("name") or ""
            supertype = c.get("supertype")
            subtypes = ",".join(c.get("subtypes", []))
            number = c.get("number") or ""
            rarity = c.get("rarity")
            images = c.get("images", {})
            img_small = images.get("small")
            img_large = images.get("large")
            cardmarket = c.get("cardmarket", {})
            cm_url = cardmarket.get("url")
            updated_at = cardmarket.get("updatedAt")

            # --- Stammdaten in 'cards' -----------------------------------
            cur.execute("""
                INSERT OR REPLACE INTO cards
                (id, set_code, name, supertype, subtypes, number, rarity,
                 image_small, image_large, cardmarket_url, cardmarket_product_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(
                    (SELECT cardmarket_product_id FROM cards WHERE id = ?), NULL
                ))
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
                cm_url,
                None
            ))

            # --- TCGConnect: Mapping + Preise ---------------------------
            try:
                tcg_card = tcg_search_card(card_id, name, number, set_code)
            except Exception as e:
                print(f"   ⚠️ TCGConnect search Fehler für {card_id}: {e}")
                continue

            if not tcg_card:
                print(f"   ⚠️ Keine TCGConnect Karte für {card_id} gefunden")
                continue

            cardmarket_product_id = tcg_card.get("cardmarket_product_id")
            # aktuellen EN/GERMANY Preis holen
            price_en_nm_de = extract_en_nm_de_current_price(tcg_card)

            # Karten-Tabelle um cardmarket_product_id aktualisieren
            cur.execute(
                "UPDATE cards SET cardmarket_product_id = ? WHERE id = ?",
                (cardmarket_product_id, card_id)
            )

            avg7_normal = avg30_normal = None
            latest_date = updated_at

            if cardmarket_product_id:
                # 7-Tage-Historie
                try:
                    hist7 = tcg_get_price_history(card_id, days=7)
                    avg7_normal, date7, condition = compute_average_from_history(hist7)
                    if date7:
                        latest_date = date7
                except Exception as e:
                    print(f"   ⚠️ Fehler bei 7d-Preisen für {card_id}: {e}")

                # 30-Tage-Historie
                try:
                    hist30 = tcg_get_price_history(card_id, days=30)
                    avg30_normal, date30, condition = compute_average_from_history(hist30)
                    if date30:
                        latest_date = date30
                except Exception as e:
                    print(f"   ⚠️ Fehler bei 30d-Preisen für {card_id}: {e}")

            # Fallback: wenn kein Datum vorhanden, nimm heute
            if not latest_date:
                latest_date = datetime.now().date().isoformat()

            cur.execute("""
                INSERT INTO card_prices
                (card_id, cardmarket_product_id, date,
                 price_en_nm_de, avg7_normal, avg30_normal, condition, variant)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                card_id,
                cardmarket_product_id,
                latest_date,
                price_en_nm_de,
                avg7_normal,
                avg30_normal,
                condition,
                "NORMAL"
            ))

            # kleine Pause, um API nicht zu stressen
            time.sleep(0.2)

        conn.commit()


def import_set_mapping(conn, mapping_path=SET_MAPPING_PATH):
    cur = conn.cursor()
    mapping_file = Path(mapping_path)
    if not mapping_file.exists():
        print(f"⚠️ Set-Mapping-Datei '{mapping_path}' nicht gefunden – überspringe Sets")
        return

    with mapping_file.open("r", encoding="utf-8") as f:
        mapping = json.load(f)

    for set_name, value in mapping.items():
        main_code, short_code = normalize_mapping_entry(value)
        cur.execute("""
            INSERT OR REPLACE INTO sets (code, name, short_code)
            VALUES (?, ?, ?)
        """, (main_code, set_name, short_code))

    conn.commit()
    print("✅ Set-Mapping importiert")


# def import_cache_jsons(conn: sqlite3.Connection, cache_dir: Path, lang_code: str = "de"):
#     cur = conn.cursor()
#     plugin = CardmarketPricePlugin()
#     today_str = date.today().isoformat()
#     error_cards = []

#     if not cache_dir.exists():
#         print(f"⚠️ Cache-Verzeichnis '{cache_dir}' nicht gefunden")
#         return

#     json_files = list(cache_dir.glob("*.json"))
#     print(f"🔍 Gefundene Cache-JSONs: {len(json_files)}")

#     for json_file in json_files:
#         set_code = json_file.stem  # z.B. sv9
#         print(f"➡️ Importiere Set {set_code} aus {json_file}")

#         with json_file.open("r", encoding="utf-8") as f:
#             cards = json.load(f)

#         for c in cards:
#             card_id = c.get("id")
#             name = c.get("name")
#             supertype = c.get("supertype")
#             subtypes = ",".join(c.get("subtypes", []))
#             number = c.get("number")
#             rarity = c.get("rarity")
#             images = c.get("images", {})
#             img_small = images.get("small")
#             img_large = images.get("large")
#             cardmarket = c.get("cardmarket", {})
#             cm_url = cardmarket.get("url")
#             updated_at = cardmarket.get("updatedAt") or today_str
#             prices = cardmarket.get("prices", {}) or {}

#             # 1) Stammdaten der Karte
#             cur.execute("""
#                 INSERT OR REPLACE INTO cards
#                 (id, set_code, name, supertype, subtypes, number, rarity,
#                  image_small, image_large, cardmarket_url)
#                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
#             """, (
#                 card_id,
#                 set_code,
#                 name,
#                 supertype,
#                 subtypes,
#                 number,
#                 rarity,
#                 img_small,
#                 img_large,
#                 cm_url
#             ))

#             # 2) Basispreise aus JSON
#             low_price = prices.get("lowPrice")
#             reverse_holo_low = prices.get("reverseHoloLow")

#             # 3) Zusatzpreise via Scraping (optional)
#             avg_7_days = None
#             avg_30d = None
#             if cm_url:
#                 try:
#                     lang_code = lang_code  
#                     isreverse = False 
#                     url = build_cardmarket_url(cm_url, lang_code, isreverse)

#                     html = scrape_with_playwright_sync(
#                         url,
#                         engine="playwright-stealth",
#                         headless=True
#                     )
#                     fields = plugin.parse(html)
#                     print(f"[DEBUG] Scrape-Ergebnisse für {card_id}: {[f'{f.name}={f.value}' for f in fields]}")
#                     if not fields:
#                         error_cards.append(card_id)
#                     for f in fields:
#                         name_lower = f.name.lower()
#                         if "avg_7_days" in name_lower or "7-day" in name_lower:
#                             avg7_normal = f.value
#                         elif "avg_30_days" in name_lower:
#                             avg30_normal = f.value
#                     try:        
#                         # -------- Reverse ----------
#                         url_reverse = build_cardmarket_url(cm_url, lang_code, isreverse=True)
#                         html = scrape_with_playwright_sync(
#                             url_reverse,
#                             engine="playwright-stealth",
#                             headless=True
#                         )
#                         fields = plugin.parse(html)

#                         for f in fields:
#                             name_lower = f.name.lower()
#                             if "avg_7" in name_lower or "7-day" in name_lower:
#                                 avg7_reverse = f.value
#                             elif "avg_30" in name_lower or "30-day" in name_lower:
#                                 avg30_reverse = f.value
#                     except Exception as e:
#                         print(f"   ⚠️ Reverse-Scrape-Fehler für {card_id}: {e}")
#                         avg7_reverse = reverse_holo_low
#                         avg30_reverse = None
#                     print(f"   ✅ Scrape ok für {card_id}")

#                 except Exception as e:
#                     print(f"   ⚠️ Scrape-Fehler für {card_id}: {e}")
#                     avg7_normal = low_price
#                     avg30_normal = None

#                 print("Waiting before scraping for not getting caught...")
#                 time.sleep(30)

#             # 4) Snapshot in card_prices
#             cur.execute("""
#                 INSERT INTO card_prices
#                 (card_id, date,
#                 low_price, reverse_holo_low,
#                 avg7_normal, avg30_normal,
#                 avg7_reverse, avg30_reverse)
#                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)
#             """, (
#                 card_id,
#                 updated_at,
#                 low_price,
#                 reverse_holo_low,
#                 avg7_normal,
#                 avg30_normal,
#                 avg7_reverse,
#                 avg30_reverse
#             ))

#         conn.commit()
#     with open("error_cards.json", "w", encoding="utf-8") as f:
#         json.dump(error_cards, f, ensure_ascii=False, indent=4)
#     print("✅ Alle Cache-JSONs importiert")


def load_cache_index(cache_dir: Path):
    """
    set_code -> { card_id -> {lowPrice, reverseHoloLow, date} }
    """
    index = {}
    for json_file in cache_dir.glob("*.json"):
        set_code = json_file.stem
        with json_file.open("r", encoding="utf-8") as f:
            data = json.load(f)
        by_id = {}
        if not isinstance(data, list):
            continue
        for c in data:
            cid = c.get("id")
            cm = (c.get("cardmarket") or {})
            prices = (cm.get("prices") or {})
            by_id[cid] = {
                "lowPrice": prices.get("lowPrice"),
                "reverseHoloLow": prices.get("reverseHoloLow"),
                "date": cm.get("updatedAt"),
            }
        index[set_code] = by_id
    return index


def normalize_mapping_entry(value):
    """value = 'sv9' oder ['sv9', 'JTG'] -> (main_code, short_code)"""
    if isinstance(value, list):
        main_code = value[0]
        short_code = value[1] if len(value) > 1 else None
    else:
        main_code = value
        short_code = None
    return main_code, short_code


def backfill_all(db_path=DB_PATH, cache_dir=CACHE_DIR):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cache_index = load_cache_index(cache_dir)

    # 1) Bestehende API-Werte als NEAR_MINT markieren, falls Condition noch NULL
    cur.execute("""
        UPDATE card_prices
        SET condition = 'NEAR_MINT'
        WHERE condition IS NULL
          AND (avg7_normal IS NOT NULL OR avg30_normal IS NOT NULL OR price_en_nm_de IS NOT NULL)
    """)

    # 2) Alle Karten + Set-Code + Produkt-ID holen
    cur.execute("""
        SELECT id AS card_id, set_code, cardmarket_product_id
        FROM cards
    """)
    rows = cur.fetchall()

    updated_api = 0
    updated_json = 0
    created_reverse = 0

    for row in rows:
        card_id = row["card_id"]
        set_code = row["set_code"]
        cmp_id = row["cardmarket_product_id"]

        json_prices = (cache_index.get(set_code) or {}).get(card_id) or {}
        low_json = json_prices.get("lowPrice")
        rev_json = json_prices.get("reverseHoloLow")
        json_date = json_prices.get("date")

        # aktuelle NORMAL-Zeile (falls vorhanden)
        cur.execute("""
            SELECT id, avg7_normal, avg30_normal, date, condition, price_en_nm_de
            FROM card_prices
            WHERE card_id = ? AND variant = 'NORMAL'
            ORDER BY id DESC
            LIMIT 1
        """, (card_id,))
        cp = cur.fetchone()

        # Basis-Datum
        latest_date = (cp["date"] if cp else None) or json_date

        # 2a) fehlende 7d/30d aus TCGConnect mit condition=None nachholen (nur wenn cardmarket_product_id vorhanden)
        if cmp_id:
            avg7 = cp["avg7_normal"] if cp else None
            avg30 = cp["avg30_normal"] if cp else None
            cond = cp["condition"] if cp else None

            # 7d
            if avg7 is None:
                try:
                    hist7 = tcg_get_price_history_generic(cmp_id, days=7, condition=None)
                    avg7_new, date7, cond7 = compute_average_from_history(hist7)
                    if avg7_new is not None:
                        avg7 = avg7_new
                        latest_date = date7 or latest_date
                        cond = cond7 or cond
                except Exception as e:
                    print(f"⚠️ Fehler bei Generic-7d für {card_id}: {e}")

            # 30d
            if avg30 is None:
                try:
                    hist30 = tcg_get_price_history_generic(cmp_id, days=30, condition=None)
                    avg30_new, date30, cond30 = compute_average_from_history(hist30)
                    if avg30_new is not None:
                        avg30 = avg30_new
                        latest_date = date30 or latest_date
                        cond = cond30 or cond
                except Exception as e:
                    print(f"⚠️ Fehler bei Generic-30d für {card_id}: {e}")

            if cp and (avg7 is not None or avg30 is not None):
                cur.execute("""
                    UPDATE card_prices
                    SET avg7_normal = COALESCE(?, avg7_normal),
                        avg30_normal = COALESCE(?, avg30_normal),
                        date = COALESCE(?, date),
                        condition = COALESCE(?, condition)
                    WHERE id = ?
                """, (avg7, avg30, latest_date, cond, cp["id"]))
                updated_api += 1
            elif not cp and (avg7 is not None or avg30 is not None):
                # es gab noch keine NORMAL-Zeile, leg eine an (reiner API-Fall)
                cur.execute("""
                    INSERT INTO card_prices
                    (card_id, cardmarket_product_id, date,
                     price_en_nm_de, avg7_normal, avg30_normal, variant, condition)
                    VALUES (?, ?, ?, NULL, ?, ?, 'NORMAL', ?)
                """, (
                    card_id, cmp_id,
                    latest_date or datetime.utcnow().date().isoformat(),
                    avg7, avg30, cond or None
                ))
                updated_api += 1

        # 2b) price_en_nm_de aus JSON füllen, falls noch None
        if low_json is not None:
            if cp:
                if cp["price_en_nm_de"] is None:
                    cur.execute("""
                        UPDATE card_prices
                        SET price_en_nm_de = ?,
                            date = COALESCE(?, date)
                        WHERE id = ?
                    """, (low_json, json_date, cp["id"]))
                    updated_json += 1
            else:
                # noch keine NORMAL-Zeile vorhanden -> neue aus JSON (ohne condition)
                cur.execute("""
                    INSERT INTO card_prices
                    (card_id, cardmarket_product_id, date,
                     price_en_nm_de, avg7_normal, avg30_normal, variant, condition)
                    VALUES (?, ?, ?, ?, NULL, NULL, 'NORMAL', NULL)
                """, (
                    card_id,
                    cmp_id,
                    json_date or datetime.utcnow().date().isoformat(),
                    low_json
                ))
                updated_json += 1

        # 2c) Reverse aus JSON anlegen (falls vorhanden, egal ob Set neu ist)
        if rev_json is not None:
            cur.execute("""
                SELECT 1 FROM card_prices
                WHERE card_id = ? AND variant = 'REVERSE'
                LIMIT 1
            """, (card_id,))
            if not cur.fetchone():
                cur.execute("""
                    INSERT INTO card_prices
                    (card_id, cardmarket_product_id, date,
                     price_en_nm_de, avg7_normal, avg30_normal, variant, condition)
                    VALUES (?, ?, ?, ?, NULL, NULL, 'REVERSE', NULL)
                """, (
                    card_id,
                    cmp_id,
                    json_date or datetime.now().date().isoformat(),
                    rev_json
                ))
                created_reverse += 1

    conn.commit()
    conn.close()
    print(f"✅ Backfill abgeschlossen: {updated_api} Karten mit TCGConnect-Øs, "
          f"{updated_json} Preise aus JSON ergänzt, {created_reverse} Reverse-Zeilen erstellt")
    

if __name__ == "__main__":
    backfill_all()
