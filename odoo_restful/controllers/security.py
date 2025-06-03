# -*- coding: utf-8 -*-

from odoo import api, _, SUPERUSER_ID
from odoo.http import request, route, Controller, borrow_request
from odoo.exceptions import AccessDenied
from odoo.modules.registry import Registry
from odoo.tools import config
from . import make_json_response
from datetime import datetime, timedelta, timezone
import threading
import jwt


def validate_jwt(token):
    """
    Validate a JWT token and extract its payload

    ---
    #### Parameters
    token: str
        The token string to validate

    ---
    #### Returns
    dict
        the payload of the token.

    ---
    #### Exceptions
    AccessDenied
        If the token validation fails
    """
    try:
        # Decode the JWT and validate its signature
        # If no exception was raised, the token is valid
        return jwt.decode(token, config.get('jwt_secret_key'), algorithms=["HS256"])

    except jwt.ExpiredSignatureError:
        raise AccessDenied(_('The token has expired'))
    except:
        raise AccessDenied(_('Invalid token'))


def authenticate():
    """
    Authenticate the user using the Authorization header from the current request

    ---
    #### Parameters
    none

    ---
    #### Returns
    tuple (db, uid)

    - db <str>: The database name to use
    - uid <int>: The user id

    ---
    #### Exceptions
    AccessDenied
        If the token validation fails
    """
    auth = request.httprequest.headers.get('Authorization', '')

    if not auth or not auth.startswith('Bearer '):
        raise AccessDenied
    
    auth = auth[7:]

    try:
        token = validate_jwt(auth)
        uid = int(token.get('sub'))
        db = token.get('db')
    except:
        raise AccessDenied
    
    return db, uid



