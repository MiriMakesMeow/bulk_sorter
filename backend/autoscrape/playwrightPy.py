import asyncio
import random
import os
import sys
from typing import Optional, Dict, Any, List
import pathlib

DEFAULT_USER_AGENT_PATH = str(pathlib.Path(__file__).parent / "user-agents.txt")

async def scrape_with_playwright(
    url: str, 
    engine: str = 'playwright', 
    headless: bool = True, 
    timeout: int = 30000, 
    output_file: Optional[str] = None,
    user_agents_file: str = DEFAULT_USER_AGENT_PATH,
    simulate_human: bool = True
) -> str:
    """
    Scrape a URL using Playwright with multiple engine configurations.
    
    Args:
        url (str): The URL to scrape
        engine (str): The engine to use: 'playwright', 'playwright-stealth', or 'puppeteer-compat'
        headless (bool): Whether to run in headless mode
        timeout (int): Timeout in milliseconds
        output_file (str): Optional path to save the HTML output
        user_agents_file (str): Path to file containing user agents
        simulate_human (bool): Whether to simulate human behavior
        
    Returns:
        str: The HTML content of the page
    """
    from playwright.async_api import async_playwright
    #print(f"Using user agents from: {user_agents_file}")

    # Validate engine choice
    valid_engines = ['playwright', 'playwright-stealth', 'puppeteer-compat']
    if engine not in valid_engines:
        raise ValueError(f"Engine must be one of: {', '.join(valid_engines)}")
    
    #print(f"Scraping {url} with {engine} engine")
    
    # Load user agents
    user_agents = _load_user_agents(user_agents_file)
    user_agent = random.choice(user_agents)
    
    html = ""
    
    # Initialize resources
    p = await async_playwright().start()
    browser = None
    context = None
    page = None
    
    try:
        # Configure browser launch options based on engine
        launch_options = {
            "headless": headless,
        }
        
        # Add stealth-specific options
        if engine in ['playwright-stealth', 'puppeteer-compat']:
            launch_options["args"] = [
                '--disable-blink-features=AutomationControlled',
                '--disable-features=IsolateOrigins,site-per-process',
                '--disable-site-isolation-trials',
            ]
        
        # Launch browser
        browser = await p.chromium.launch(**launch_options)
        
        # Create browser context with options
        context_options = {
            "viewport": {'width': 1920, 'height': 1080},
            "user_agent": user_agent,
        }
        
        # Add stealth-specific context options
        if engine in ['playwright-stealth', 'puppeteer-compat']:
            context_options.update({
                "java_script_enabled": True,
                "bypass_csp": True,
                "extra_http_headers": {
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'none',
                    'Sec-Fetch-User': '?1',
                    'Cache-Control': 'max-age=0',
                }
            })
        
        context = await browser.new_context(**context_options)
        
        # Apply stealth script for more advanced protection
        if engine in ['playwright-stealth', 'puppeteer-compat']:
            stealth_page = await context.new_page()
            await stealth_page.add_init_script("""
                // Overwrite the webdriver property
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => false,
                });
                
                // Overwrite plugins array
                Object.defineProperty(navigator, 'plugins', {
                    get: () => {
                        return [{
                            0: {
                                type: 'application/x-google-chrome-pdf',
                                description: 'Portable Document Format'
                            },
                            name: 'Chrome PDF Plugin',
                            filename: 'internal-pdf-viewer',
                            description: 'Portable Document Format'
                        }];
                    },
                });
                
                // Overwrite languages
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en'],
                });
                
                // Overwrite permissions
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({state: Notification.permission}) :
                        originalQuery(parameters)
                );
            """)
            await stealth_page.close()
        
        # Create a new page for the actual scraping
        page = await context.new_page()
        
        # Navigate to the page with timeout
        response = await page.goto(url, timeout=timeout, wait_until="domcontentloaded")
        await page.wait_for_selector("a[href*='/en/Pokemon/Products/Singles/']", timeout=timeout)

        
        if not response:
            print(f"Failed to load {url}: No response")
            return ""
            
        if response.status >= 400:
            print(f"Failed to load {url}: Status code {response.status}")
            return ""
        
        # Wait to ensure page is fully loaded
        await page.wait_for_load_state("domcontentloaded")
        
        # Simulate human behavior if enabled
        if simulate_human and engine != 'playwright':  # Only for advanced modes
            await _simulate_human_behavior(page)
        
        # Important: Get the HTML content
        html = await page.content()
        
        # Save to output file if specified
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(html)
            print(f"HTML saved to {output_file}")
        
        return html
            
    except Exception as e:
        print(f"Error accessing {url}: {str(e)}")
        return ""
    finally:
        # Critical: Make sure to close everything in the correct order
        if page:
            await page.close()
        if context:
            await context.close()
        if browser:
            await browser.close()
        await p.stop()
        
        # Force exit for visible browser to make sure it closes
        if not headless:
            import gc
            gc.collect()

