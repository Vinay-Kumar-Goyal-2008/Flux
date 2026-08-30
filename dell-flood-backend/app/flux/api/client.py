import os
import requests
from dotenv import load_dotenv

load_dotenv()

class MireyeAPIError(Exception):
    pass

class MireyeClient:
    def __init__(self, api_token: str = None, base_url: str = 'https://api.mireye.com'):
        self.api_token = api_token or os.getenv('MIREYE_API_TOKEN', '')
        self.base_url = base_url

    def _headers(self):
        return {
            'Authorization': f'Bearer {self.api_token}',
            'Content-Type': 'application/json'
        }

    def fetch(self, lat: float = None, lng: float = None, address: str = None, fields: list = None, preset: str = None):
        payload = {}
        if address:
            payload['address'] = address
        elif lat is not None and lng is not None:
            payload['lat'] = float(lat)
            payload['lng'] = float(lng)
        if fields:
            payload['fields'] = fields
        if preset:
            payload['preset'] = preset
        
        try:
            resp = requests.post(f'{self.base_url}/v1/fetch', headers=self._headers(), json=payload, timeout=60)
            if resp.status_code == 200:
                return resp.json()
            return {'error': f'HTTP {resp.status_code}', 'detail': resp.text}
        except Exception as e:
            return {'error': str(e)}

    def ask(self, question: str, lat: float = None, lng: float = None, address: str = None):
        payload = {'question': question}
        if address:
            payload['address'] = address
        elif lat is not None and lng is not None:
            payload['lat'] = float(lat)
            payload['lng'] = float(lng)
        try:
            resp = requests.post(f'{self.base_url}/v1/ask', headers=self._headers(), json=payload, timeout=90)
            if resp.status_code == 200:
                return resp.json()
            return {'error': f'HTTP {resp.status_code}', 'detail': resp.text}
        except Exception as e:
            return {'error': str(e)}

    def geocode(self, address: str):
        try:
            resp = requests.post(f'{self.base_url}/v1/geocode', headers=self._headers(), json={'address': address}, timeout=30)
            if resp.status_code == 200:
                return resp.json()
            return {'error': f'HTTP {resp.status_code}'}
        except Exception as e:
            return {'error': str(e)}
