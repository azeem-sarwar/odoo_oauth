# -*- coding: utf-8 -*-

from odoo import api, SUPERUSER_ID, _
from odoo.http import request, route, Controller, borrow_request
from odoo.exceptions import ValidationError, UserError
from odoo.modules.registry import Registry
from odoo.service.model import execute
from werkzeug.wrappers import Response
from . import make_json_response, handle_error
from .security import authenticate
import json
import math
import threading

def dispatch(db, uid, model, method, *args, **kw):
    """
    Dispatch executable to model service, to delegate handling the call

    ---
    #### Parameters
    db: str
        The name of the database to query, example 'odoo_db'

    uid: int
        The id of the user, example 2

    model: str
        The name of the model to query, example 'res.users'

    method: str
        The function to call on the model, example 'search_read'.
        Note that the function must be annotated with `@api.model` so the executor
        can discover it.

    args: list
        The list of arguments to pass to the method

    kw: dict
        The list of keyword arguments to pass to the method
    ---
    #### Returns
    Any
        the result of the executed method
    """
    if request.db:
        request.env.cr.close()

    with borrow_request():
        threading.current_thread().dbname = db
        threading.current_thread().uid = uid
        registry = Registry(db).check_signaling()
        with registry.manage_changes():
            return execute(db, uid, model, method, *args, **kw)


def validate_model(db, model):
    """
    Validate the existence of the given model in the given database

    ---
    #### Parameters
    db: str
        The name of the database to query, example 'odoo_db'

    model: str
        The name of the model to query, example 'res.users'

    ---
    #### Exceptions
    UserError
        if the model is not found
    """
    with Registry(db).cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {})
        if not env['ir.model'].search([('model', '=', model)], limit=1):
            raise UserError(_("Model '%s' not found") % model)


def validate_fields(db, model, fields):
    """
    Validate the existence of all the fields in the given model from the given database

    ---
    #### Parameters
    db: str
        The name of the database to query, example 'odoo_db'

    model: str
        The name of the model to query, example 'res.users'

    fields: list<str>
        The list of fields to validate

    ---
    #### Exceptions
    ValidationError
        if one or more fields are not found
    """
    with Registry(db).cursor() as cr:
        Model = api.Environment(cr, SUPERUSER_ID, {})[model]
        unknown_fields = [field for field in fields if field not in Model._fields]
        if len(unknown_fields) > 0:
            raise ValidationError(_("The following fields are not found in the model '%s': %s") % (model, ','.join(unknown_fields)))


def validate_domain(db, model, domain):
    """
    Validate the existence of all the fields in the given model from the given database
    and make sure values and comparators are acceptable

    ---
    #### Parameters
    db: str
        The name of the database to query, example 'odoo_db'

    model: str
        The name of the model to query, example 'res.users'

    domain: list<tuple>
        The list of filter domain to validate

    ---
    #### Exceptions
    ValidationError
        if one or more fields are not found
    """
    validator = {}

    validator['integer'] = validator['many2one'] = validator['many2one_reference'] = {
        'comparators': ['=', '!=', '>', '<', '>=', '<=', 'in', 'not in'],
        'converter': lambda value: int(value)
    }

    validator['float'] = validator['monetary'] = {
        'comparators': ['=', '!=', '>', '<', '>=', '<=', 'in', 'not in'],
        'converter': lambda value: float(value)
    }

    validator['many2many'] = validator['one2many'] = {
        'comparators': ['in', 'not in'],
        'converter': lambda value: int(value)
    }

    validator['char'] = validator['selection'] = validator['text'] = {
        'comparators': ['=', '!=', 'in', 'not in', 'ilike', 'not ilike'],
        'converter': lambda value: str(value)
    }

    validator['date'] = validator['datetime'] = {
        'comparators': ['=', '!=', '>', '<', '>=', '<='],
        'converter': lambda value: str(value)
    }

    validator['boolean'] = {
        'comparators': ['='],
        'converter': lambda value: (isinstance(value, bool) and value) or (isinstance(value, int) and value > 0) or (isinstance(value, str) and value.lower() in ['', 'yes', 'true', 'on', '1', 'ok'])
    }

    with Registry(db).cursor() as cr:
        Model = api.Environment(cr, SUPERUSER_ID, {})[model]
        fields = list(set([f for f,c,v in domain]))
        unknown_fields = [field for field in fields if field not in Model._fields]
        if len(unknown_fields) > 0:
            raise ValidationError(_("The following fields are not found in the model '%s': %s") % (model, ','.join(unknown_fields)))

        Fields = Model.fields_get(fields)

        valid_domain = []
        for field, comparator, value in domain:
            Field = Fields[field]
            if Field['type'] not in validator:
                raise ValidationError(_("The field %s (%s) is of type %s which does not support filtering") % (Field['string'] or Field['name'], Field['name'], Field['type']))
            if comparator not in validator[Field['type']]['comparators']:
                raise ValidationError(_("The field %s (%s) is of type %s which does not support the operator '%s'. Only the following operators are supported: '%s'") % (Field['string'] or Field['name'], Field['name'], Field['type'], comparator, "', '".join(validator[Field['type']]['comparators'])))

            try:
                converter = validator[Field['type']]['converter']
                if comparator in ['in', 'not in']:
                    value = [converter(i.strip()) for i in str(value).split(',')]
                else:
                    value = converter(value)
            except:
                raise ValidationError(_("In valid value detected for the field %s (%s): %s") % (Field['string'] or Field['name'], Field['name'], str(value)))

            valid_domain.append((field, comparator, value))

        return valid_domain


