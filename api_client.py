import requests
import json
from config import config
import logging

logger = logging.getLogger(__name__)

class APIClient:
    def __init__(self):
        self.base_url = config.API_URL
        self.session = requests.Session()
        self.token = None
    
    def set_token(self, token):
        """Set the authentication token"""
        self.token = token
        if token:
            self.session.headers.update({
                'Authorization': f'Bearer {token}'
            })
        else:
            self.session.headers.pop('Authorization', None)
    
    def _make_request(self, method, endpoint, data=None, params=None, requires_auth=False):
        """Make API request to backend"""
        url = f"{self.base_url}{endpoint}"
        
        headers = {'Content-Type': 'application/json'}
        
        if requires_auth and self.token:
            headers['Authorization'] = f'Bearer {self.token}'
            logger.info(f"🔑 Making authenticated request")
        else:
            logger.info(f"📡 Making public request")
        
        try:
            response = self.session.request(
                method=method,
                url=url,
                json=data,
                params=params,
                headers=headers,
                timeout=60
            )
            
            logger.info(f"📊 Response status: {response.status_code}")
            
            try:
                result = response.json()
            except:
                return {'success': False, 'message': 'Invalid response from server', 'status_code': response.status_code}
            
            if response.status_code >= 200 and response.status_code < 300:
                return {'success': True, 'data': result.get('data'), 'message': result.get('message', 'Success'), 'status_code': response.status_code}
            else:
                return {'success': False, 'message': result.get('message', 'Request failed'), 'status_code': response.status_code}
                
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Request error: {e}")
            return {'success': False, 'message': f'Connection error: {str(e)}'}
    
    # ============ User Endpoints ============
    
    def register_user(self, phone, password, tg_id, agent_id=None):
        """Register a new user"""
        data = {
            'phone': phone,
            'password': password,
            'tg_id': tg_id
        }
        
        if agent_id and agent_id.strip():
            data['agent_id'] = agent_id
        
        return self._make_request('POST', '/auth/register', data)
    
    def get_user_profile(self):
        """Get current user profile (requires auth)"""
        return self._make_request('GET', '/auth/profile', requires_auth=True)
    
    def get_user(self, user_id):
        """Get user by ID (requires auth)"""
        return self._make_request('GET', f'/user/{user_id}', requires_auth=True)
    
    def change_password(self, current_password, new_password):
        """Change user password (requires auth)"""
        data = {
            'currentPassword': current_password,
            'newPassword': new_password
        }
        return self._make_request('POST', '/auth/change-password', data, requires_auth=True)
    
    # ============ Wallet Endpoints ============
    
    def get_wallet(self):
        """Get current user's wallet (requires auth)"""
        return self._make_request('GET', '/wallet', requires_auth=True)
    
    def get_wallet_balance(self, user_id):
        """Get user's wallet balance (requires auth)"""
        return self._make_request('GET', f'/wallet/{user_id}', requires_auth=True)
    
    def create_transaction(self, data):
        """Create a new transaction (deposit/withdrawal) (requires auth)"""
        return self._make_request('POST', '/transactions', data, requires_auth=True)
    
    def get_transactions(self, user_id, limit=20, page=1):
        """Get user's transaction history (requires auth)"""
        params = {'limit': limit, 'page': page}
        return self._make_request('GET', f'/transactions/user/{user_id}', params=params, requires_auth=True)
    
    def get_transaction(self, transaction_id):
        """Get specific transaction details (requires auth)"""
        return self._make_request('GET', f'/transactions/{transaction_id}', requires_auth=True)
    
    # ============ Accountant Endpoints ============
    
    def get_accountants(self, blocked=False):
        """Get active accountants"""
        params = {'blocked': str(blocked).lower()}
        return self._make_request('GET', '/accountants', params=params, requires_auth=True)
    
    def generate_game_code(self, user_id):
        """Generate a one-time code for the game link"""
        data = {'userId': user_id}
        return self._make_request('POST', '/auth/generate-game-code', data, requires_auth=True)

    def exchange_game_code(self, code):
        """Exchange a game code for a JWT token"""
        data = {'code': code}
        return self._make_request('POST', '/auth/exchange-game-code', data)
    
    def refresh_token(self):
        """Refresh the current token using the refresh endpoint"""
        if not self.token:
            return {'success': False, 'message': 'No token to refresh'}
        
        headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {self.token}'}
        
        try:
            response = self.session.post(
                f"{self.base_url}/auth/refresh-token",
                headers=headers,
                timeout=60
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    new_token = result.get('data', {}).get('token')
                    if new_token:
                        self.set_token(new_token)
                        return {'success': True, 'token': new_token, 'data': result.get('data')}
            
            return {'success': False, 'message': 'Refresh failed'}
        except Exception as e:
            logger.error(f"❌ Refresh token error: {e}")
            return {'success': False, 'message': str(e)}
    
    # ✅ ADD THIS MISSING METHOD
    def check_user_by_telegram_id(self, tg_id):
        """Check if a user exists in the database by Telegram ID"""
        clean_tg_id = tg_id.replace('@', '').strip()
        return self._make_request('GET', f'/auth/check-user/{clean_tg_id}')
    
    def check_user_and_token(self, tg_id):
        """Single API call that checks user and token in one go"""
        clean_tg_id = tg_id.replace('@', '').strip()
        return self._make_request('GET', f'/auth/check-user-token/{clean_tg_id}', requires_auth=False)
            
# Global API client instance
api = APIClient()