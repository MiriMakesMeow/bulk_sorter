import json
import os
import time
from datetime import datetime
from bs4 import BeautifulSoup

from .playwrightPy import scrape_with_playwright_sync
from .cardmarket_parser import CardmarketPricePlugin


def scrape_all_card_urls_from_set(set_url_base: str, max_pages: int = 20) -> list[dict]:
    collected_cards = []
    seen_numbers = set()
    
    for page in range(1, max_pages + 1):
        url = f"{set_url_base}&site={page}"
        html = scrape_with_playwright_sync(url, engine="playwright-stealth", headless=False)
        soup = BeautifulSoup(html, "html.parser")
        with open(f"debug_seite_{page}.html", "w", encoding="utf-8") as f:
            f.write(str(soup))

        card_rows = soup.select('div.table.table-striped.mb-3 div.row.g-0[id^="productRow"]')

        print(f"[Seite {page}] Gefundene card_rows: {len(card_rows)}")
        print(soup.title)
        if not card_rows:
            print(f"[Seite {page}] Keine card_rows gefunden, Abbruch.")
            break

        for row in card_rows:
            # Code- und Promo-Karten überspringen
            if row.select_one('svg[aria-label="Online Code Card"]') or "Live Code Card" in row.text:
                continue

            link_tag = row.select_one('a[href*="/Products/Singles/"]')
            number_div = row.select_one('div.col-md-2')
            price_normal_div = row.select_one('div.col-price.pe-sm-2')
            price_reverse_div = row.select_one('div.col-price.d-lg-flex')

            if not link_tag or not number_div:
                continue

            number = number_div.text.strip().lstrip("0")
            if not number.isdigit() or number in seen_numbers:
                continue

            seen_numbers.add(number)
            card_name = link_tag.text.strip()
            card_url = "https://www.cardmarket.com" + link_tag["href"]

            try:
                normal_price = float(price_normal_div.text.replace("€", "").replace(",", ".").strip())
            except:
                normal_price = None

            try:
                reverse_price = float(price_reverse_div.text.replace("€", "").replace(",", ".").strip())
            except:
                reverse_price = None

            collected_cards.append({
                "number": number,
                "name": card_name,
                "url": card_url,
                "price": normal_price,
                "reverse_price": reverse_price
            })


        time.sleep(1)
    return collected_cards
