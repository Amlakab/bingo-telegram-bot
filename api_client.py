import requests
import json
from config import config
import logging

logger = logging.getLogger(__name__)

class APIClient:
    def __init__(self):
        self.base_url = config.API_URL
        # ❌ REMOVED: self.token = None (shared state)
        # ❌ REMOVED: self.session = requests.Session() (shared state)
    
    def _make_request(self, method, endpoint, data=None, params=None, token=None):
        """
        Make API request to backend
        ✅ token passed explicitly - NO shared state
        """
        url = f"{self.base_url}{endpoint}"
        
        headers = {'Content-Type': 'application/json'}
        
        if token:
            headers['Authorization'] = f'Bearer {token}'
            logger.info(f"🔑 Making authenticated request")
        else:
            logger.info(f"📡 Making public request")
        
        try:
            # ✅ Each request uses its own session (no shared state)
            response = requests.request(
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
    
    def get_user_profile(self, token):
        """Get current user profile (requires auth) - ✅ token passed explicitly"""
        return self._make_request('GET', '/auth/profile', token=token)
    
    def get_user(self, user_id, token):
        """Get user by ID (requires auth) - ✅ token passed explicitly"""
        return self._make_request('GET', f'/user/{user_id}', token=token)
    
    def change_password(self, current_password, new_password, token):
        """Change user password (requires auth) - ✅ token passed explicitly"""
        data = {
            'currentPassword': current_password,
            'newPassword': new_password
        }
        return self._make_request('POST', '/auth/change-password', data, token=token)
    
    # ============ Wallet Endpoints ============
    
    def get_wallet(self, token):
        """Get current user's wallet (requires auth) - ✅ token passed explicitly"""
        return self._make_request('GET', '/wallet', token=token)
    
    def get_wallet_balance(self, user_id, token):
        """Get user's wallet balance (requires auth) - ✅ token passed explicitly"""
        return self._make_request('GET', f'/wallet/{user_id}', token=token)
    
    def create_transaction(self, data, token):
        """Create a new transaction (deposit/withdrawal) (requires auth) - ✅ token passed explicitly"""
        return self._make_request('POST', '/transactions', data, token=token)
    
    def get_transactions(self, user_id, token, limit=20, page=1):
        """Get user's transaction history (requires auth) - ✅ token passed explicitly"""
        params = {'limit': limit, 'page': page}
        return self._make_request('GET', f'/transactions/user/{user_id}', params=params, token=token)
    
    def get_transaction(self, transaction_id, token):
        """Get specific transaction details (requires auth) - ✅ token passed explicitly"""
        return self._make_request('GET', f'/transactions/{transaction_id}', token=token)
    
    # ============ Accountant Endpoints ============
    
    def get_accountants(self, token, blocked=False):
        """Get active accountants - ✅ token passed explicitly"""
        params = {'blocked': str(blocked).lower()}
        return self._make_request('GET', '/accountants', params=params, token=token)
    
    def generate_game_code(self, user_id, token):
        """Generate a one-time code for the game link - ✅ token passed explicitly"""
        data = {'userId': user_id}
        return self._make_request('POST', '/auth/generate-game-code', data, token=token)

    def exchange_game_code(self, code):
        """Exchange a game code for a JWT token"""
        data = {'code': code}
        return self._make_request('POST', '/auth/exchange-game-code', data)
    
    def refresh_token(self, token):
        """Refresh the current token using the refresh endpoint - ✅ token passed explicitly"""
        if not token:
            return {'success': False, 'message': 'No token to refresh'}
        
        headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {token}'}
        
        try:
            response = requests.post(
                f"{self.base_url}/auth/refresh-token",
                headers=headers,
                timeout=60
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    new_token = result.get('data', {}).get('token')
                    if new_token:
                        return {'success': True, 'token': new_token, 'data': result.get('data')}
            
            return {'success': False, 'message': 'Refresh failed'}
        except Exception as e:
            logger.error(f"❌ Refresh token error: {e}")
            return {'success': False, 'message': str(e)}
    
    def check_user_by_telegram_id(self, tg_id):
        """Check if a user exists in the database by Telegram ID"""
        clean_tg_id = tg_id.replace('@', '').strip()
        return self._make_request('GET', f'/auth/check-user/{clean_tg_id}')
    
    def check_user_and_token(self, tg_id, token=None):
        """Single API call that checks user and token in one go - ✅ token passed explicitly"""
        clean_tg_id = tg_id.replace('@', '').strip()
        return self._make_request('GET', f'/auth/check-user-token/{clean_tg_id}', token=token)


# ✅ NO global state - api instance is stateless
# Each method now requires token to be passed explicitly

# ❌ REMOVED: api = APIClient() - No global instance