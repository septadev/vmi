# -*- encoding: utf-8 -*-

import random
import string
import operator
import os.path
import cStringIO
import xmlrpclib
import simplejson
import base64
import logging
from types import *
from simpletal import simpleTAL, simpleTALES
import werkzeug.utils
import werkzeug.wrappers
import openerp
from openerp.tools.translate import _
import openerp.addons.web.http as vmiweb

_logger = logging.getLogger(__name__)

# -----------------------------------------------| VMI Global Methods.


def fields_get(req, model):
    Model = req.session.model(model)
    fields = Model.fields_get(False, req.context)
    #_logger.debug('fields: %s', fields)
    return fields

#				 (req, 'dbe.vendor', ['id', 'company'], 0, False, [('vuid', '=', uid)], None)
def do_search_read(req, model, fields=False, offset=0, limit=False, domain=None, sort=None):
    """ Performs a search() followed by a read() (if needed) using the
provided search criteria

:param req: a JSON-RPC request object
:type req: vmiweb.JsonRequest
:param str model: the name of the model to search on
:param fields: a list of the fields to return in the result records
:type fields: [str]
:param int offset: from which index should the results start being returned
:param int limit: the maximum number of records to return
:param list domain: the search domain for the query
:param list sort: sorting directives
:returns: A structure (dict) with two keys: ids (all the ids matching
                    the (domain, context) pair) and records (paginated records
                    matching fields selection set)
:rtype: list
"""
    Model = req.session.model(model)

    ids = Model.search(domain, offset or 0, limit or False, sort or False,
                       req.context)
    if limit and len(ids) == limit:
        length = Model.search_count(domain, req.context)
    else:
        length = len(ids) + (offset or 0)
    if fields and fields == ['id']:
        # shortcut read if we only want the ids
        return {
            'length': length,
            'records': [{'id': id} for id in ids]
        }

    records = Model.read(ids, fields or False, req.context)
    records.sort(key=lambda obj: ids.index(obj['id']))
    return {
        'length': length,
        'records': records
    }


def newSession(req):
    """ create admin session for testing purposes only """
    db = 'dev_main'
    login = 'admin'
    password = 'openerp'
    uid = req.session.authenticate(db, login, password)
    return uid


def check_partner_parent(pid):
    res = None
    parent_id = None
    try:
        res = do_search_read(req, 'res.partner', ['active', 'parent_id'], 0, False, [('id', '=', pid)], None)
    except Exception:
        _logger.debug('Session expired or Partner not found for partner ID: %s', pid)

    if res:
        record = res['records'][0]
        if record['parent_id'] and record['active']:
            parent_id = record['parent_id']
        else:
            raise Exception("AccessDenied")
    else:
        return False

    return parent_id


def get_partner(req, pid):
    partner = None
    fields = fields_get(req, 'res.partner')
    try:
        partner = do_search_read(req, 'res.partner', fields, 0, False, [('id', '=', pid)], None)
    except Exception:
        _logger.debug('Partner not found for ID: %s', pid)

    if not partner:
        raise Exception("AccessDenied")

    return partner


def get_vendor_by_name(req, name):
    """
    Find the partner record for the supplied vendor name.
    @param req: object
    @param name: string
    @return: partner record
    """
    partner = None
    fields = fields_get(req, 'res.partner')
    try:
        partner = do_search_read(req, 'res.partner', fields, 0, False, [('name', '=', name), ('supplier', '=', True)], None)
    except Exception:
        _logger.debug('Partner not found for ID: %s', name)

    if not partner:
        raise Exception("AccessDenied")

    return partner

def get_vendor_id(req, uid=None, **kwargs):
    """ Find the vendor associated to the current logged-in user """
    vendor_ids = None
    try:
        vendor_ids = do_search_read(req, 'dbe.vendor', ['id', 'company'], 0, False, [('vuid.id', '=', uid)], None)
    except Exception:
        _logger.debug('Session expired or Vendor not found for user ID: %s', uid)

    if not vendor_ids:
        raise Exception("AccessDenied")

    _logger.debug('Vendor ID: %s',
                  vendor_ids) #{'records': [{'company': u'Gomez Electrical Supply', 'id': 3}], 'length': 1}
    return vendor_ids


def get_partner_id(req, uid=None, **kwargs):
    """ Find the partner associated to the current logged-in user """
    partner_ids = None
    try:
        partner_ids = do_search_read(req, 'res.users', ['partner_id'], 0, False, [('id', '=', uid)], None)
    except Exception:
        _logger.debug('Session expired or Partner not found for user ID: %s', uid)

    if not partner_ids:
        raise Exception("AccessDenied")

    record = partner_ids['records'][0]
    pid = record['partner_id'][0]
    parent_id = check_partner_parent(pid)
    if parent_id:
        p = get_partner(parent_id)
        parent = p['records'][0]
        record['company'] = parent['name']
        record['company_id'] = parent['id']
        partner_ids['records'].append(record)
        partner_ids.pop(0)

    _logger.debug('Partner ID: %s',
                  partner_ids) #{'records': [{'groups_id': [3, 9, 19, 20, 24, 27], 'partner_id': (20, u'Partner'), 'id': 13, 'name': u'Partner'}], 'length': 1}
    return partner_ids


