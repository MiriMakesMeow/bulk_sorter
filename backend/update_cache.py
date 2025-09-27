import csv
import json
import time
from datetime import datetime, timedelta
from pathlib import Path

from bs4 import BeautifulSoup
import requests

from autoscrape.playwrightPy import scrape_with_playwright_sync
from autoscrape.cardmarket_parser import CardmarketPricePlugin


# Globale Pfade
HERE = Path(__file__).parent.resolve()
CACHE_PATH = HERE.parent / "cache"
OLD_CACHE_PATH = HERE.parent / "old_cache" # legacy cache path
MAPPING = HERE / "set_mapping.json"
MAPPING_V2 = HERE / "set_mapping-v2.json"
ALBUM_PATH = HERE.parent / "cache" / "users" / "admin" / "albums"

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

def load_set_mapping(mapping_path: Path = MAPPING):
    with mapping_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_set_mapping_v2(mapping_path: Path = MAPPING_V2):
    with mapping_path.open("r", encoding="utf-8") as f:
        mapping = json.load(f)
    alias_to_master = {}
    master_to_aliases = {}
    for master, aliases in mapping.items():
        if isinstance(aliases, str):
            aliases = [aliases]
        for alias in aliases:
            alias_to_master[alias.lower()] = master
        master_to_aliases[master] = [a.lower() for a in aliases]
    return alias_to_master, master_to_aliases


def load_cards_from_old_cache(set_id, base_path: Path = CACHE_PATH):
    path = base_path / f"{set_id}.json"
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_updated_cards(set_id, cards, base_path: Path = CACHE_PATH):
    base_path.mkdir(parents=True, exist_ok=True)
    path = base_path / f"{set_id}.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(cards, f, ensure_ascii=False, indent=2)


def scrape_overview_prices(set_url_base: str, max_pages: int = 20) -> dict:
    result = {}
    seen = set()
    found = False

    for page in range(1, max_pages + 1):
        url = f"{set_url_base}&site={page}"
        if page == 1:
            print(f"Scraping: {url}")

        html = scrape_with_playwright_sync(url, engine="playwright-stealth", headless=True)
        soup = BeautifulSoup(html, "html.parser")
        rows = soup.select('div.table.table-striped.mb-3 div.row.g-0[id^="row"]') or soup.select('div.table.table-striped.mb-3 div.row.g-0[id^="row"]')
        if not rows:
            if page == 1:
                return None
            break

        found = True
        for row in rows:
            aria_labels = [svg.get("aria-label", "") for svg in row.select("svg[aria-label]")]
            if "Online Code Card" in aria_labels:
                continue
            link = row.select_one('a[href*="/Products/"]')
            number_div = row.select_one('div.col-md-2')
            price_div = row.select_one('div.col-price.pe-sm-2')
            price_rev_div = row.select_one('div.col-price.d-lg-flex')

            if not link or not number_div:
                continue

            number = number_div.text.strip().lstrip("0")
            if not number.isdigit():
                continue

            name = link.text.strip()
            url = "https://www.cardmarket.com" + link["href"]
            try:
                price = float(price_div.text.replace("€", "").replace(",", ".").strip())
            except Exception:
                price = None
            try:
                price_rev = float(price_rev_div.text.replace("€", "").replace(",", ".").strip())
            except Exception:
                price_rev = None

            promo = "Promo" in aria_labels
            key = f"{number}-promo" if promo else number
            if key in seen:
                continue
            seen.add(key)
            result[key] = {
                "number": number,
                "url": url,
                "price": price,
                "price_rev": price_rev,
                "promo": promo,
                "name": name
            }
        time.sleep(1)
    if not found:
        return None
    return result


def update_single_set_from_overview(set_id: str, mapped_name: str):
    print(f"\nUpdating set: {set_id} → {mapped_name}")
    cards = load_cards_from_old_cache(set_id, OLD_CACHE_PATH)
    updated_epoch = datetime.now()
    overview_url = f"https://www.cardmarket.com/en/pokemon/products/singles/{mapped_name}?idRarity=0&sort=collectorsnumber-asc"
    overview = scrape_overview_prices(overview_url)

    if overview is None:
        print(f"Warning: no cards found for {mapped_name} at {overview_url}")
        return

    num_to_card = {c["number"].lstrip("0"): c for c in cards}
    updated = 0
    for key, entry in overview.items():
        num = entry["number"]
        existing = num_to_card.get(num)
        if entry.get("promo"):
            if existing:
                new_card = existing.copy()
                new_card["id"] = f"{set_id}-promo-{num}"
                new_card["name"] = f"{entry['name']} (Promo)"
                new_card["rarity"] = "Promo"
                new_card["cardmarket"] = {
                    "url": entry["url"],
                    "updatedAt": updated_epoch.strftime("%Y-%m-%d"),
                    "prices": {
                        "low": entry["price"],
                        "rev": entry["price_rev"]
                    }
                }
                cards.append(new_card)
                updated += 1
            continue
        if existing:
            cm = existing.get("cardmarket")
            if cm:
                try:
                    lu = datetime.strptime(cm.get("updatedAt", "1970-01-01"), "%Y-%m-%d")
                    if (updated_epoch - lu).days < 7:
                        continue
                except Exception:
                    pass
            existing["cardmarket"] = {
                "url": entry["url"],
                "updatedAt": updated_epoch.strftime("%Y-%m-%d"),
                "prices": {
                    "low": entry["price"],
                    "rev": entry["price_rev"]
                }
            }
            updated += 1

    save_updated_cards(set_id, cards, Path("../cache"))
    print(f"Updated {updated} cards for {set_id}")