def scrape_with_playwright_sync(
    url: str, 
    engine: str = 'playwright', 
    headless: bool = True, 
    timeout: int = 30000, 
    output_file: Optional[str] = None,
    user_agents_file: str = DEFAULT_USER_AGENT_PATH,
    simulate_human: bool = True
) -> str:
    """
    Synchronous wrapper for scrape_with_playwright.
    
    This function has the same interface as scrape_with_js to make it easy
    to replace in existing code.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(scrape_with_playwright(
            url=url,
            engine=engine,
            headless=headless,
            timeout=timeout,
            output_file=output_file,
            user_agents_file=user_agents_file,
            simulate_human=simulate_human
        ))
        return result
    finally:
        loop.close()

async def _simulate_human_behavior(page) -> None:
    """Simulate human-like behavior on the page."""
    try:
        # Random delay between 1-2 seconds (shorter to avoid timeouts)
        await asyncio.sleep(random.uniform(0.5, 1))
        
        # Get viewport and page dimensions
        viewport_height = await page.evaluate("window.innerHeight")
        page_height = await page.evaluate("document.body.scrollHeight")
        
        # Perform fewer scroll actions to reduce chances of errors
        scroll_positions = [0, viewport_height, page_height // 2, page_height]
        for position in scroll_positions:
            # Scroll to position
            await page.evaluate(f"window.scrollTo(0, {position})")
            # Shorter pause
            await asyncio.sleep(random.uniform(0.3, 0.7))
        
        # Optionally move mouse once
        if random.random() > 0.5:
            x = random.randint(100, 800)
            y = random.randint(100, 600)
            await page.mouse.move(x, y)
        
        # Final short delay
        await asyncio.sleep(0.5)
    except Exception as e:
        print(f"Error during human simulation: {str(e)}")
        # Continue execution even if human simulation fails

def _load_user_agents(user_agents_file: str) -> List[str]:
    """Load user agents from file."""
    try:
        with open(user_agents_file, 'r') as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print(f"Warning: User agents file '{user_agents_file}' not found. Using default user agent.")
        return ["Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"]

# For backwards compatibility with the original scrape_with_js function
def scrape_with_js(
    url: str, 
    engine: str = 'hero', 
    headless: bool = True, 
    timeout: int = 30000, 
    output_file: Optional[str] = None
) -> str:
    """
    Maintain compatibility with the original scrape_with_js function.
    
    This function maps the old engine names to the new ones and calls scrape_with_playwright_sync.
    """
    # Map old engine names to new ones
    engine_map = {
        'hero': 'playwright',
        'puppeteer': 'playwright',
        'puppeteer-extra': 'playwright-stealth',
        'puppeteer-stealth': 'playwright-stealth'
    }
    
    playwright_engine = engine_map.get(engine, 'playwright')
    
    return scrape_with_playwright_sync(
        url=url,
        engine=playwright_engine,
        headless=headless,
        timeout=timeout,
        output_file=output_file
    )

# Example usage with more error handling
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Scrape a website using Playwright with various configurations')
    parser.add_argument('url', nargs='?', default="https://example.com", help='URL to scrape')
    parser.add_argument('--engine', '-e', choices=['playwright', 'playwright-stealth', 'puppeteer-compat'], 
                      default='playwright', help='Browser engine configuration to use')
    parser.add_argument('--visible', '-v', action='store_true', help='Show browser window')
    parser.add_argument('--output', '-o', help='Output file for HTML')
    parser.add_argument('--timeout', '-t', type=int, default=30000, help='Timeout in milliseconds')
    parser.add_argument('--user-agents', '-u', default='user-agents.txt', help='Path to user agents file')
    parser.add_argument('--no-human', action='store_true', help='Disable human behavior simulation')
    
    args = parser.parse_args()
    
    try:
        html = scrape_with_playwright_sync(
            url=args.url,
            engine=args.engine,
            headless=not args.visible,
            timeout=args.timeout,
            output_file=args.output,
            user_agents_file=args.user_agents,
            simulate_human=not args.no_human
        )
        
        if not args.output:
            print(f"HTML length: {len(html)} characters")
            if html:
                print(html[:500] + "..." if len(html) > 500 else html)
    except Exception as e:
        print(f"Error: {str(e)}")
        sys.exit(1)