def get_stock_locations(req, pid, **kwargs):
    """

    @param req: object
    @param pid: partner ID
    @param kwargs:
    @return: search result of all stock.location instances
    """
    stock_locations = None
    fields = ['name', 'id', 'location_id', 'partner_id']
    try:
        stock_locations = do_search_read(req, 'stock.location', fields, 0, False, [], None)
    except Exception:
        _logger.debug('stock locations not found for partner ID: %s', pid)

    if not stock_locations:
        raise Exception("AccessDenied")
    _logger.debug('stock locations: %s', str(stock_locations['records']))
    return stock_locations

def get_stock_location_by_id(req, ids, all=False):
    """

    @param req: object
    @param ids: location_ids
    @param kwargs:
    @return: search result of specified stock.location instances
    """
    stock_locations = None
    fields = ['name', 'id', 'location_id', 'partner_id']
    if all:
        fields = fields_get(req, 'stock.location')

    try:
        stock_locations = do_search_read(req, 'stock.location', fields, 0, False, [('id', 'in', ids)], None)
    except Exception:
        _logger.debug('stock locations not found for ids: %s', ids)

    if not stock_locations:
        raise Exception("AccessDenied")
    #_logger.debug('stock locations: %s', str(stock_locations['records']))
    return stock_locations


def get_uom_by_id(req, ids):
    """
    Search for Units of Measure by specific ids.
    @param req: object
    @param ids: product.uom ids
    @return: search result of product.uom record(s).
    """
    units = None
    fields = fields_get(req, 'product.uom')
    try:
        units = do_search_read(req, 'product.uom', fields, 0, False, [('id', 'in', ids)], None)
    except Exception:
        _logger.debug('product uoms not found for ids: %s', ids)

    if not units:
        raise Exception("AccessDenied")

    return units

def get_product_by_id(req, ids, all=False):
    """
    Search for products with specific ids.
    @param req: object
    @param ids: location_ids
    @param all: selects all fields in result
    @return: search result of specified product.product record(s).
    """
    products = None
    fields = ['name', 'id', 'default_code', 'vendor_part_number', 'description', 'categ_id', 'seller_ids']
    if all:
        fields = fields_get(req, 'product.product')

    try:
        products = do_search_read(req, 'product.product', fields, 0, False, [('id', 'in', ids)], None)
    except Exception:
        _logger.debug('products not found for ids: %s', ids)

    if not products:
        raise Exception("AccessDenied")
    #_logger.debug('products: %s', str(products['records']))
    return products

def get_client_page(req, page):
    """
    Search for vmi.client.page instances for client page.

    @param req: object
    @param page: string
    @return: dict
    """
    client = None
    fields = fields_get(req, 'vmi.client.page')
    try:
        client = do_search_read(req, 'vmi.client.page', fields, 0, False, [('name', '=', page)], None)
    except Exception:
        _logger.debug('VMI Page not found for ID: %s', page)

    if not client:
        raise Exception("AccessDenied")

    return client


def get_stock_moves_by_id(req, ids, all=False):
    """
    search stock.moves with specific ids.
    @param req: object
    @param ids: stock.move ids
    @param all: selects all fields in result
    """
    moves = None
    fields = ['id', 'origin', 'create_date', 'product_id', 'product_qty', 'product_uom', 'location_dest_id', 'note', 'audit_fail']
    if all:
        fields = fields_get(req, 'stock.move')

    try:
        moves = do_search_read(req, 'stock.move', fields, 0, False, [('id', 'in', ids)], None)
    except Exception:
        _logger.debug('moves not found for ids: %s', ids)

    if not moves:
        raise Exception("AccessDenied")

    return moves

def get_stock_pickings(req, pid, limit=10):
    """
    Search for last 100 packing slip uploads for the vendor.
    @param req: object
    @param pid: partner_id
    @param limit: number of records in result
    @return: dict
    """
    pickings = None
    fields = ['date', 'origin', 'purchase_id', 'state', 'partner_id', 'move_lines', 'product_id']
    try:
        pickings = do_search_read(req, 'stock.picking.in', fields, 0, limit, [('partner_id.id', '=', pid),
                                                                              ('type', '=', 'in')
                                                                             ], None)
    except Exception:
        _logger.debug('No stock.picking.in instances found for partner ID: %s', pid)

    if not pickings:
        raise Exception("AccessDenied")

    return pickings




def random_string(size, format):
    """
    Generate some random characters of length size=n.
    @param size: Int (Size of random string returned.)
    @param format: String (hex, letters, digits)
    @type size: IntType
    @type format: StringType
    @return: String
    """
    formats = ('hex', 'letters', 'digits')
    assert type(size) is IntType, "size is not an integer: %r" % size
    assert type(format) is StringType, "format is not a string: %r" % format
    format = format.lower()
    if format in formats:
        allowed = ''
        if format == formats[1]:   # Generate string comprised of random letters.
            allowed = string.ascii_letters
        elif format == formats[0]: # Generate string comprised of random letters and numbers.
            allowed = string.hexdigits
        elif format == formats[2]: # Generate string comprised of random numbers.
            allowed = string.digits

    else:
        raise TypeError

    return ''.join([allowed[random.randint(0, len(allowed) - 1)] for x in xrange(size)])