class Security(Controller):

    @route('/rest/auth', type='http', auth='none', methods=['POST'], save_session=False, cors="*", csrf=False)
    def get_token(self):
        """
        Generate a JWT token to access Odoo RESTful APIs

        ---
        #### Parameters
        none

        ---
        #### Returns
        HttpResponse
            the page for browsing the records.
        """
        data = request.httprequest.json

        if request.db:
            request.env.cr.close()

        with borrow_request():
            threading.current_thread().uid = None
            threading.current_thread().dbname = None

            # make sure the database exists
            if 'database' not in data:
                raise AccessDenied(_("Invalid request. Missing database"))
            database = data.get('database')
            try:
                threading.current_thread().dbname = database
                Registry(database).check_signaling()
            except:
                raise AccessDenied(_("Invalid request. Missing database"))
            
            with Registry(database).cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {})

                try:
                    user = self.login_user(env, data)
                except AccessDenied as e:
                    return make_json_response({'error': str(e)}, status=400)

                return make_json_response({'token': self.generate_token(env, user)}, status=200)


    def generate_token(self, env, user):
        """
        Generate a JWT token from the user info

        ---
        #### Parameters
        env: Any
            The current environment to access models on database

        user: dict
            The signed user data

        ---
        #### Returns
        str
            The generated jwt token
        """

        # Create a payload
        payload = {
            'sub': str(user.id),
            'name': user.name,
            'db': env.cr.dbname,
            'iat': datetime.now(timezone.utc),  # Issued at
            'exp': datetime.now(timezone.utc) + timedelta(hours=1),  # Expiration time
            # TODO add custom payload from params
        }

        # Allow custom update for the token payload
        payload.update(self.update_token_payload(env, payload, user))

        # Encode the payload to create a JWT
        return jwt.encode(payload, config.get('jwt_secret_key'), algorithm='HS256')


    def update_token_payload(self, env, payload, user):
        """
        This method is meant to be overridden to allow extension
        and the implementation of custom JWT payloads.

        ---
        #### Parameters
        env: Any
            The current environment to access models on database

        payload: dict
            The initial JWT payload

        user: record <res.users>
            The signed user

        ---
        #### Returns
        dict
            The updated JWT payload
        """

        # add custom inputs for oauth users
        auth_oauth = env['ir.module.module'].search([('name', '=', 'auth_oauth')])

        if not auth_oauth or auth_oauth.state != 'installed':
            return payload

        if user.oauth_provider_id and user.oauth_uid:
            payload.update({
                'uid': user.oauth_uid,
                'provider': user.oauth_provider_id.id
            })
        
        return payload


    def login_user(self, env, credentials:dict):
        """
        Login and get user info using the credentials

        ---
        #### Parameters
        env: Any
            The current environment to access models on database

        credentials: dict
            The credentials used to login users

        ---
        #### Returns
        record <res.users>
            The logged-in user record

        ---
        #### Exceptions
        AccessDenied
            If the login fails
        """

        if not credentials:
            raise AccessDenied(_('Invalid request'))

        # extract login method
        method = credentials.get('method')

        # make sure the method is supported
        if method not in self.get_login_methods():
            raise AccessDenied(_("Method '%s' not allowed") % method)

        # get the executor function name
        executor = f'_login_using_{method}'
        if not hasattr(self, executor):
            raise AccessDenied(_("Method '%s' not allowed") % method)

        # login user
        user = getattr(self, executor)(env, credentials)

        # update current thread user id
        threading.current_thread().uid = user.id

        # update the user last login
        user = user.with_user(user)
        user._update_last_login()
    
        return user


    def get_login_methods(self):
        """
        This method is meant to be overridden to allow extension
        and the implementation of custom methods.

        Methods will be handled by function named `_login_using_<METHOD_NAME>`
        #### example: 
        | Method | function to execute |
        | --- | --- |
        | `credentials` | `_login_using_credentials` |
        | `token` | `_login_using_token` |
        | `oauth` | `_login_using_oauth` |

        ---
        #### Parameters
        none

        ---
        #### Returns
        list<str>
            The list of allowed methods
        """

        return ['credentials', 'token', 'oauth']


    def _login_using_credentials(self, env, credentials:dict):
        """
        Login user using username and password

        ---
        #### Parameters
        env: Any
            The current environment to access models on database

        credentials: dict
            The credentials used to login users, containing username, password and database

        ---
        #### Returns
        record <res.users>
            The logged-in user record

        ---
        #### Exceptions
        AccessDenied
            If the login fails
        """

        if 'username' not in credentials or 'password' not in credentials:
            raise AccessDenied(_("Invalid request. Missing data for method 'credentials', please provide a 'username' and a 'password'"))

        username = credentials.get('username')
        password = credentials.get('password')

        with env['res.users']._assert_can_auth(user=username):
            user = env['res.users'].search(env['res.users']._get_login_domain(username), order=env['res.users']._get_login_order(), limit=1)
            if not user:
                raise AccessDenied()

            user = user.with_user(user)
            user._check_credentials(password, {'interactive': False})

        return user


    def _login_using_token(self, env, credentials:dict):
        """
        Login user using Json Web Token or, in other words, regenerate token 

        ---
        #### Parameters
        env: Any
            The current environment to access models on database

        credentials: dict
            The credentials used to login users, containing token

        ---
        #### Returns
        record <res.users>
            The logged-in user record

        ---
        #### Exceptions
        AccessDenied
            If the login fails
        """

        if 'token' not in credentials:
            raise AccessDenied(_("Invalid request. Missing data for method 'token', please provide a valid 'token'"))

        token = credentials.get('token')
        payload = validate_jwt(token)

        try:
            user = env['res.users'].search([('id', '=', int(payload.get('sub')))], limit=1)
            if not user:
                raise AccessDenied
        except:
            raise AccessDenied(_('Invalid token'))

        return user


    def _login_using_oauth(self, env, credentials:dict):
        """
        Login user using a token for an OAuth Identity Provider

        ---
        #### Parameters
        env: Any
            The current environment to access models on database

        credentials: dict
            The credentials used to login users, containing token

        ---
        #### Returns
        record <res.users>
            The logged-in user record

        ---
        #### Exceptions
        AccessDenied
            If the login fails
        """

        # Make sure the oauth module is installed
        auth_oauth = env['ir.module.module'].search([('name', '=', 'auth_oauth')])

        if not auth_oauth or auth_oauth.state != 'installed':
            raise AccessDenied(_("Method '%s' not allowed") % 'oauth')

        # Make sure the required request's payload exist
        if 'token' not in credentials or 'provider' not in credentials:
            raise AccessDenied(_("Invalid request. Missing data for method 'token', please provide a valid 'provider' and a 'token'"))

        # Validate the oauth provider
        try:
            provider = env['auth.oauth.provider'].search([('id', '=', int(credentials.get('provider')))], limit=1).id
        except:
            raise AccessDenied(_('Invalid provider'))

        token = credentials.get('token')

        try:
            oauth_uid = env['res.users']._auth_oauth_validate(provider, token)['user_id']
            oauth_user = env['res.users'].search([("oauth_uid", "=", oauth_uid), ('oauth_provider_id', '=', provider)])
            if not oauth_user:
                raise AccessDenied()
            assert len(oauth_user) == 1
            oauth_user.write({'oauth_access_token': token})
            return oauth_user
        except:
            raise AccessDenied(_('Invalid token'))
