from odoo import models, fields

class OAuthConfig(models.Model):
    _name = 'oauth.config'
    _description = 'OAuth Configuration'

    access_token_expiry_minutes = fields.Integer(
        string='Access Token Expiry (minutes)',
        default=60,
        help='Number of minutes until access token expires'
    )
    refresh_token_expiry_days = fields.Integer(
        string='Refresh Token Expiry (days)',
        default=30,
        help='Number of days until refresh token expires'
    ) 