# -----------------------------------------------| VMI Session Object.
class Session(vmiweb.Controller):
    _cp_path = "/vmi/session"

    def session_info(self, req):
        req.session.ensure_valid()
        uid = req.session._uid
        args = req.httprequest.args
        request_id = str(req.jsonrequest['id'])
        _logger.debug('JSON Request ID: %s', request_id)
        res = {}
        if request_id == 'DBE': # Check to see if user is a DBE vendor
            try:                                                                # Get vendor ID for session
                vendor = get_vendor_id(req, uid)['records'][0]
            except IndexError:
                _logger.debug('Vendor not found for user ID: %s', uid)
                return {'error': _('No Vendor found for this User ID!'), 'title': _('Vendor Not Found')}
            res = {
                "session_id": req.session_id,
                "uid": req.session._uid,
                "user_context": req.session.get_context() if req.session._uid else {},
                "db": req.session._db,
                "username": req.session._login,
                "vendor_id": vendor['id'],
                "company": vendor['company'],
            }
        elif request_id == 'VMI': # Check to see if user is a VMI vendor
            try:                                                                                # Get Partner ID for session
                vendor = get_partner_id(req, uid)['records'][0]
            except IndexError:
                _logger.debug('Partner not found for user ID: %s', uid)
                return {'error': _('No Partner found for this User ID!'), 'title': _('Partner Not Found')}
            company = ""
            if vendor.has_key('company'):
                company = vendor['company']
            res = {
                "session_id": req.session_id,
                "uid": req.session._uid,
                "user_context": req.session.get_context() if req.session._uid else {},
                "db": req.session._db,
                "username": req.session._login,
                "partner_id": vendor['partner_id'][0],
                "company": vendor['partner_id'][1],
            }
        else: # Allow login for valid user without Vendor or Partner such as Admin or Manager
            res = {
                "session_id": req.session_id,
                "uid": req.session._uid,
                "user_context": req.session.get_context() if req.session._uid else {},
                "db": req.session._db,
                "username": req.session._login,
            }
        return res

    @vmiweb.jsonrequest
    def get_session_info(self, req):
        return self.session_info(req)

    @vmiweb.jsonrequest
    def authenticate(self, req, db, login, password, base_location=None):
        wsgienv = req.httprequest.environ
        env = dict(
            base_location=base_location,
            HTTP_HOST=wsgienv['HTTP_HOST'],
            REMOTE_ADDR=wsgienv['REMOTE_ADDR'],
        )
        req.session.authenticate(db, login, password, env)

        return self.session_info(req)

    @vmiweb.jsonrequest
    def change_password(self, req, fields):
        old_password, new_password, confirm_password = operator.itemgetter('old_pwd', 'new_password', 'confirm_pwd')(
            dict(map(operator.itemgetter('name', 'value'), fields)))
        if not (old_password.strip() and new_password.strip() and confirm_password.strip()):
            return {'error': _('You cannot leave any password empty.'), 'title': _('Change Password')}
        if new_password != confirm_password:
            return {'error': _('The new password and its confirmation must be identical.'),
                    'title': _('Change Password')}
        try:
            if req.session.model('res.users').change_password(
                    old_password, new_password):
                return {'new_password': new_password}
        except Exception:
            return {'error': _('The old password you provided is incorrect, your password was not changed.'),
                    'title': _('Change Password')}
        return {'error': _('Error, password not changed !'), 'title': _('Change Password')}


    @vmiweb.jsonrequest
    def check(self, req):
        req.session.assert_valid()
        return None

    @vmiweb.jsonrequest
    def destroy(self, req):
        req.session._suicide = True

# -----------------------------------------------| VMI Controller Methods.




