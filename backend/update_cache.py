import os
import json
import time
from datetime import datetime
from pathlib import Path
from bs4 import BeautifulSoup

from autoscrape.playwrightPy import scrape_with_playwright_sync


def load_set_mapping(mapping_path="set_mapping.json"):
    with open(mapping_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_cards_from_old_cache(set_id, base_path="../cache_old"):
    path = os.path.join(base_path, f"{set_id}.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_updated_cards(set_id, cards, base_path="../cache"):
    os.makedirs(base_path, exist_ok=True)
    path = os.path.join(base_path, f"{set_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cards, f, ensure_ascii=False, indent=2)


def scrape_overview_prices(set_url_base: str, max_pages: int = 20) -> dict:
    """Gibt ein Dict zurück: {"number": {"url": ..., "price": ..., "reverse_price": ..., "promo": bool, "name": ...}}"""
    result = {}
    seen_numbers = set()

    for page in range(1, max_pages + 1):
        url = f"{set_url_base}&site={page}"
        print(f"Scraping: {url}")
        html = scrape_with_playwright_sync(url, engine="playwright-stealth", headless=True)
        soup = BeautifulSoup(html, "html.parser")
        card_rows = soup.select('div.table.table-striped.mb-3 div.row.g-0[id^="productRow"]')

        if not card_rows:
            break

        for row in card_rows:
            aria_labels = [svg["aria-label"] for svg in row.select("svg[aria-label]")]

            if "Online Code Card" in aria_labels:
                continue

            link_tag = row.select_one('a[href*="/Products/Singles/"]')
            number_div = row.select_one('div.col-md-2')
            price_normal_div = row.select_one('div.col-price.pe-sm-2')
            price_reverse_div = row.select_one('div.col-price.d-lg-flex')

            if not link_tag or not number_div:
                continue

            number = number_div.text.strip().lstrip("0")
            if not number.isdigit():
                continue

            name = link_tag.text.strip()
            url = "https://www.cardmarket.com" + link_tag["href"]

            try:
                normal_price = float(price_normal_div.text.replace("\u20ac", "").replace(",", ".").strip())
            except:
                normal_price = None

            try:
                reverse_price = float(price_reverse_div.text.replace("\u20ac", "").replace(",", ".").strip())
            except:
                reverse_price = None

            is_promo = "Promo" in aria_labels and "Promo" not in name
            key = f"{number}-promo" if is_promo else number

            if key in seen_numbers:
                continue
            seen_numbers.add(key)
            print(f"Gefunden: {name} ({number}) - URL: {url} - Normal: {normal_price} - Reverse: {reverse_price} - Promo: {is_promo}")
            result[key] = {
                "number": number,
                "url": url,
                "price": normal_price,
                "reverse_price": reverse_price,
                "promo": is_promo,
                "name": name
            }

        time.sleep(1)

    return result


def update_single_set_from_overview(set_id, mapped_set_name):
    print(f"\n=== Aktualisiere Set: {set_id} → {mapped_set_name} ===")

    cards = load_cards_from_old_cache(set_id)
    updated_at = datetime.now().strftime("%Y-%m-%d")

    set_url_base = f"https://www.cardmarket.com/en/Pokemon/Products/Singles/{mapped_set_name}?idRarity=0&sortBy=collectorsnumber_asc"
    overview_data = scrape_overview_prices(set_url_base)

    number_to_card = {c["number"].lstrip("0"): c for c in cards}
    updated = 0

    for key, entry in overview_data.items():
        number = entry["number"]
        if entry.get("promo"):
            if number not in number_to_card:
                print(f"➕ Füge Promo-Karte hinzu: {entry['name']} ({number})")
                new_card = {
                    **number_to_card.get(number, {}).copy(),
                    "id": f"{set_id}-promo-{number}",
                    "name": f"{entry['name']} (Promo)",
                    "rarity": "Promo",
                    "number": number,
                    "cardmarket": {
                        "url": entry["url"],
                        "updatedAt": updated_at,
                        "prices": {
                            "lowPrice": entry["price"],
                            "reverseHoloLow": entry["reverse_price"]
                        }
                    }
                }
                cards.append(new_card)
                updated += 1
            continue

        if number in number_to_card:
            card = number_to_card[number]
            card["cardmarket"] = {
                "url": entry["url"],
                "updatedAt": updated_at,
                "prices": {
                    "lowPrice": entry["price"],
                    "reverseHoloLow": entry["reverse_price"]
                }
            }
            updated += 1

    save_updated_cards(set_id, cards)
    print(f"\n✔ {updated} Karten aktualisiert und gespeichert unter ../cache/{set_id}.json")


if __name__ == "__main__":
    set_mapping = load_set_mapping("set_mapping.json")
    # update_single_set_from_overview("sv3pt5", set_mapping["sv3pt5"])
    for set_id, mapped_set_name in set_mapping.items():
        update_single_set_from_overview(set_id, mapped_set_name)