class Main(Controller):

    @route('/rest/models/<model>', type='http', auth='none', methods=['GET'], save_session=False, cors="*", csrf=False)
    def browse(self, model, **kwargs):
        """
        Browse the list of records of a given model

        ---
        #### Parameters
        model: str
            The name of the model to query

        kwargs: dict
            Additional query params to customize the request

        ---
        #### Returns
        HttpResponse
            the page for browsing the records.
        """

        try:
            db, uid = authenticate()
            validate_model(db, model)

            fields = kwargs.get('_fields', 'id,display_name').split(',')
            validate_fields(db, model, fields)

            # validate the page
            try:
                page = int(kwargs.get('_page', 1))
                if page <= 0:
                    raise Exception
            except:
                raise ValidationError(_('Page must be a valid strictly positive integer'))

            # validate the size
            try:
                size = int(kwargs.get('_size', 80))
                if size <= 0:
                    raise Exception
            except:
                raise ValidationError(_('Size must be a valid strictly positive integer'))

            # validate the order
            try:
                order = kwargs.get('_order', 'id desc').split(',')
                sort_fields = []
                sort_errors = []
                sort_container = []
                for o in order:
                    s = o.split()
                    if len(s) != 2:
                        sort_errors.append(_("Missing order rule for field '%s'. Please specify wether it's 'desc' or 'asc'") % s)
                    sort_fields.append(s[0])
                    if len(s) == 2:
                        sort_container.append(s[0] + ' ' + s[1].lower())

                try:
                    validate_fields(db, model, sort_fields)
                except ValidationError as e:
                    sort_errors.append(str(e))

                if len(sort_errors) > 0:
                    raise Exception('\n'.join(['- ' + error for error in sort_errors]))
                
                order = ','.join(sort_container)
            except Exception as e:
                raise ValidationError(_("Order must be a valid sorting string, example 'name asc, id desc'\nThe following errors were found:\n\n") + str(e))

            offset = ((page - 1) * size)
            domain = []

            # Compute filtering domain
            keys = list(kwargs.keys() - ['_fields', '_page', '_size', '_order'])
            for key in keys:
                value = kwargs.get(key)
                if key.endswith(('_ne', '_gt', '_lt', '_gte', '_lte', '_in', '_nin', '_like', '_nlike')):
                    parts = key.split('_')
                    comparator = {
                        'ne': '!=', 
                        'gt': '>', 
                        'lt': '<', 
                        'gte': '>=', 
                        'lte': '<=', 
                        'in': 'in', 
                        'nin': 'not in', 
                        'like': 'ilike', 
                        'nlike': 'not ilike'
                    }.get(parts.pop())
                    field = '_'.join(parts)
                else:
                    comparator = '='
                    field = key
                
                domain.append((field, comparator, value))
            
            domain = validate_domain(db, model, domain)

            # Count total elements
            count = dispatch(db, uid, model, 'search_count', domain=domain)

            # compute the total number of pages
            totalPages = math.ceil(max(count, 1) / size)

            if page > totalPages:
                raise ValidationError(_("Page %d does not exist") % page)

            if count == 0:
                return make_json_response({
                    "content": [],
                    "totalElements": 0,
                    "totalPages": 0,
                    "last": True,
                    "first": True,
                    "numberOfElements": 0,
                    "size": size,
                    "number": page,
                    "sort": order,
                    "empty": True
                }, status=200)

            # Fetch actual data
            res = dispatch(db, uid, model, 'search_read' , domain=domain, fields=fields, offset=offset, limit=size, order=order)

            return make_json_response({
                "content": res,
                "totalElements": count,
                "totalPages": totalPages,
                "last": page == totalPages,
                "first": page == 1,
                "numberOfElements": len(res),
                "size": size,
                "number": page,
                "sort": order,
                "empty": False
            }, status=200)

        except Exception as e:
            return handle_error(e, model)


    @route('/rest/models/<model>/<int:id>', type='http', auth='none', methods=['GET'], save_session=False, cors="*", csrf=False)
    def read(self, model, id, **kwargs):
        """
        Read a specific record from a given model

        ---
        #### Parameters
        model: str
            The name of the model to query

        id: int
            The id of the record to read

        kwargs: dict
            Additional query params to customize the request

        ---
        #### Returns
        HttpResponse
            the data of record if found.
        """

        try:
            db, uid = authenticate()
            validate_model(db, model)

            fields = kwargs.get('fields')
            if fields:
                fields = fields.split(',')
                validate_fields(db, model, fields)
            else:
                fields = None

            res = dispatch(db, uid, model, 'search_read', domain=[('id', '=', id)], fields=fields, limit=1)

            if not res:
                raise UserError(_("Record with id '%d' not found under the model '%s'") % (id, model))

            return make_json_response(res[0], status=200)

        except Exception as e:
            return handle_error(e, model)


    @route('/rest/models/<model>/<int:id>', type='http', auth='none', methods=['PATCH'], save_session=False, cors="*", csrf=False)
    def edit(self, model, id):
        """
        Update a specific record from a given model

        ---
        #### Parameters
        model: str
            The name of the model to query

        id: int
            The id of the record to read

        ---
        #### Returns
        HttpResponse
            the data of record if found.
        """
        data = request.httprequest.json

        try:
            db, uid = authenticate()
            validate_model(db, model)

            res = dispatch(db, uid, model, 'write', [id], data)

            if not res:
                raise UserError(_("Record with id '%d' not found under the model '%s'") % (id, model))

            return make_json_response({'message': 'OK'}, status=200)

        except Exception as e:
            return handle_error(e, model)


    @route('/rest/models/<model>', type='http', auth='none', methods=['POST'], save_session=False, cors="*", csrf=False)
    def add(self, model):
        """
        Create a new record of a given model

        ---
        #### Parameters
        model: str
            The name of the model to query

        ---
        #### Returns
        HttpResponse
            Ok if record created.
        """
        data = request.httprequest.json

        try:
            db, uid = authenticate()
            validate_model(db, model)

            try:
                res = dispatch(db, uid, model, 'create', [data])[0]
            except UserError as e:
                raise ValidationError(e)

            return Response(json.dumps({'message': 'OK', 'id': res}), status=201, content_type='application/json', headers={'Location': f'/rest/models/{model}/{res}'})

        except Exception as e:
            return handle_error(e, model)


    @route('/rest/models/<model>/<int:id>', type='http', auth='none', methods=['DELETE'], save_session=False, cors="*", csrf=False)
    def delete(self, model, id):
        """
        Delete a specific record from a given model

        ---
        #### Parameters
        model: str
            The name of the model to query

        id: int
            The id of the record to delete

        ---
        #### Returns
        HttpResponse
            Ok if record deleted.
        """

        try:
            db, uid = authenticate()
            validate_model(db, model)

            dispatch(db, uid, model, 'unlink', [id])

            return make_json_response({'message': 'OK'}, status=200)
        except Exception as e:
            return handle_error(e, model)
