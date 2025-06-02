from odoo import models, fields, api
from datetime import datetime, timedelta
import secrets
import logging

_logger = logging.getLogger(__name__)

class OAuthToken(models.Model):
    _name = 'oauth.token'
    _description = 'OAuth Token'
    _order = 'create_date desc'

    user_id = fields.Many2one('res.users', string='User', required=True, ondelete='cascade')
    access_token = fields.Char(string='Access Token', required=True, index=True)
    refresh_token = fields.Char(string='Refresh Token', required=True, index=True)
    access_token_expiry = fields.Datetime(string='Access Token Expiry', required=True)
    refresh_token_expiry = fields.Datetime(string='Refresh Token Expiry', required=True)
    is_revoked = fields.Boolean(string='Is Revoked', default=False)
    last_used = fields.Datetime(string='Last Used', default=fields.Datetime.now)

    @api.model
    def generate_tokens(self, user_id):
        """Generate new access and refresh tokens for a user."""
        config = self.env['oauth.config'].sudo().search([], limit=1)
        if not config:
            config = self.env['oauth.config'].sudo().create({
                'access_token_expiry_minutes': 60,
                'refresh_token_expiry_days': 30,
            })

        access_token = secrets.token_urlsafe(32)
        refresh_token = secrets.token_urlsafe(32)
        
        now = datetime.now()
        access_token_expiry = now + timedelta(minutes=config.access_token_expiry_minutes)
        refresh_token_expiry = now + timedelta(days=config.refresh_token_expiry_days)

        token = self.create({
            'user_id': user_id,
            'access_token': access_token,
            'refresh_token': refresh_token,
            'access_token_expiry': access_token_expiry,
            'refresh_token_expiry': refresh_token_expiry,
        })

        return token

    @api.model
    def validate_access_token(self, access_token):
        """Validate an access token and return the associated user if valid."""
        token = self.search([
            ('access_token', '=', access_token),
            ('is_revoked', '=', False),
            ('access_token_expiry', '>', fields.Datetime.now())
        ], limit=1)

        if token:
            token.write({'last_used': fields.Datetime.now()})
            return token.user_id
        return False

    @api.model
    def refresh_access_token(self, refresh_token):
        """Generate a new access token using a valid refresh token."""
        token = self.search([
            ('refresh_token', '=', refresh_token),
            ('is_revoked', '=', False),
            ('refresh_token_expiry', '>', fields.Datetime.now())
        ], limit=1)

        if token:
            config = self.env['oauth.config'].sudo().search([], limit=1)
            if not config:
                config = self.env['oauth.config'].sudo().create({
                    'access_token_expiry_minutes': 60,
                    'refresh_token_expiry_days': 30,
                })

            new_access_token = secrets.token_urlsafe(32)
            access_token_expiry = datetime.now() + timedelta(minutes=config.access_token_expiry_minutes)

            token.write({
                'access_token': new_access_token,
                'access_token_expiry': access_token_expiry,
                'last_used': fields.Datetime.now()
            })

            return token
        return False

    @api.model
    def revoke_token(self, access_token):
        """Revoke an access token."""
        token = self.search([('access_token', '=', access_token)], limit=1)
        if token:
            token.write({'is_revoked': True})
            return True
        return False 