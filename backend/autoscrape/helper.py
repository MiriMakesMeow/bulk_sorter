import json
import os
import time
from datetime import datetime
from bs4 import BeautifulSoup

from playwrightPy import scrape_with_playwright_sync
from cardmarket_parser import CardmarketPricePlugin


def scrape_all_card_urls_from_set(set_url_base: str, max_pages: int = 20) -> list[dict]:
    collected_cards = []
    seen_numbers = set()
    
    for page in range(1, max_pages + 1):
        url = f"{set_url_base}&site={page}"
        html = scrape_with_playwright_sync(url, engine="playwright-stealth", headless=False)
        soup = BeautifulSoup(html, "html.parser")
        with open(f"debug_seite_{page}.html", "w", encoding="utf-8") as f:
            f.write(str(soup))

        card_rows = soup.select("table.table tbody tr")

        print(f"[Seite {page}] Gefundene card_rows: {len(card_rows)}")
        print(soup.title)
        if not card_rows:
            print(f"[Seite {page}] Keine card_rows gefunden, Abbruch.")
            break

        for row in card_rows:
            cols = row.find_all("td")
            if len(cols) < 5:
                continue

            number_text = cols[0].text.strip()
            link_tag = cols[1].select_one("a")
            if not link_tag or not number_text:
                continue

            number = number_text.lstrip("0")
            if not number.isdigit():
                continue
            if number in seen_numbers:
                continue

            seen_numbers.add(number)
            card_name = link_tag.text.strip()
            card_url = "https://www.cardmarket.com" + link_tag["href"]

            collected_cards.append({
                "number": number,
                "name": card_name,
                "url": card_url
            })

        time.sleep(1)
    return collected_cards


def update_cardmarket_prices(json_path: str, set_url_base: str, output_path: str):
    with open(json_path, "r", encoding="utf-8") as f:
        cards = json.load(f)

    card_urls = scrape_all_card_urls_from_set(set_url_base)

    number_to_url = {entry["number"]: entry["url"] for entry in card_urls}
    parser = CardmarketPricePlugin()
    updated_at = datetime.utcnow().strftime("%Y-%m-%d")

    updated = 0
    for card in cards:
        number = card.get("number", "").lstrip("0")
        if number not in number_to_url:
            continue

        url = number_to_url[number]
        html = scrape_with_playwright_sync(url, engine="playwright-stealth", headless=True)
        fields = parser.parse(html)
        prices = {}

        for f in fields:
            if "reverse" in f.name.lower():
                prices_key = f"reverseHolo{f.name[0].upper() + f.name[1:]}"
            else:
                prices_key = f.name

            prices[prices_key] = f.value

        card["cardmarket"] = {
            "url": url,
            "updatedAt": updated_at,
            "prices": prices
        }

        updated += 1
        time.sleep(1)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(cards, f, ensure_ascii=False, indent=2)

    print(f"{updated} Karten mit Preisen aktualisiert.")
    print(f"Gespeichert unter: {output_path}")


# Beispiel-Aufruf
if __name__ == "__main__":
    update_cardmarket_prices(
        json_path="cache_old/sv3pt5.json",
        set_url_base="https://www.cardmarket.com/en/Pokemon/Products/Singles/151?idRarity=0&sortBy=collectorsnumber_asc",
        output_path="cache/sv3pt5.json"
    )
