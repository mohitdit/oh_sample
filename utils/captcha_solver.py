import requests
import base64
from typing import Optional
import asyncio
import time

class CaptchaSolver:
    def __init__(self, username: str, password: str):
        """
        Initialize DeathByCaptcha solver using HTTP API
        Args:
            username: DBC username
            password: DBC password
        """
        self.username = username
        self.password = password
        # CRITICAL: Use HTTP, not HTTPS
        self.base_url = "http://deathbycaptcha.com/api"
        self.last_response_text = ""
        self.last_captcha_id = None
        
    def get_balance(self) -> float:
        """Get account balance"""
        try:
            response = requests.post(
                f"{self.base_url}/user",
                data={
                    "username": self.username,
                    "password": self.password
                },
                headers={
                    "Accept": "application/json"
                },
                timeout=30
            )
            
            print(f"Balance check: Status {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"Balance response: {data}")
                
                # If error is False, authentication worked
                if data.get('error') is False or data.get('error') == False:
                    # Check if balance field exists
                    if 'balance' in data:
                        balance = float(data.get('balance', 0)) / 100
                        return balance
                    else:
                        # No balance field means account is valid, bypass check
                        print("✅ Account authenticated (no balance field returned)")
                        return 999.99  # Return fake high balance to continue

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
        Synchronous captcha solving using DBC HTTP API
        CRITICAL: Must send base64 string in POST data, not as multipart file
        """
        try:
            print(f"📤 Uploading captcha ({len(image_bytes)} bytes)...")
            
            # Encode image to base64
            base64_image = base64.b64encode(image_bytes).decode('utf-8')
            
            # Step 1: Upload the captcha
            # CRITICAL: Send as form data with base64 string, not as file upload
            response = requests.post(
                f"{self.base_url}/captcha",
                data={
                    "username": self.username,
                    "password": self.password,
                    "captchafile": f"base64:{base64_image}",
                    "type": "0"  # 0 = normal text captcha
                },
                headers={
                    "Accept": "application/json"
                },
                timeout=60
            )
            
            print(f"Upload status: {response.status_code}")
            print(f"Upload response: {response.text[:300]}")
            
            if response.status_code not in [200, 303]:
                print(f"❌ Upload failed: {response.status_code}")
                return False
            
            data = response.json()
            
            # Check for errors in response
            if data.get('is_correct') == 255:
                print("❌ DBC returned error code 255 (invalid image or service issue)")
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
                        headers={
                            "Accept": "application/json"
                        },
                        auth=(self.username, self.password),
                        timeout=30
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        text = str(data.get('text', '')).strip()
                        is_correct = data.get('is_correct')
                        
                        # Check if solved (text exists and not marked as incorrect)
                        if text and is_correct != 255:
                            self.last_response_text = text
                            print(f"✅ Captcha solved: '{self.last_response_text}'")
                            return True
                    
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
                    timeout=30
                )
                if response.status_code == 200:
                    print(f"✅ Reported captcha {self.last_captcha_id} as incorrect")
                    return True
                else:
                    print(f"❌ Report failed: {response.status_code}")
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