alias_map, alias_reversed_map = load_set_mapping_v2(MAPPING_V2)


def get_all_aliases(set_code: str):
    man = alias_map.get(set_code.lower())
    if man is None:
        #print(f"Warning: no master name for '{set_code}'")
        return [set_code.lower()]
    return alias_reversed_map[man]


def find_cache_json(set_code: str, notes):
    probable_aliases = get_all_aliases(set_code)
    if "TG" in notes:
        probable_aliases.append("tg")
    for alias in probable_aliases:
        p = CACHE_PATH / f"{alias}.json"
        if p.exists():
            return p
    return None


def find_card(row, cards_list):
    for card in cards_list:
        if str(card.get("number", "")).lstrip("0") == str(row["nr"]).lstrip("0"):
            # if card.get("set") and row["set"].lower() in card.get("set", "").lower():
            #     if card.get("name") == row["pokemon"]:
            print(f"Match found for {row}: {card.get('name')}")
            return card
    print(f"Warning: card not found for {row}")
    return None


def build_cardmarket_url(base_url: str, lang_code: str, isreverse: bool) -> str:
    lang_param = language_map.get(lang_code.lower(), 3)  # default de=3
    if isreverse:
        base_url = f"{base_url}?isReverseHolo=Y"
    if "?" in base_url:
        return base_url + f"&language={lang_param}"
    else:
        return base_url + f"?language={lang_param}"


def update_prices_in_csv():
    plugin = CardmarketPricePlugin()  # dein Cardmarket-Parser
    full_collection_path = ALBUM_PATH / "fullcollection.csv"
    save_collection_path = ALBUM_PATH / "fullcollection_with_prices.csv"
    set_not_found = []
    no_url_found = []


    with full_collection_path.open("r", encoding="utf-8", newline="") as csvfile, \
            save_collection_path.open("w", encoding="utf-8", newline="") as outcsv:

        reader = csv.DictReader(csvfile)
        fieldnames = reader.fieldnames + ["online_price"]
        writer = csv.DictWriter(outcsv, fieldnames=fieldnames)
        writer.writeheader()

        cache_cache = {}

        for row in reader:
            notes = []
            if row.get("note1"):
                notes.append(row["note1"])
            if row.get("note2"):
                notes.append(row["note2"])
            set_code = row["set"]
            cache_json_path = find_cache_json(set_code, notes)
            if cache_json_path is None:
                print(f"⚠️ Kein Cache-JSON für Set '{set_code}' gefunden. Zeile wird übersprungen.")
                set_not_found.append(set_code)
                continue
            if cache_json_path not in cache_cache:
                with cache_json_path.open("r", encoding="utf-8") as f:
                    cache_cache[cache_json_path] = json.load(f)
            cards = cache_cache[cache_json_path]
            match = find_card(row, cards)
            if match and match.get("cardmarket", {}).get("url"):
                url = match["cardmarket"]["url"]
                try:
                    lang_code = row.get("lang", "de")
                    isreverse = False
                    if "Reverse" in notes:
                        isreverse = True
                    url = build_cardmarket_url(url, lang_code, isreverse)
                    # Lade die Seite mit Playwright (echter Browser)
                    html = scrape_with_playwright_sync(url, engine="playwright-stealth",headless=True)
                    # Parsen mit dem Cardmarket-Parser
                    fields = plugin.parse(html)

                    price = None
                    for f in fields:
                        # Preisdaten hier anpassbar (avg, low, trend, ...)
                        if "avg_7_days" in f.name.lower():
                            price = f.value

                    row["online_price"] = price

                except Exception as e:
                    row["online_price"] = ""
                    print(f"⚠️ Fehler beim Verarbeiten von URL {url}: {e}")
                    no_url_found.append()
            else:
                row["online_price"] = ""
                print(f"⚠️  Keine URL in Cache für {row}")
                no_url_found.append(f"{set_code} - {row['nr']}")
            writer.writerow(row)
    set(set_not_found)
    set(no_url_found)
    print(f"Sets not mapped yet: {set_not_found}")
    print(f"Cards without URL or price: {no_url_found}")
    
            
update_prices_in_csv()
# if __name__ == "__main__":
#     set_mapping = load_set_mapping("set_mapping.json")
#     # update_single_set_from_overview("sv3pt5", set_mapping["sv3pt5"])

#     for set_id, mapped_set_name in set_mapping.items():
#         update_single_set_from_overview(set_id, mapped_set_name)