class VmiController(vmiweb.Controller):
    _cp_path = '/vmi'
    import csv

    _modes = ('N', 'D', 'T')
    _error_page = '/vmi/error'
    _default_stock_location_suffix = ' Input' # This must match the naming convention for locations inside OpenERP.
    _packing_slip_fields = ('month',
                            'day',
                            'year',
                            'vendor_part_number',
                            'bin',
                            'item_description',
                            'uom',
                            'quantity_ordered',
                            'quantity_shipped',
                            'quantity_backordered',
                            'septa_part_number',
                            'line_number',
                            'purchase_order',
                            'supplier',
                            'packing_list_number',
                            'destination',
                            'shipment_type'
    )

    _invoice_fields = ('month',
                       'day',
                       'year',
                       'vendor_part_number',
                       'item_description',
                       'septa_part_number',
                       'quantity_shipped',
                       'uom',
                       'unit_price',
                       'line_total',
                       'line_number',
                       'purchase_order',
                       'supplier',
                       'packing_list_number',
                       'invoice_number',
                       'payment_terms',
                       'destination'
    )
    # These fields from vmi.client.page.
    _template_keys = ('title',
                      'header',
                      'form_flag',
                      'form_action',
                      'form_legend',
                      'template_path',
                      'template_name',
                      'mode'
    )
    _html_template = """<!DOCTYPE html>
        <html style="height: 100%%">
            <head>
                <meta http-equiv="X-UA-Compatible" content="IE=edge,chrome=1"/>
                <meta http-equiv="content-type" content="text/html; charset=utf-8" />
                <title>SEPTA VMI</title>
                <link rel="shortcut icon" href="/vmi/static/src/img/favicon.ico" type="image/x-icon"/>
                <link rel="stylesheet" href="/vmi/static/src/css/main.css" />
                %(css)s
                %(js)s
                <script type="text/javascript">
                  %(script)s
                </script>
            </head>
            <body>
               %(body)s
            </body>
        </html>
        """
    def _get_vmi_client_page(self, req, page):

        """


        @param req:
        @param page: string
        @return: search object
        """

        return get_client_page(req, page)


    def _get_upload_history(self, req, pid):
        """
        Return the vendors packing slip submission history with associated moves details.
        @param req: object
        @param pid: partner_id
        @return: search result object
        """
        #import pdb; pdb.set_trace()
        res = get_stock_pickings(req, pid)['records'] # Find the last 100 stock.picking.in records for current vendor.
        _logger.debug('_get_upload_history initial result count: %s', str(len(res)))
        if res: # Find the associated stock.move records for the current picking.
            for pick in res:
                move_ids = pick['move_lines']
                moves = get_stock_moves_by_id(req, move_ids)['records']
                pick['line_items'] = moves         # Append moves/line items to current picking.
                for line in pick['line_items']:    # Find + append the actual product record for each line item.
                    prod_id = line['product_id'][0]
                    line['product_details'] = get_product_by_id(req, [prod_id])['records'] # Get product records.
                    if line['audit_fail']:
                        pick['audit_fail'] = True # If any line item failed audit then the pick gets flagged as failed.



        _logger.debug('_get_upload_history final result: %s', str(res))
        return res

    def _create_attachment(self, req, model, id, descr, ufile):
        """

        @param req:
        @param model:
        @param id:
        @param descr:
        @param ufile:
        @return:
        """
        uid = newSession(req)
        Model = req.session.model('ir.attachment')
        args = {}
        ufile.seek(0)
        try:
            attachment_id = Model.create({
                                             'name': descr + '_' + ufile.filename,
                                             'datas': base64.encodestring(ufile.read()),
                                             'datas_fname': str(id) + '_' + ufile.filename,
                                             'description': descr,
                                             'res_model': model,
                                             'res_id': int(id)
                                         }, req.context)
            args.update({
                'filename': ufile.filename,
                'id': attachment_id
            })
        except xmlrpclib.Fault, e:
            args.update({'error': e.faultCode})
        return args

    def _validate_products(self, req, csv_rows, pid):
        """

        @param req:
        @param csv_rows:
        @param pid:
        @return: @raise IndexError:
        """
        res = {}
        results = {}
        args = {}
        csv_part_numbers = []
        fields = ['id', 'default_code', 'uom_id']
        db_part_numbers = []
        for row in csv_rows:
            csv_part_numbers.append(row['septa_part_number'].strip())

        if len(csv_part_numbers) == 0:
            _logger.debug('<_validate_products> Packing slip missing part numbers for partner: %s', str(pid))
            raise IndexError("<_validate_products> Product not found in (%r)!" % str(csv_part_numbers))
        else:
            unique_part_numbers = list(set(csv_part_numbers))
            try:
                res = do_search_read(req, 'product.product', fields, 0, False, [('default_code', 'in', unique_part_numbers)], None)
            except xmlrpclib.Fault, e:
                args.update({'error': e.faultCode})
                _logger.debug('<_validate_products> Error finding products in: %s', str(unique_part_numbers))
                return args

            if res is not None:
                for record in res['records']:
                    db_part_numbers.append(record['default_code'])
            else:
                raise IndexError("<_validate_products> No products returned from search: (%r)!" % str(res))

            _logger.debug('<_validate_products> db_part_numbers: %s', db_part_numbers)
            _logger.debug('<_validate_products> csv_part_numbers: %s', unique_part_numbers)
            if cmp(db_part_numbers.sort(), unique_part_numbers.sort()) == 0:
                results.update({'records': res['records'], 'length': len(res), 'valid': True})
            else:
                bad_products = [x for x in unique_part_numbers if x not in db_part_numbers]
                results.update({'records': bad_products, 'length': len(bad_products), 'valid': False})
                _logger.debug('<_validate_products> Invalid products found in packing slip: %s', str(bad_products))

        return results


    def _validate_csv_file(self, filedata, fields):
    #validator = CSVValidator(fields)
    ## basic header and record length checks
    #validator.add_header_check('EX1', 'bad header')
    #validator.add_record_length_check('EX2', 'unexpected record length')
    #data = csv.reader(StringIO(filedata.read()), delimiter='\t')
    #problems = validator.validate(data)
    #if problems:
    #_logger.debug('<_validate_csv_file> CSV file could not be validated: %s', filedata.filename)
        return True

    def _csv_reader(self, filedata, fields):
        """

        @param filedata:
        @param fields:
        @return:
        """
        res = []
        csv = self.csv
        csv.register_dialect('escaped', escapechar='\\', doublequote=False, quoting=csv.QUOTE_NONE)
        csv.register_dialect('singlequote', quotechar="'", quoting=csv.QUOTE_ALL)
        sniffer = csv.Sniffer()
        validated = False
        try:
            validated = self._validate_csv_file(filedata, fields)
        except Exception, e:
            errors = {'error': e.message, 'method': '_csv_reader 1'}
            _logger.debug('<_csv_reader> CSV file could not be validated: %s', errors)
            return errors

        if validated:
            dialect = sniffer.sniff(filedata.readline(), delimiters=',')
            filedata.seek(0)
            reader = csv.DictReader(filedata.readlines(), dialect=csv.excel) # fieldnames=fields,
            try:
                for row in reader:
                    res.append(row)
                    _logger.debug('<_csv_reader> CSV file: %s', str(row))
            except csv.Error as e:
                _logger.debug('<_csv_reader> CSV file could not be read: %s', e.message)
                errors = {'error': e.message, 'method': '_csv_reader 2'}
                return errors

        return {'records': res, 'length': len(res)}

    def _create_stock_picking(self, req, csv_rows, pid):
        """

        @param req:
        @param csv_rows:
        @param pid:
        @return:
        """
        model_name = 'stock.picking.in'
        Model = req.session.model(model_name)
        res = []
        if len(csv_rows) > 0:
            for row in csv_rows:
                rnd = random_string(8, 'digits')
                vendor = str(row['supplier']).strip()
                partner = get_vendor_by_name(req, vendor)['records'][0]
                delivery_date = str(row['year']).strip() + '/' + str(row['month']).strip() + '/' + str(
                    row['day']).strip()
                #_logger.debug('<_create_stock_picking> CSV file: %s', str(row))
                picking_id = Model.create({
                                              'name': row[
                                                          'packing_list_number'].strip() + '.' + delivery_date + '.' + rnd,
                                              'date': delivery_date,
                                              'partner_id': partner['id'],
                                              'origin': row['packing_list_number'].strip(),
                                              'invoice_state': 'none',
                                              'note': row['purchase_order'].strip()
                                          }, req.context)
                res.append({'picking_id': picking_id, 'packing_list': row['packing_list_number'].strip(), 'partner': partner['id']})

        return res

    def _create_move_line(self, req, csv_rows, pid):
        """
        Create an OpenERP stock.move instance for each line item
        within the packing slip.
        @param req: object
        @param csv_rows: lines from packing slip data
        @param pid: Partner ID
        @return: stock.move ID list
        """
        moves = []
        all_locations = []
        model_name = 'stock.move'
        Model = req.session.model(model_name)
        location_id = None
        location_partner = None
        locations = get_stock_locations(req, pid)
        validated_products = self._validate_products(req, csv_rows, pid)
        if len(csv_rows) > 0 and validated_products['valid']:
            product = None
            for csv_row in csv_rows:
                for prod in validated_products['records']: # Verify products in CSV actually exist.
                    _logger.debug('<_create_move_line> Current product: %s', prod['default_code'])
                    if prod['default_code'] == csv_row['septa_part_number'].strip():
                        product = prod
                        break

                for location in locations['records']: # Find the matching stock.location id for the CSV location value.
                    location_name = str(csv_row['destination']).strip() + self._default_stock_location_suffix
                    if location['name'].upper() == location_name.upper():
                        location_id = location['id']
                        if location['partner_id']:
                            location_partner = location['partner_id'][0]
                        _logger.debug('<_create_move_line> Location Id: %s, Location Name: %s', str(location_id), location_name)
                        break

                if not location_id:
                    raise ValueError("(%r) is not a proper value for destination location!" % str(csv_row['destination']))
                else:
                    all_locations.append(location_id)

                delivery_date = str(csv_row['year']).strip() + '/' + str(csv_row['month']).strip() + '/' + str(
                    csv_row['day']).strip()
                move_id = Model.create({
                    'product_id': product['id'],
                    'name': csv_row['packing_list_number'].strip() + '.' + delivery_date + '.' + random_string(8, 'digits'),
                    'product_uom': product['uom_id'][0],
                    'product_qty': float(csv_row['quantity_shipped']),
                    'location_dest_id': location_id,
                    'location_id': csv_row['partner'],
                    'partner_id': location_partner,
                    'picking_id': csv_row['picking_id'],
                    'date': delivery_date,
                })
                moves.append(move_id)

        else:
            _logger.debug('<_create_move_line> Moves not created due to bad products: %s', validated_products['records'])

        return {'moves': moves, 'locations': list(set(all_locations))}


    def _parse_packing_slip(self, req, filedata, pid):
        result = {}
        ps_vals = {}
        ps_lines = []
        fields = self._packing_slip_fields
        res = self._csv_reader(filedata, fields)
        if res.has_key('error'):
            _logger.debug('<_parse_packing_slip> CSV reader returned an error: %s', res['error'])
            return res
        else:
            #res['records'].sort(cmp=lambda x,y : cmp(x['packing_list_number'], y['packing_list_number']))
            unique_slips = []
            pickings = []
            for record in res['records']:
                ps_lines.append(record.copy())
                if record['packing_list_number'] not in unique_slips:
                    unique_slips.append(record['packing_list_number'])
                    pickings.append(record)

            picked = self._create_stock_picking(req, pickings, pid)
            for pick in picked:
                attached = self._create_attachment(req, 'stock.picking.in', pick['picking_id'], pick['packing_list'],
                                                   filedata)
                if attached.has_key('error'):
                    _logger.debug('<_parse_packing_slip> _create_attachment returned an error: %s', attached['error'])

            for line in ps_lines:
                for pick in picked:
                    if pick['packing_list'] == line['packing_list_number']:
                        line.update(pick)
                        #del line['packing_list_number']
                        break

            moves = self._create_move_line(req, ps_lines, pid)

        result.update({'stock_pickings': picked, 'move_lines': moves, 'pid': pid})
        _logger.debug('<_parse_packing_slip> returned values: %s', str(result))
        return result #{'stock_pickings': [{'picking_id': picking_id, 'packing_list': packing_list_number}],
                      # 'move_lines': {'moves': [id], 'locations', [id]
                      # 'pid': id}


    def _call_methods(self, req, model, method, args, **kwargs):
        """
        For calling public methods on OpenERP models.
        @param req: object
        @param model: name of OpenERP model.
        @param method: name of model method to be called.
        @param args: list of arguments for called method.
        @param kwargs: ? (Godzilla and Staypuft wrecking the city in an apocalyptic death match)
        """
        res = None
        if hasattr(req.session.model(model), method):
            func = getattr(req.session.model(model), method, None)
            if callable(func):
                res = func(*args, **kwargs)

        else:
            _logger.debug('<_call_methods> Method %s not found on model %s', method, model)
            return req.not_found()

        return res


    @vmiweb.httprequest
    def index(self, req, mod=None, **kwargs):
        #vmi_client_page = self._get_vmi_client_page(req, 'index')
        js = """

$(document).ready(function(){
	$("form#loginForm").submit(function() { // loginForm is submitted
	var username = $('#username').attr('value'); // get username
	var password = $('#password').attr('value'); // get password


	if (username && password) { // values are not empty
		$.ajax({
		type: "POST",
		url: "/vmi/session/authenticate", // URL of OpenERP Authentication Handler
		contentType: "application/json; charset=utf-8",
		dataType: "json",
		// send username and password as parameters to OpenERP
		data:	 '{"jsonrpc": "2.0", "method": "call", "params": {"session_id": null, "context": {}, "login": "' + username + '", "password": "' + password + '", "db": "dev_main"}, "id": "VMI"}',
		// script call was *not* successful
		error: function(XMLHttpRequest, textStatus, errorThrown) {
			$('div#loginResult').text("responseText: " + XMLHttpRequest.responseText
			+ ", textStatus: " + textStatus
			+ ", errorThrown: " + errorThrown);
			$('div#loginResult').addClass("error");
		}, // error
		// script call was successful
		// data contains the JSON values returned by OpenERP
		success: function(data){
			if (data.result.error) { // script returned error
			$('div#loginResult').text("data.result.title: " + data.result.error);
			$('div#loginResult').addClass("error");
			} // if
			else { // login was successful
			$('form#loginForm').hide();
			$('div#loginResult').html("<h2>Success!</h2> "
				+ " Welcome <b>" + data.result.company + "</b>");
			$('div#loginResult').addClass("success");
			responseData = data.result;
			sessionid = data.result.session_id;
			$('div#vmi_menu').fadeIn();
			} //else
		} // success
		}); // ajax
	} // if
	else {
		$('div#loginResult').text("enter username and password");
		$('div#loginResult').addClass("error");
	} // else
	$('div#loginResult').fadeIn();
	return false;
	});
});

		"""
        input = ''
        try:
            input = open('/home/amir/dev/parts/openerp-7.0-20131118-002448/openerp/addons/vmi/vmi_web/template/index.html', 'r')
        except IOError, e:
            _logger.debug('opening the template file %s returned an error: %s, with message %s', e.filename, e.strerror, e.message)
        finally:
            pass

        template = simpleTAL.compileHTMLTemplate(input)
        input.close()

        context = simpleTALES.Context()
        # Add a string to the context under the variable title
        context.addGlobal("title", "SEPTA VMI Client")
        context.addGlobal("script", js)

        output = cStringIO.StringIO()
        template.expand(context, output)
        return output.getvalue()

    @vmiweb.httprequest
    def upload(self, req, mod=None, **kwargs):
        """
        Controller for VMI Packing Slip Upload Page
        @param req: request object
        @param mod: mode selector (N, D, T)
        @param kwargs:
        @return: TAL Template
        """
        page_name = 'upload'
        redirect_url = self._error_page
        req.session.ensure_valid()
        uid = newSession(req)
        temp_globals = dict.fromkeys(self._template_keys, None)
        vmi_client_page = self._get_vmi_client_page(req, page_name)['records']
        if vmi_client_page: # Set the mode for the controller and template.
            for key in temp_globals:
                temp_globals[key] = vmi_client_page[0][key]

            if mod is None:
                mod = vmi_client_page[0]['mode']
        else:
            _logger.debug('No vmi.client.page record found for page name %s!', page_name)
            return req.not_found()

        if mod is not None:
            if mod not in self._modes:
                raise KeyError

        js = 'var csvFields = new Array%s;\n' % str(self._packing_slip_fields)
        js += 'var mode = "%s";\n' % mod
        temp_location = os.path.join(vmi_client_page[0]['template_path'], vmi_client_page[0]['template_name'])
        input = ''
        try:
            input = open(temp_location, 'r')
        except IOError, e:
            _logger.debug('opening the template file %s returned an error: %s, with message %s', e.filename, e.strerror, e.message)
        finally:
            pass

        # If the template file not found or readable then redirect to error page.
        if not input:
            return req.not_found()

        template = simpleTAL.compileHTMLTemplate(input)
        input.close()
        sid = req.session_id
        uid = 17 #req.context['uid']
        pid = 9
        context = simpleTALES.Context()
        # Add a string to the context under the variable title
        context.addGlobal("title", temp_globals['title'])
        context.addGlobal("script", js)
        context.addGlobal("header", temp_globals['header'])
        context.addGlobal("form_flag", temp_globals['form_flag'])
        context.addGlobal("form_action", temp_globals['form_action'])
        context.addGlobal("form_legend", temp_globals['form_legend'])
        context.addGlobal("sid", sid)
        context.addGlobal("pid", pid)
        context.addGlobal("uid", uid)
        context.addGlobal("mode", mod)
        output = cStringIO.StringIO()
        template.expand(context, output)
        return output.getvalue()

    @vmiweb.httprequest
    def result(self, req, mod=None, **kwargs):
        """
        Controller for upload result page.
        @param req: request object
        @param mod: mode selector (N, D, T)
        @param kwargs: Zombies, locusts, nuclear fallout, Richard Simmons!
        @return: TAL Template
        """

        if mod is not None:
            if mod not in self._modes:
                raise KeyError

        pid = None
        local_vals = {}
        if kwargs is not None:
            local_vals.update(kwargs)
            pid = local_vals.get('pid')
        else:
            try:    # Get Partner ID for session
                pid = get_partner_id(req, req.session._uid)['records'][0]
            except IndexError:
                _logger.debug('Partner not found for user ID: %s', uid)
                return {'error': _('No Partner found for this User ID!'), 'title': _('Partner Not Found')}

        page_name = 'result'
        redirect_url = self._error_page
        req.session.ensure_valid()
        uid = newSession(req)
        temp_globals = dict.fromkeys(self._template_keys, None)
        vmi_client_page = self._get_vmi_client_page(req, page_name)['records']
        if vmi_client_page: # Set the mode for the controller and template.
            for key in temp_globals:
                temp_globals[key] = vmi_client_page[0][key]

