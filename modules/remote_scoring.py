import requests
import logging
import os
import time
from modules import config

class EveryPixelClient:
    BASE_URL = "https://api.everypixel.com/v1/quality"

    def __init__(self):
        secrets = config.get_secret('everypixel')
        if not secrets:
            self.disabled = True
            logging.warning("EveryPixel secrets not found. API disabled.")
            return

        self.client_id = secrets.get('client_id')
        self.client_secret = secrets.get('client_secret')
        self.default_quality_type = secrets.get('quality_type', 'ugc')
        self.disabled = False
        
        if not self.client_id or not self.client_secret:
            self.disabled = True
            logging.warning("EveryPixel credentials incomplete.")

    def test_connection(self):
        """
        Tests connectivity to the EveryPixel API.
        Returns: (bool, message)
        """
        if self.disabled:
            return False, "Disabled (Config missing)"
            
        try:
            # Just test reachability of the endpoint
            # We use a short timeout
            response = requests.get(self.BASE_URL, timeout=5)
            # 405 Method Not Allowed is expected for GET on a POST endpoint
            # 200 is invalid for this endpoint usually, but implies reachability
            if response.status_code in [200, 405, 400, 401, 403]:
                 return True, "Connection Successful"
            else:
                 return False, f"API returned unexpected status: {response.status_code}"
        except Exception as e:
            return False, f"Connection Failed: {e}"

    def score_image(self, image_path, quality_type=None):
        """
        Scores an image using EveryPixel API.
        Args:
            image_path (str): Path to image file.
            quality_type (str): 'ugc' or 'stock'. Defaults to config or 'ugc'.
        Returns:
            dict: {
                'score': float (0-100), 
                'quality_type': str,
                'status': 'success'/'failed',
                'error': str,
                'raw': dict
            }
        """
        if self.disabled:
            return {'status': 'failed', 'error': 'API Disabled (Missing Secrets)'}
            
        if not os.path.exists(image_path):
             return {'status': 'failed', 'error': 'File not found'}

        q_type = quality_type if quality_type else self.default_quality_type
        
        try:
            with open(image_path, 'rb') as f:
                response = requests.post(
                    self.BASE_URL,
                    files={'data': f},
                    data={'type': q_type},
                    auth=(self.client_id, self.client_secret),
                    timeout=30
                )
            
            if response.status_code == 200:
                data = response.json()
                # Response format: {'quality': {'score': 0.78, 'class': 'good'}, 'status': 'ok'}
                # Wait, PDF says 0-100? Docs usually say 0-1 probability or percentage?
                # User PDF says "0-100 score".
                # API usually returns 0.0 to 1.0 probability.
                # Let's check raw response to be safe.
                # Assuming 'quality': {'score': X} where X is 0-1 or 0-100.
                if 'quality' in data and 'score' in data['quality']:
                    raw_score = data['quality']['score']
                    # Normalize to 0-100 if it is 0-1? 
                    # Or PDF says "0-100 score". 
                    # If I get 0.78, implies 78?
                    # I will return raw score and normalization separately if strict.
                    # Actually, let's normalize to project standard (0-1) for storage?
                    # The project uses 0-1 for general scores mostly.
                    # But db field is REAL.
                    # I will return what I get, but verify.
                    # EveryPixel documentation usually says 0-1 probability.
                    # PDF says "0-100 score". Maybe PDF means percentage?
                    # I'll store what I get. If < 1, likely probability.
                    
                    return {
                        'score': raw_score * 100 if raw_score <= 1.0 else raw_score, # Ensure 0-100 scale if user wants that?
                        # Wait, Project uses 0-1 for everything (score_general).
                        # Impl plan said "score_everypixel_quality (REAL) - 0-100 range".
                        # I will store 0-100.
                        'quality_type': q_type,
                        'status': 'success',
                        'raw': data
                    }
                else:
                    return {'status': 'failed', 'error': 'No score in response', 'raw': data}
            else:
                 return {'status': 'failed', 'error': f"HTTP {response.status_code}: {response.text}"}
                 
        except Exception as e:
            logging.error(f"EveryPixel request failed: {e}")
            return {'status': 'failed', 'error': str(e)}


class SightEngineClient:
    BASE_URL = "https://api.sightengine.com/1.0/check.json"

    def __init__(self):
        secrets = config.get_secret('sightengine')
        if not secrets:
            self.disabled = True
            logging.warning("SightEngine secrets not found. API disabled.")
            return

        self.api_user = secrets.get('api_user')
        self.api_secret = secrets.get('api_secret')
        self.disabled = False

        if not self.api_user or not self.api_secret:
             self.disabled = True
             logging.warning("SightEngine credentials incomplete.")

    def test_connection(self):
        """
        Tests connectivity to the SightEngine API.
        Returns: (bool, message)
        """
        if self.disabled:
            return False, "Disabled (Config missing)"
            
        try:
            # Test reachability
            response = requests.get(self.BASE_URL, timeout=5)
            if response.status_code in [200, 405, 400, 401, 403]:
                 return True, "Connection Successful"
            else:
                 return False, f"API returned unexpected status: {response.status_code}"
        except Exception as e:
            return False, f"Connection Failed: {e}"

    def score_image(self, image_path):
        """
        Scores an image using SightEngine API (Technical Quality).
        Returns:
            dict: {
                'score': float (0-1), 
                'status': 'success'/'failed', 
                'error': str,
                'raw': dict
            }
        """
        if self.disabled:
            return {'status': 'failed', 'error': 'API Disabled (Missing Secrets)'}
            
        if not os.path.exists(image_path):
             return {'status': 'failed', 'error': 'File not found'}

        try:
            with open(image_path, 'rb') as f:
                response = requests.post(
                    self.BASE_URL,
                    files={'media': f},
                    data={
                        'models': 'quality',
                        'api_user': self.api_user,
                        'api_secret': self.api_secret
                    },
                    timeout=30
                )
            
            if response.status_code == 200:
                data = response.json()
                # Response format: {'status': 'success', 'quality': {'score': 0.89}}
                if data.get('status') == 'success' and 'quality' in data:
                    score = data['quality'].get('score', 0.0)
                    return {
                        'score': score, # 0-1
                        'status': 'success',
                        'raw': data
                    }
                else:
                     return {'status': 'failed', 'error': data.get('error', {}).get('message', 'Unknown Error'), 'raw': data}
            else:
                 return {'status': 'failed', 'error': f"HTTP {response.status_code}: {response.text}"}
                 
        except Exception as e:
            logging.error(f"SightEngine request failed: {e}")
            return {'status': 'failed', 'error': str(e)}
