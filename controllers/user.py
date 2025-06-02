from odoo import http
from odoo.http import request
import json
import logging

_logger = logging.getLogger(__name__)

class UserController(http.Controller):
    @http.route('/api/user/data', type='http', auth='none', methods=['GET'], csrf=False)
    def get_user_data(self, **kwargs):
        try:
            auth_header = request.httprequest.headers.get('Authorization')
            if not auth_header or not auth_header.startswith('Bearer '):
                return json.dumps({
                    'error': 'Missing or invalid authorization header'
                }), 401

            access_token = auth_header.split(' ')[1]
            user = request.env['oauth.token'].sudo().validate_access_token(access_token)
            
            if not user:
                return json.dumps({
                    'error': 'Invalid or expired token'
                }), 401

            # Example of protected user data
            user_data = {
                'id': user.id,
                'name': user.name,
                'login': user.login,
                'email': user.email,
                'company_id': user.company_id.id,
                'company_name': user.company_id.name,
            }

            return json.dumps(user_data)

        except Exception as e:
            _logger.error("User data retrieval error: %s", str(e))
            return json.dumps({
                'error': 'Internal server error'
            }), 500 