#            if mod is None:
#                mod = vmi_client_page[0]['mode']
        else:
            _logger.debug('No vmi.client.page record found for page name %s!', page_name)
            return req.not_found()

        temp_location = os.path.join(vmi_client_page[0]['template_path'], vmi_client_page[0]['template_name'])
        input = ''
        try:
            input = open(temp_location, 'r')
        except IOError, e:
            _logger.debug('opening the template file %s returned an error: %s, with message %s', e.filename, e.strerror, e.message)
        finally:
            pass

        # If the template file not found or readable then redirect to error page.
        if not input:
            _logger.debug('No template found for page name %s!', page_name)
            return req.not_found()

        template = simpleTAL.compileHTMLTemplate(input)
        input.close()
        history = simplejson.dumps(self._get_upload_history(req, pid))
        js = 'var history_data = %s;\n' % history
        js += 'var mode = "%s";\n' % mod
        sid = req.session_id
        uid = 17 #req.context['uid']
        pid = 9
        context = simpleTALES.Context()
        if 'audit_result' in local_vals: # Append the result of audit flagging.
            js += 'var audit = "%s";\n' % simplejson.dumps(local_vals['audit_result'])
            context.addGlobal("audit_result", local_vals['audit_result'])
        if 'error' in local_vals:        # Append errors generated by the parsing of the file.
            js += 'var error = "%s";\n' % simplejson.dumps(local_vals['error'])
            context.addGlobal("error", local_vals['error'])
            temp_globals['form_flag'] = False
        # Add a string to the context under the variable title
        context.addGlobal("title", temp_globals['title'])
        context.addGlobal("script", js)
        context.addGlobal("header", temp_globals['header'])
        context.addGlobal("form_flag", temp_globals['form_flag'])
        context.addGlobal("form_action", temp_globals['form_action'])
        context.addGlobal("form_legend", temp_globals['form_legend'])
        context.addGlobal("sid", sid)
        context.addGlobal("pid", pid)
        context.addGlobal("uid", uid)
        context.addGlobal("mode", mod)
        output = cStringIO.StringIO()
        template.expand(context, output)
        return output.getvalue()

    @vmiweb.httprequest
    def packing_slip(self, req, mod=None, **kwargs):
        #vmi_client_page = self._get_vmi_client_page(req, 'upload')
        js = 'var csvFields = new Array%s;' %str(self._packing_slip_fields)
        input = open(
            '/home/amir/dev/parts/openerp-7.0-20131118-002448/openerp/addons/vmi/vmi_web/template/upload.html',
            'r')
        template = simpleTAL.compileHTMLTemplate(input)
        input.close()
        form_flag = True
        sid = req.session_id
        uid = 17 #req.context['uid']
        pid = 9
        context = simpleTALES.Context()
        # Add a string to the context under the variable title
        context.addGlobal("title", "SEPTA VMI Packing Slip")
        context.addGlobal("script", js)
        context.addGlobal("header", "Packing Slip")
        context.addGlobal("form_flag", form_flag)
        context.addGlobal("sid", sid)
        context.addGlobal("pid", pid)
        context.addGlobal("uid", uid)
        output = cStringIO.StringIO()
        template.expand(context, output)
        return output.getvalue()

    @vmiweb.httprequest
    def invoice(self, req, mod=None, **kwargs):
        #vmi_client_page = self._get_vmi_client_page(req, 'invoice')
        input = open(
            '/home/amir/dev/parts/openerp-7.0-20131118-002448/openerp/addons/vmi/vmi_web/template/vmi_invoice.html',
            'r')
        template = simpleTAL.compileHTMLTemplate(input)
        input.close()

        context = simpleTALES.Context()
        # Add a string to the context under the variable title
        context.addGlobal("title", "SEPTA VMI Invoice")
        context.addGlobal("script", "")
        context.addGlobal("header", "Invoice")

        output = cStringIO.StringIO()
        template.expand(context, output)
        return output.getvalue()

    @vmiweb.httprequest
    def upload_vmi_document(self, req, pid, uid, contents_length, callback, ufile):
        #session_data = Session.session_info(req.session)
        #vmi_client_page = self._get_vmi_client_page(req, 'upload')
        args = {}
        picking_id = None
        form_flag = True
        title = '...page title goes here...'
        header = '...brief instructions go here...'
        req.session.ensure_valid()
        uid = newSession(req)
        model = None
        input = None
        if contents_length:
            #import pdb; pdb.set_trace()
            try:
                self._parse_packing_slip(req, ufile, pid)
            except Exception, e:
                args = {'error': str(e) }

            try:
                input = open('/home/amir/dev/parts/openerp-7.0-20131118-002448/openerp/addons/vmi/vmi_web/template/upload.html', 'r')
            except IOError, e:
                _logger.debug('opening the template file %s returned an error: %s, with message %s', e.filename, e.strerror, e.message)
            finally:
                pass

        template = simpleTAL.compileHTMLTemplate(input)
        input.close()
        context = simpleTALES.Context()

        #try:
        #attachment_id = Model.create(parsedata, req.context)
        #except xmlrpclib.Fault, e:
        #args = {'error':e.faultCode }
        if args:
            form_flag = False

        req.session._suicide = True
        script = """var callback = %s; \n var return_args = %s;""" % (
            simplejson.dumps(callback), simplejson.dumps(args))
        context.addGlobal("title", title)
        context.addGlobal("script", script)
        context.addGlobal("header", header)
        context.addGlobal("picking_id", picking_id)
        context.addGlobal("form_flag", form_flag)

        output = cStringIO.StringIO()
        template.expand(context, output)
        return output.getvalue()

    @vmiweb.httprequest
    def saveas(self, req, model, field, id=None, filename_field=None, **kw):
        """ Download link for files stored as binary fields.

        If the ``id`` parameter is omitted, fetches the default value for the
        binary field (via ``default_get``), otherwise fetches the field for
        that precise record.

        :param req: OpenERP request
        :type req: :class:`web.common.http.HttpRequest`
        :param str model: name of the model to fetch the binary from
        :param str field: binary field
        :param str id: id of the record from which to fetch the binary
        :param str filename_field: field holding the file's name, if any
        :returns: :class:`werkzeug.wrappers.Response`
        """
        Model = req.session.model(model)
        fields = [field]
        if filename_field:
            fields.append(filename_field)
        if id:
            res = Model.read([int(id)], fields, req.context)[0]
        else:
            res = Model.default_get(fields, req.context)
        filecontent = base64.b64decode(res.get(field, ''))
        if not filecontent:
            return req.not_found()
        else:
            filename = '%s_%s' % (model.replace('.', '_'), id)
            if filename_field:
                filename = res.get(filename_field, '') or filename
            return req.make_response(filecontent,
                [('Content-Type', 'application/octet-stream'),
                 ('Content-Disposition', content_disposition(filename, req))])


    @vmiweb.httprequest
    def upload_document(self, req, pid, uid, contents_length, callback, ufile):

        """

        @param req: object
        @param pid: partner ID
        @param uid: user ID
        @param contents_length:
        @param callback:
        @param ufile: file contents
        @return:
        """
        page_name = 'upload_document'
        #session_data = Session.session_info(req.session)
        mod = None
        args = {}
        args.update({'pid': pid})
        args.update({'uid': uid})
        uid = newSession(req)
        vmi_client_page = self._get_vmi_client_page(req, page_name)['records']
        if vmi_client_page: # Set the mode for the controller and template.
            temp_globals = dict.fromkeys(self._template_keys, None)
            for key in temp_globals:
                temp_globals[key] = vmi_client_page[0][key]

            if mod is None:
                mod = vmi_client_page[0]['mode']
        else:
            _logger.debug('No vmi.client.page record found for page name %s!', page_name)
            return req.not_found()

        if mod is not None:
            if mod not in self._modes:
                _logger.debug('<upload_document>The mode is not set to a recognized value: %s!', str(mod))
                raise KeyError
