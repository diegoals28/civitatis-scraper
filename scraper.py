"""
Civitatis Tour Operator Scraper
Extracts and compares local tour operators for different schedules on the same day.
"""

import asyncio
import re
from datetime import datetime
from playwright.async_api import async_playwright, Page, Browser


async def select_date_on_calendar(page: Page, date: str) -> bool:
    """
    Navigate the Civitatis calendar and select a specific date.

    Args:
        page: Playwright page instance
        date: Date in format YYYY-MM-DD

    Returns:
        True if date was selected successfully
    """
    date_obj = datetime.strptime(date, "%Y-%m-%d")
    target_day = date_obj.day
    target_month = date_obj.month
    target_year = date_obj.year

    # Wait for calendar to load
    try:
        await page.wait_for_selector('.clndr-table, .clndr, .calendar, [class*="calendar"]', timeout=15000)
    except Exception as e:
        return False

    # Wait for calendar to fully render
    await page.wait_for_timeout(3000)

    # Check current calendar state by looking at day classes to determine year/month
    first_day = page.locator('.clndr-table td.day:not(.adjacent-month)').first
    if await first_day.count() > 0:
        first_day_class = await first_day.get_attribute('class') or ""
        date_match = re.search(r'calendar-day-(\d{4})-(\d{2})-(\d{2})', first_day_class)
        if date_match:
            cal_year = int(date_match.group(1))
            cal_month = int(date_match.group(2))

            # Navigate to correct month if needed
            if not (cal_year == target_year and cal_month == target_month):
                months_diff = (target_year - cal_year) * 12 + (target_month - cal_month)

                for _ in range(abs(months_diff)):
                    if months_diff > 0:
                        next_btn = page.locator('.clndr-controls .clndr-next-button, .clndr-next-button').first
                    else:
                        next_btn = page.locator('.clndr-controls .clndr-previous-button, .clndr-previous-button').first

                    if await next_btn.count() > 0:
                        await next_btn.click()
                        await page.wait_for_timeout(600)
                    else:
                        break

    await page.wait_for_timeout(500)

    # Format the date for class selector (calendar-day-YYYY-MM-DD)
    date_str = f"{target_year}-{target_month:02d}-{target_day:02d}"

    # Use attribute contains selector to handle whitespace issues in classes
    date_class_selector = f'td[class*="calendar-day-{date_str}"]'
    date_element = page.locator(date_class_selector).first

    if await date_element.count() > 0:
        classes = await date_element.get_attribute('class') or ""
        # Check if it's available (not inactive)
        if 'inactive' not in classes:
            await date_element.click()
            await page.wait_for_timeout(2000)
            return True

    # Fallback: iterate through all day cells and check class attribute
    all_days = page.locator('.clndr-table td.day')
    day_count = await all_days.count()

    for i in range(day_count):
        cell = all_days.nth(i)
        classes = await cell.get_attribute('class') or ""
        classes_normalized = ' '.join(classes.split())

        if f'calendar-day-{date_str}' in classes_normalized:
            if 'inactive' not in classes_normalized:
                await cell.click()
                await page.wait_for_timeout(2000)
                return True
            else:
                return False

    return False


