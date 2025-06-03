from odoo import _
from odoo.tools import json_default
from odoo.exceptions import AccessDenied, ValidationError, UserError, AccessError
from werkzeug.wrappers import Response
import json
import logging

_logger = logging.getLogger(__name__)

def make_json_response(data, status):
    return Response(json.dumps(data, ensure_ascii=False, default=json_default), status=status, content_type='application/json')

def handle_error(e, model):
    if isinstance(e, ValidationError) or isinstance(e, ValueError) or isinstance(e, TypeError):
        return make_json_response({'error': str(e)}, status=400)
    if isinstance(e, UserError):
        return make_json_response({'error': str(e)}, status=404)
    if isinstance(e, AccessError):
        return make_json_response({'error': _("You are not allowed to access the model '%s' and/or one or more of its relationships") % model}, status=403)
    if isinstance(e, AccessDenied):
        return make_json_response({'error': _('Access Denied')}, status=401)
    
    _logger.error(e)
    return make_json_response({'error': str(e)}, status=500)