#            else:
#                args.update({'mod': mod})


        req.session.ensure_valid()
        uid = newSession(req)
        if contents_length:
            if ufile:
                result = None
                #import pdb; pdb.set_trace()
                try:
                    result = self._parse_packing_slip(req, ufile, pid) # Parse CSV file contents.
                except Exception, e:
                    args.update({'error': str(e) })
                    _logger.debug('<upload_document>_parse_packing_slip failed: %s!', str(e))

                args.update({'parse_result': result})
            else:
                args.update({'error': 'File is empty or invalid!'})

        if 'error' not in args:
            result = None
            vals = args.copy()
            vals['pid'] = 31
            #import pdb; pdb.set_trace()
            try:
                result = self._call_methods(req, 'stock.picking.in', 'action_flag_audit', [vals, None]) # Flag audits.
            except Exception, e:
                args.update({'error': str(e) })
                _logger.debug('<upload_document>_call_methods failed: %s!', str(e))

            args.update({'audit_result': result})

        if 'audit_result' in args: # Call the Done method on moves that weren't flagged for audit.
            if 'move_lines' in args['parse_result']:
                result = None
                moves = args['parse_result']['move_lines']
                unflagged = []
                for move in moves['moves']:
                    if move not in args['audit_result']:
                        unflagged.append(move)
                #import pdb; pdb.set_trace()

                try:
                    result = self._call_methods(req, 'stock.move', 'action_done', [unflagged, None])
                except Exception, e:
                    args.update({'error': str(e) })
                    _logger.debug('<upload_document>_call_methods failed: %s!', str(e))

                _logger.debug('<upload_document>unflagged moves set to done: %s!', str(unflagged))


        kwargs = args.copy()
        return self.result(req, None, **kwargs)
