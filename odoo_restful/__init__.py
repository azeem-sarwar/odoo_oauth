import sys
import random
from odoo.tools import config
from odoo.exceptions import UserError

# Check each library
missing_library = False
try:
    __import__('jwt')
except ImportError:
    missing_library = True

# If any libraries are missing, raise an error to halt installation
if missing_library:
    raise UserError(
        f"The following Python library is required but not installed: jwt. "
        f"Please install it before installing this module. "
        f"You can use `pip install pyjwt`"
    )

# Verify the security key is configured
if not config.get('jwt_secret_key'):
    raise UserError(
        f"The following configuration parameter is required but not present: 'jwt_secret_key'. "
        f"Please add the secret to the config by appending the odoo.conf file or any other way.\n"
        f"We recommend using a 128 bytes alphanumeric string like the following:\n"
        f"{''.join(random.choices([chr(i) for i in range(65, 91)] + [chr(i) for i in range(48, 58)], k=128))}"
    )


from . import controllers