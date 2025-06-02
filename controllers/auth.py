from odoo import http
from odoo.http import request
import json
import logging

_logger = logging.getLogger(__name__)

class OAuthController(http.Controller):
    @http.route('/api/auth/token', type='http', auth='none', methods=['POST'], csrf=False)
    def generate_token(self, **kwargs):
        try:
            data = json.loads(request.httprequest.data)
            username = data.get('username')
            password = data.get('password')

            if not username or not password:
                return json.dumps({
                    'error': 'Missing username or password'
                }), 400

            uid = request.session.authenticate(request.session.db, username, password)
            if not uid:
                return json.dumps({
                    'error': 'Invalid credentials'
                }), 401

            user = request.env['res.users'].sudo().browse(uid)
            token = request.env['oauth.token'].sudo().generate_tokens(user.id)

            return json.dumps({
                'access_token': token.access_token,
                'refresh_token': token.refresh_token,
                'expires_in': request.env['oauth.config'].sudo().search([], limit=1).access_token_expiry_minutes * 60
            })

        except Exception as e:
            _logger.error("Token generation error: %s", str(e))
            return json.dumps({
                'error': 'Internal server error'
            }), 500

    @http.route('/api/auth/refresh', type='http', auth='none', methods=['POST'], csrf=False)
    def refresh_token(self, **kwargs):
        try:
            data = json.loads(request.httprequest.data)
            refresh_token = data.get('refresh_token')

            if not refresh_token:
                return json.dumps({
                    'error': 'Missing refresh token'
                }), 400

            token = request.env['oauth.token'].sudo().refresh_access_token(refresh_token)
            if not token:
                return json.dumps({
                    'error': 'Invalid or expired refresh token'
                }), 401

            return json.dumps({
                'access_token': token.access_token,
                'expires_in': request.env['oauth.config'].sudo().search([], limit=1).access_token_expiry_minutes * 60
            })

        except Exception as e:
            _logger.error("Token refresh error: %s", str(e))
            return json.dumps({
                'error': 'Internal server error'
            }), 500

    @http.route('/api/auth/revoke', type='http', auth='none', methods=['POST'], csrf=False)
    def revoke_token(self, **kwargs):
        try:
            auth_header = request.httprequest.headers.get('Authorization')
            if not auth_header or not auth_header.startswith('Bearer '):
                return json.dumps({
                    'error': 'Missing or invalid authorization header'
                }), 401

            access_token = auth_header.split(' ')[1]
            if request.env['oauth.token'].sudo().revoke_token(access_token):
                return json.dumps({
                    'message': 'Token revoked successfully'
                })
            return json.dumps({
                'error': 'Invalid token'
            }), 401

        except Exception as e:
            _logger.error("Token revocation error: %s", str(e))
            return json.dumps({
                'error': 'Internal server error'
            }), 500 