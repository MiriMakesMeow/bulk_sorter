from dataclasses import dataclass
from typing import Any, Optional, List, Type, Union
from bs4 import BeautifulSoup
import html
import re
from templated_plugin import ScrapedField, DataType

class CardmarketPricePlugin:
    """Plugin that extracts price information from Cardmarket pages."""
    
    # Global configuration flag to control whether prices are stored as floats or formatted strings
    STORE_PRICES_AS_FLOAT = True  
    
    def get_name(self) -> str:
        """Return the name of the plugin."""
        return "Cardmarket Price Plugin"
    
    def get_description(self) -> str:
        """Return a description of what the plugin extracts."""
        return "Extracts price information from Cardmarket product pages across different games and languages"
    
    def get_version(self) -> str:
        """Return the version of the plugin."""
        return "1.1.0"
    
    def get_available_fields(self) -> List[ScrapedField]:
        """
        Returns a list of all possible fields this plugin can extract, with realistic default values.
        Price values will be returned as floats or formatted strings based on STORE_PRICES_AS_FLOAT setting.
        
        Returns:
            List of ScrapedField objects with default values
        """
        return [
            ScrapedField(
                name="card_name",
                value="Example Card",
                field_type=DataType.STRING,
                description="Name of the card",
                accumulate=True
            ),
            ScrapedField(
                name="card_set",
                value="Example Set",
                field_type=DataType.STRING,
                description="Set/expansion the card belongs to",
                accumulate=True
            ),
            ScrapedField(
                name="available_items",
                value=500,
                field_type=DataType.INTEGER,
                description="Number of available items for sale",
                accumulate=True
            ),
            ScrapedField(
                name="lowest_price",
                value=1.00 if self.STORE_PRICES_AS_FLOAT else "1,00 €",
                field_type=DataType.FLOAT if self.STORE_PRICES_AS_FLOAT else DataType.STRING,
                description="Lowest price available for the card",
                accumulate=True
            ),
            ScrapedField(
                name="price_trend",
                value=5.00 if self.STORE_PRICES_AS_FLOAT else "5,00 €",
                field_type=DataType.FLOAT if self.STORE_PRICES_AS_FLOAT else DataType.STRING,
                description="Price trend of the card",
                accumulate=True
            ),
            ScrapedField(
                name="avg_30_days",
                value=4.75 if self.STORE_PRICES_AS_FLOAT else "4,75 €",
                field_type=DataType.FLOAT if self.STORE_PRICES_AS_FLOAT else DataType.STRING,
                description="Average price over the last 30 days",
                accumulate=True
            ),
            ScrapedField(
                name="avg_7_days",
                value=4.50 if self.STORE_PRICES_AS_FLOAT else "4,50 €",
                field_type=DataType.FLOAT if self.STORE_PRICES_AS_FLOAT else DataType.STRING,
                description="Average price over the last 7 days",
                accumulate=True
            ),
            ScrapedField(
                name="avg_1_day",
                value=4.25 if self.STORE_PRICES_AS_FLOAT else "4,25 €",
                field_type=DataType.FLOAT if self.STORE_PRICES_AS_FLOAT else DataType.STRING,
                description="Average price over the last day",
                accumulate=True
            ),
            ScrapedField(
                name="card_rarity",
                value="Uncommon",
                field_type=DataType.STRING,
                description="Rarity of the card",
                accumulate=True
            ),
            ScrapedField(
                name="card_number",
                value="123",
                field_type=DataType.STRING,
                description="Card number in the set",
                accumulate=True
            ),
            ScrapedField(
                name="card_expansion",
                value="Example Set",
                field_type=DataType.STRING,
                description="Expansion/set the card belongs to",
                accumulate=True
            )
        ]

    def _clean_price_string(self, price_string: str) -> str:
        """
        Clean and fix encoding issues in price strings.
        
        Args:
            price_string: Raw price string from HTML
            
        Returns:
            Cleaned price string with correct currency symbols
        """
        if not price_string:
            return ""
            
        # Handle common encoding issues
        cleaned = price_string.replace("â‚¬", "€")
        cleaned = cleaned.replace("Â£", "£")
        cleaned = cleaned.replace("Â$", "$")
        
        # Remove any extra whitespace
        cleaned = cleaned.strip()
        
        return cleaned
        
    def _parse_price_to_float(self, price_string: str) -> float:
        """
        Parse a price string into a float value, removing currency symbols.
        
        Args:
            price_string: Cleaned price string (e.g. "13,98 €")
            
        Returns:
            Float value of the price or 0.0 if parsing fails
        """
        if not price_string:
            return 0.0
            
        try:
            # Remove currency symbols and other non-numeric characters
            cleaned = ''.join(c for c in price_string if c.isdigit() or c in ',.').strip()
            
            # Handle European number format (comma as decimal separator)
            if ',' in cleaned and '.' in cleaned:
                # If both are present, assume European format with thousand separators
                cleaned = cleaned.replace('.', '')  # Remove thousand separators
                cleaned = cleaned.replace(',', '.')  # Convert decimal separator
            elif ',' in cleaned:
                # Only comma present, assume it's a decimal separator
                cleaned = cleaned.replace(',', '.')
                
            return float(cleaned)
        except ValueError:
            return 0.0

    def parse(self, html_content: str) -> List[ScrapedField]:
        """
        Parse HTML content and extract Cardmarket price information.
        
        Args:
            html_content: Raw HTML string
            
        Returns:
            List of ScrapedField objects with price data
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        results = []
        
        # Extract card name and set
        try:
            title_container = soup.select_one('.page-title-container')
            if title_container:
                h1 = title_container.select_one('h1')
                if h1:
                    # Extract main card name (text before the span)
                    card_name = h1.get_text().strip()
                    set_span = h1.select_one('span')
                    if set_span:
                        card_name = card_name.replace(set_span.get_text(), '').strip()
                        card_set = set_span.get_text().strip()
                        
                        results.append(ScrapedField(
                            name="card_name",
                            value=card_name,
                            field_type=DataType.STRING,
                            description="Name of the card",
                            accumulate=True
                        ))
                        
                        results.append(ScrapedField(
                            name="card_set",
                            value=card_set,
                            field_type=DataType.STRING,
                            description="Set/expansion the card belongs to",
                            accumulate=True
                        ))
        except Exception as e:
            # Continue even if card name extraction fails
            pass
        
        # Find the info container using a class-based selector
        container = soup.select_one('.info-list-container')
        
        if not container:
            # If we can't find the container, return what we have so far
            return results
            
        # Find the definition list containing the key-value pairs
        dl = container.select_one('dl')
        if not dl:
            return results
            
        # Extract all definition terms and values
        dt_elements = dl.select('dt')
        dd_elements = dl.select('dd')
        
        # Create a dictionary to map field keys to values
        price_data = {}
        for i in range(min(len(dt_elements), len(dd_elements))):
            key = dt_elements[i].get_text().strip()
            # For the value, extract the text or try to find a specific span
            value_elem = dd_elements[i].select_one('span')
            value = value_elem.get_text().strip() if value_elem else dd_elements[i].get_text().strip()
            price_data[key] = value
        
        # Extract card rarity
        if "Rarity" in price_data:
            # The actual text is in the SVG tooltip, so we'll extract the aria-label
            rarity_dd = None
            for i, dt in enumerate(dt_elements):
                if dt.get_text().strip() == "Rarity" and i < len(dd_elements):
                    rarity_dd = dd_elements[i]
                    break
                    
            rarity_value = "Unknown"
            if rarity_dd:
                svg_elem = rarity_dd.select_one('svg')
                if svg_elem and svg_elem.get('aria-label'):
                    rarity_value = svg_elem.get('aria-label')
                else:
                    # Try to get any text in the dd element
                    rarity_value = rarity_dd.get_text().strip()
            
            results.append(ScrapedField(
                name="card_rarity",
                value=rarity_value,
                field_type=DataType.STRING,
                description="Rarity of the card",
                accumulate=True
            ))
        
        # Extract card number
        number_value = None
        for key in price_data:
            if 'Number' in key:
                number_value = price_data[key]
                break
        
        if number_value:
            results.append(ScrapedField(
                name="card_number",
                value=number_value,
                field_type=DataType.STRING,
                description="Card number in the set",
                accumulate=True
            ))
        
        # Extract available items
        available_items_value = None
        for key in price_data:
            if any(term in key.lower() for term in ['available', 'artikel', 'articles']):
                available_items_value = price_data[key]
                # Try to convert to integer
                try:
                    available_items_value = int(''.join(c for c in available_items_value if c.isdigit()))
                except (ValueError, TypeError):
                    pass
                break
        
        if available_items_value is not None:
            results.append(ScrapedField(
                name="available_items",
                value=available_items_value,
                field_type=DataType.INTEGER if isinstance(available_items_value, int) else DataType.STRING,
                description="Number of available items for sale",
                accumulate=True
            ))
        
        # Extract lowest price
        lowest_price = None
        for key in price_data:
            if any(term == key.lower() for term in ['from', 'de', 'ab']):
                cleaned_price = self._clean_price_string(price_data[key])
                if self.STORE_PRICES_AS_FLOAT:
                    lowest_price = self._parse_price_to_float(cleaned_price)
                else:
                    lowest_price = cleaned_price
                break
        
        if lowest_price is not None:
            results.append(ScrapedField(
                name="lowest_price",
                value=lowest_price,
                field_type=DataType.FLOAT if self.STORE_PRICES_AS_FLOAT else DataType.STRING,
                description="Lowest price available for the card",
                accumulate=True
            ))
        
        # Extract price trend
        price_trend = None
        for key in price_data:
            if any(term in key.lower() for term in ['trend', 'tendance']):
                cleaned_price = self._clean_price_string(price_data[key])
                if self.STORE_PRICES_AS_FLOAT:
                    price_trend = self._parse_price_to_float(cleaned_price)
                else:
                    price_trend = cleaned_price
                break
        
        if price_trend is not None:
            results.append(ScrapedField(
                name="price_trend",
                value=price_trend,
                field_type=DataType.FLOAT if self.STORE_PRICES_AS_FLOAT else DataType.STRING,
                description="Price trend of the card",
                accumulate=True
            ))
        
        # Extract 30-day average
        avg_30_days = None
        for key in price_data:
            if '30' in key and any(term in key.lower() for term in ['day', 'jour', 'tage']):
                cleaned_price = self._clean_price_string(price_data[key])
                if self.STORE_PRICES_AS_FLOAT:
                    avg_30_days = self._parse_price_to_float(cleaned_price)
                else:
                    avg_30_days = cleaned_price
                break
        
        if avg_30_days is not None:
            results.append(ScrapedField(
                name="avg_30_days",
                value=avg_30_days,
                field_type=DataType.FLOAT if self.STORE_PRICES_AS_FLOAT else DataType.STRING,
                description="Average price over the last 30 days",
                accumulate=True
            ))
        
        # Extract 7-day average
        avg_7_days = None
        for key in price_data:
            if '7' in key and any(term in key.lower() for term in ['day', 'jour', 'tage']):
                cleaned_price = self._clean_price_string(price_data[key])
                if self.STORE_PRICES_AS_FLOAT:
                    avg_7_days = self._parse_price_to_float(cleaned_price)
                else:
                    avg_7_days = cleaned_price
                break
        
        if avg_7_days is not None:
            results.append(ScrapedField(
                name="avg_7_days",
                value=avg_7_days,
                field_type=DataType.FLOAT if self.STORE_PRICES_AS_FLOAT else DataType.STRING,
                description="Average price over the last 7 days",
                accumulate=True
            ))
        
        # Extract 1-day average
        avg_1_day = None
        for key in price_data:
            if '1' in key and any(term in key.lower() for term in ['day', 'jour', 'tage']):
                cleaned_price = self._clean_price_string(price_data[key])
                if self.STORE_PRICES_AS_FLOAT:
                    avg_1_day = self._parse_price_to_float(cleaned_price)
                else:
                    avg_1_day = cleaned_price
                break
        
        if avg_1_day is not None:
            results.append(ScrapedField(
                name="avg_1_day",
                value=avg_1_day,
                field_type=DataType.FLOAT if self.STORE_PRICES_AS_FLOAT else DataType.STRING,
                description="Average price over the last day",
                accumulate=True
            ))
        
        # Extract card expansion (though we already got it from the title)
        card_expansion = None
        for key in price_data:
            if any(term in key.lower() for term in ['printed in', 'edité dans', 'erschienen in']):
                card_expansion = price_data[key]
                break
        
        if card_expansion:
            results.append(ScrapedField(
                name="card_expansion",
                value=card_expansion,
                field_type=DataType.STRING,
                description="Expansion/set the card belongs to",
                accumulate=True
            ))
        
        return results