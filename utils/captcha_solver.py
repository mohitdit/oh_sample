import requests
import base64
from typing import Optional
import asyncio
import time

class CaptchaSolver:
    def __init__(self, username: str, password: str):
        """
        Initialize DeathByCaptcha solver using correct HTTP API
        Args:
            username: DBC username
            password: DBC password
        """
        self.username = username
        self.password = password
        # CORRECT DBC API endpoint
        self.base_url = "http://api.dbcapi.me/api"
        self.last_response_text = ""
        self.last_captcha_id = None
        
    def get_balance(self) -> float:
        """Get account balance using GET request to base API"""
        try:
            # According to DBC docs: GET or POST to https://api.dbcapi.me/api
            response = requests.post(
                self.base_url,  # Changed from /api/user to /api
                data={
                    "username": self.username,
                    "password": self.password
                },
                headers={
                    "Accept": "application/json"  # Request JSON response
                },
                timeout=30
            )
            
            print(f"Balance check: Status {response.status_code}")
            print(f"Balance response text: {response.text[:200]}")
            
            if response.status_code == 200:
                # Try to parse as JSON
                try:
                    data = response.json()
                    print(f"Balance response JSON: {data}")
                    
                    if 'balance' in data:
                        # Balance is in US cents, convert to dollars
                        balance = float(data.get('balance', 0)) / 100
                        print(f"✅ Account balance: ${balance:.2f}")
                        return balance
                    else:
                        print("⚠️ No balance field in response, but authenticated successfully")
                        return 999.99  # Assume sufficient balance if authenticated
                except ValueError as e:
                    print(f"❌ JSON parsing error: {e}")
                    print(f"Response was: {response.text}")
                    return 0.0
            else:
                print(f"❌ Balance check failed with status {response.status_code}")
                print(f"Response: {response.text}")
                return 0.0
            
        except Exception as e:
            print(f"❌ Error checking balance: {e}")
            import traceback
            traceback.print_exc()
            return 0.0

    async def solve_captcha_from_bytes(self, image_bytes: bytes) -> bool:
        """
        Solve captcha from image bytes (async wrapper)
        Args:
            image_bytes: Raw image bytes
        Returns:
            True if successful, False otherwise
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._solve_sync, image_bytes)
    
    def _solve_sync(self, image_bytes: bytes) -> bool:
        """
        Synchronous captcha solving using CORRECT DBC HTTP API
        CRITICAL: Must use multipart/form-data with actual image bytes
        """
        try:
            print(f"📤 Uploading captcha ({len(image_bytes)} bytes)...")
            
            # Step 1: Upload the captcha using multipart/form-data
            files = {
                'captchafile': ('captcha.png', image_bytes, 'image/png')
            }
            
            data = {
                'username': self.username,
                'password': self.password
            }
            
            headers = {
                'Accept': 'application/json',
                'Expect': ''  # Disable Expect: 100-continue
            }
            
            response = requests.post(
                f"{self.base_url}/captcha",
                data=data,
                files=files,
                headers=headers,
                timeout=120
            )
            
            print(f"Upload status: {response.status_code}")
            print(f"Upload response: {response.text[:500]}")
            
            if response.status_code not in [200, 303]:
                print(f"❌ Upload failed: {response.status_code}")
                print(f"Response: {response.text}")
                return False
            
            # Parse response
            try:
                data = response.json()
            except ValueError:
                print(f"❌ Could not parse JSON response: {response.text}")
                return False
            
            # Check for errors in response
            if data.get('status') == 255:
                print(f"❌ API Error: {data.get('error', 'Unknown error')}")
                return False
            
            captcha_id = data.get('captcha')
            
            if not captcha_id:
                print(f"❌ No captcha ID returned. Response: {data}")
                return False
            
            self.last_captcha_id = captcha_id
            print(f"✅ Captcha uploaded. ID: {captcha_id}")
            
            # Check if already solved
            if data.get('text'):
                self.last_response_text = str(data['text']).strip()
                print(f"✅ Solved immediately: '{self.last_response_text}'")
                return True
            
            # Step 2: Poll for the solution
            print("⏳ Waiting for solution...")
            max_attempts = 60  # 60 attempts = 120 seconds max
            
            for attempt in range(max_attempts):
                time.sleep(2)
                
                try:
                    response = requests.get(
                        f"{self.base_url}/captcha/{captcha_id}",
                        headers={'Accept': 'application/json'},
                        timeout=30
                    )
                    
                    if response.status_code == 200:
                        try:
                            data = response.json()
                        except ValueError:
                            if attempt % 10 == 0:
                                print(f"⚠️ Invalid JSON response on attempt {attempt}")
                            continue
                        
                        text = str(data.get('text', '')).strip()
                        is_correct = data.get('is_correct')
                        
                        # Check if solved (text exists and marked as correct)
                        # In DBC API: is_correct=1 means solved or processing, is_correct=0 means failed
                        if text and is_correct:
                            self.last_response_text = text
                            print(f"✅ Captcha solved: '{self.last_response_text}'")
                            return True
                        
                        # Check if failed
                        if is_correct == 0 or is_correct is False:
                            print(f"❌ Captcha marked as incorrectly solved by DBC")
                            return False
                    
                    if attempt % 10 == 0 and attempt > 0:
                        print(f"⏳ Still waiting... ({attempt}/{max_attempts})")
                        
                except Exception as e:
                    if attempt % 20 == 0:
                        print(f"Poll error: {str(e)[:50]}")
                    continue
            
            print("❌ Captcha solving timed out")
            return False
                
        except Exception as e:
            print(f"❌ Error solving captcha: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def report_incorrect(self) -> bool:
        """
        Report the last captcha as incorrectly solved (gets refund)
        """
        if self.last_captcha_id:
            try:
                response = requests.post(
                    f"{self.base_url}/captcha/{self.last_captcha_id}/report",
                    data={
                        "username": self.username,
                        "password": self.password
                    },
                    headers={'Accept': 'application/json'},
                    timeout=30
                )
                if response.status_code == 200:
                    print(f"✅ Reported captcha {self.last_captcha_id} as incorrect")
                    return True
                else:
                    print(f"❌ Report failed: {response.status_code}")
                    print(f"Response: {response.text}")
                    return False
            except Exception as e:
                print(f"❌ Error reporting captcha: {e}")
                return False
        return False


# Convenience function for backward compatibility
async def solve_captcha(image_bytes: bytes) -> Optional[str]:
    """
    Solve captcha from image bytes using DeathByCaptcha
    Returns the captcha text or None if failed
    """
    DBC_USERNAME = "hr@dharani.co.in"
    DBC_PASSWORD = "Dh@r@ni@gnt99!"
    
    solver = CaptchaSolver(DBC_USERNAME, DBC_PASSWORD)
    
    # Check balance first
    balance = solver.get_balance()
    print(f"💰 DBC Account Balance: ${balance:.2f}")
    
    if balance <= 0:
        print("❌ Insufficient balance in DeathByCaptcha account")
        return None
    
    success = await solver.solve_captcha_from_bytes(image_bytes)
    
    if success:
        return solver.last_response_text
    else:
        print("❌ Captcha solving failed")
        return None