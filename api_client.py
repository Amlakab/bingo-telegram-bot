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
            # Remove authorization header if token is None
            self.session.headers.pop('Authorization', None)
    
    def _make_request(self, method, endpoint, data=None, params=None, requires_auth=False):
        """Make API request to backend"""
        url = f"{self.base_url}{endpoint}"
        
        # Create headers
        headers = {'Content-Type': 'application/json'}
        
        # Add authorization if required and token exists
        if requires_auth and self.token:
            headers['Authorization'] = f'Bearer {self.token}'
            logger.info(f"🔑 Making authenticated request to {endpoint}")
        else:
            logger.info(f"📡 Making public request to {endpoint}")
        
        try:
            response = self.session.request(
                method=method,
                url=url,
                json=data,
                params=params,
                headers=headers,
                timeout=60
            )
            
            # Log response status
            logger.info(f"📊 Response status: {response.status_code}")
            
            # Try to parse JSON response
            try:
                result = response.json()
            except:
                return {'success': False, 'message': 'Invalid response from server'}
            
            # Check if response indicates success
            if response.status_code >= 200 and response.status_code < 300:
                return {'success': True, 'data': result.get('data'), 'message': result.get('message', 'Success')}
            else:
                return {'success': False, 'message': result.get('message', 'Request failed')}
                
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
    
    # api_client.py - Add this method

    def generate_game_code(self, user_id):
        """Generate a one-time code for the game link"""
        data = {'userId': user_id}
        return self._make_request('POST', '/auth/generate-game-code', data, requires_auth=True)

    def exchange_game_code(self, code):
        """Exchange a game code for a JWT token"""
        data = {'code': code}
        return self._make_request('POST', '/auth/exchange-game-code', data)
# Global API client instance
api = APIClient()