async def get_schedules_and_operators(page: Page, url: str, date: str, language: str = "es") -> list[dict]:
    """
    Navigate to tour, select date, and extract all schedules with operator info.

    Args:
        page: Playwright page instance
        url: Civitatis tour URL
        date: Date in format YYYY-MM-DD
        language: Language code

    Returns:
        List of dictionaries with time, operator, and price
    """
    results = []

    # Navigate to the tour page
    await page.goto(url, wait_until="domcontentloaded", timeout=60000)
    await page.wait_for_timeout(3000)

    # Accept cookies if present
    cookie_btn = page.locator('button#didomi-notice-agree-button, [class*="cookie"] button, .accept-cookies')
    if await cookie_btn.count() > 0:
        await cookie_btn.first.click()
        await page.wait_for_timeout(500)

    # Close chat popup if present
    chat_close_selectors = [
        '.ic-close',
        '[class*="chat"] .close',
        '[class*="chat"] button[class*="close"]',
        '.chat-close',
        '[aria-label="Close"]',
        '[aria-label="Cerrar"]',
    ]
    for selector in chat_close_selectors:
        chat_close = page.locator(selector).first
        if await chat_close.count() > 0:
            try:
                await chat_close.click()
                await page.wait_for_timeout(300)
            except:
                pass

    # Scroll to the booking section
    booking_section = page.locator('#formReservaActividad, #activity-navbar, .booking-form')
    if await booking_section.count() > 0:
        await booking_section.first.scroll_into_view_if_needed()
        await page.wait_for_timeout(1000)

    # Select the date
    date_selected = await select_date_on_calendar(page, date)
    if not date_selected:
        return [{"time": "N/A", "operator": "No se pudo seleccionar la fecha", "price": None}]

    # Wait for schedule options to appear
    await page.wait_for_timeout(2000)

    # Extract schedules from the select element or radio buttons
    schedules = []

    # Try select element first (more reliable)
    schedule_select = page.locator('#horaActividad option')
    select_count = await schedule_select.count()

    if select_count > 1:  # First option is empty placeholder
        for i in range(1, select_count):  # Skip first empty option
            option = schedule_select.nth(i)
            value = await option.get_attribute('value') or ""
            if value:
                quota = await option.get_attribute('data-quota') or ""
                # If quota has a number, it means limited availability
                quota_text = None
                if quota and quota.strip():
                    quota_text = f"Ultimas {quota} plazas"
                schedules.append({
                    "time": value,
                    "index": i - 1,
                    "quota": quota_text
                })

    # If no select options, try radio buttons
    if not schedules:
        radio_buttons = page.locator('input[name="horaActividad-radios"]')
        radio_count = await radio_buttons.count()

        for i in range(radio_count):
            radio = radio_buttons.nth(i)
            value = await radio.get_attribute('value') or ""
            if value:
                schedules.append({
                    "time": value,
                    "index": i,
                    "quota": None
                })

    if not schedules:
        # Fallback: look for any time patterns in the form
        form_text = await page.locator('#formActividad').text_content() or ""
        times = re.findall(r'\b(\d{1,2}:\d{2})\b', form_text)
        for i, t in enumerate(sorted(set(times))):
            schedules.append({"time": t, "index": i, "quota": None})

    if not schedules:
        operator = await extract_operator_info(page)
        price = await extract_price(page)
        return [{"time": "N/A", "operator": "No se encontraron horarios", "price": price}]

    # Known provider mappings
    provider_names = {
        "36417": "Enroma",
        "285": "Tourismotion",
        "6130": "Vivicos",
        "54973": "Rutasromanas",
    }

    # For each schedule, select it and get the provider ID and price
    for schedule in schedules:
        # Try clicking the radio button first (more reliable for triggering price updates)
        radio_clicked = False
        radio_selector = f'input[name="horaActividad-radios"][value="{schedule["time"]}"]'
        radio_btn = page.locator(radio_selector)

        if await radio_btn.count() > 0:
            try:
                await radio_btn.click()
                radio_clicked = True
                await page.wait_for_timeout(600)  # Wait for price to update
            except:
                pass

        # Fallback to select if radio click didn't work
        if not radio_clicked:
            await page.evaluate(f'''() => {{
                const select = document.getElementById('horaActividad');
                if (select) {{
                    select.value = '{schedule["time"]}';
                    select.dispatchEvent(new Event('change', {{ bubbles: true }}));
                }}
            }}''')
            await page.wait_for_timeout(600)  # Wait for price to update

        # Get provider ID for this schedule
        proveedor_field = page.locator('#idProveedor')
        provider_id = ""
        if await proveedor_field.count() > 0:
            provider_id = await proveedor_field.get_attribute('value') or ""

        # Get operator name from mapping or show ID
        operator = provider_names.get(provider_id, f"Proveedor #{provider_id}") if provider_id else "Desconocido"

        # Extract price for this specific schedule
        price = await extract_price(page)

        results.append({
            "time": schedule["time"],
            "operator": operator,
            "price": price,
            "quota": schedule.get("quota"),
            "provider_id": provider_id
        })

    return results


async def extract_operator_info(page: Page) -> str:
    """Extract operator/provider information from the page."""

    # List of selectors to try for operator info
    operator_selectors = [
        '.operator-name',
        '.provider-name',
        '[class*="operator"]',
        '[class*="provider"]',
        '[data-operator]',
        '.activity-operator',
        '.tour-operator',
        '.m-cart-item__operator',
        '.cart-operator',
    ]

    for selector in operator_selectors:
        element = page.locator(selector).first
        if await element.count() > 0:
            text = await element.text_content()
            if text and len(text.strip()) > 0:
                return text.strip()

    # Try to find in page content with regex
    content = await page.content()

    # Look for "Operador:" or "Provider:" patterns
    patterns = [
        r'[Oo]perador[:\s]+([^<\n,]+)',
        r'[Pp]rovider[:\s]+([^<\n,]+)',
        r'[Oo]rganizador[:\s]+([^<\n,]+)',
        r'"operator"[:\s]*"([^"]+)"',
        r'"provider"[:\s]*"([^"]+)"',
    ]

    for pattern in patterns:
        match = re.search(pattern, content)
        if match:
            operator = match.group(1).strip()
            if len(operator) > 2 and len(operator) < 100:
                return operator

    return "No encontrado"


async def extract_price(page: Page) -> str:
    """Extract price information from the page."""

    # Try to get the price from the booking form price display
    # This is the price that updates when selecting a schedule
    price_selectors = [
        '#tPrecioSpan0',  # Adult price in booking form
        '.m-activity-price__top .a-text--price--big',
        '.a-text--price--big',
        '.pax-price',
        '[class*="price-final"]',
        '.total-price',
        '#precioTotal',
        '.booking-price',
    ]

    for selector in price_selectors:
        element = page.locator(selector).first
        if await element.count() > 0:
            text = await element.text_content() or ""
            text = text.strip()
            # Extract numeric price with € symbol
            price_match = re.search(r'(\d+[.,]?\d*)\s*€', text)
            if price_match:
                return price_match.group(1) + " €"
            # Try without € symbol
            price_match = re.search(r'(\d+[.,]\d{2})', text)
            if price_match:
                return price_match.group(1) + " €"

    # Try to find price in the page via JavaScript
    try:
        price_js = await page.evaluate('''() => {
            // Try to get from price spans
            const priceEl = document.querySelector('#tPrecioSpan0');
            if (priceEl) return priceEl.textContent;

            // Try booking form total
            const totalEl = document.querySelector('.m-activity-price__total');
            if (totalEl) return totalEl.textContent;

            return null;
        }''')
        if price_js:
            price_match = re.search(r'(\d+[.,]?\d*)\s*€?', price_js)
            if price_match:
                return price_match.group(1) + " €"
    except:
        pass

    return None


async def compare_all_schedules(url: str, date: str, language: str = "es") -> list[dict]:
    """
    Main function to compare operators across all available schedules.

    Args:
        url: Civitatis tour URL
        date: Date in format YYYY-MM-DD
        language: Language code (es, en, etc.)

    Returns:
        List of dictionaries with time, operator, and price for each schedule
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="es-ES"
        )

        page = await context.new_page()

        try:
            results = await get_schedules_and_operators(page, url, date, language)
            return results if results else [{"time": "N/A", "operator": "No se encontraron resultados", "price": None}]
        except Exception as e:
            return [{"time": "N/A", "operator": f"Error: {str(e)}", "price": None}]
        finally:
            await browser.close()


# For testing
if __name__ == "__main__":
    import sys

    test_url = "https://www.civitatis.com/es/roma/visita-guiada-roma-antigua/"
    test_date = "2025-02-15"

    if len(sys.argv) > 1:
        test_url = sys.argv[1]
    if len(sys.argv) > 2:
        test_date = sys.argv[2]

    print(f"Testing scraper with URL: {test_url}")
    print(f"Date: {test_date}")

    results = asyncio.run(compare_all_schedules(test_url, test_date))

    print("\nResults:")
    for r in results:
        print(f"  {r['time']} - {r['operator']} - {r.get('price', 'N/A')}€")
