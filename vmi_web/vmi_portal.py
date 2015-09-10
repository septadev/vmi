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
import sys

from datetime import datetime, date
from pytz import timezone
from types import *
from simpletal import simpleTAL, simpleTALES
from openerp.tools.translate import _
from openerp.tools.config import configmanager
import openerp.addons.web.http as vmiweb

_logger = logging.getLogger(__name__)

# read config file to get db info
command = sys.argv
if '-c' in command:
    config_file = command[command.index('-c') + 1]
    config = configmanager()
    config.parse_config(['-c', config_file])
    db = config.options['client_db']
    login = config.options['client_user'] or 'admin'
    password = config.options['client_password'] or 'admin'
else:
    raise Exception("Please specify the config file")

# -----------------------------------------------| VMI Global Methods.

def check_request(req, source):
    """
    Check if req is a auth request
    :param req:
    :param source: source page
    :return:
    """
    error = []
    if 'id' not in req.jsonrequest:
        error.append('id')
    if error:
        res = {
            'code': 400,
            'message': "OpenERP WebClient Error",
            'error': {
                'type': 'Bad Request',
                'text': 'Missing Parameter(s) in ' + error
            }
        }
        return res

def fields_get(req, model):
    Model = req.session.model(model)
    fields = Model.fields_get(False, req.context)
    return fields

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
    """
    Create admin session only to query the username/password
    :param req:
    :return: admin's id
    """

    return req.session.authenticate(db, login, password)


def check_partner_parent(req, pid):
    """
    get the vendor id
    :param req:
    :param pid: vendor user id
    :return: vendor id
    """
    res = None
    parent_id = None
    fields = fields_get(req, 'res.partner')
    try:
        res = do_search_read(req, 'res.partner', fields, 0, False, [('id', '=', pid)], None)
    except Exception:
        _logger.debug('<check_partner_parent> Session expired or Partner not found for partner ID: %s', pid)

    if res:
        record = res['records'][0]
        if record['parent_id']:
            parent_id = record['parent_id'][0]
        else:
            raise Exception("AccessDenied")
    else:
        return False

    return parent_id


def get_partner(req, pid):
    """

    :param req:
    :param pid: partner id
    :return: all fields from this partner
    """
    partner = None
    fields = fields_get(req, 'res.partner')
    try:
        partner = do_search_read(req, 'res.partner', fields, 0, False, [('id', '=', pid)], None)
    except Exception:
        _logger.debug('<get_partner> Partner not found for ID: %s', pid)

    if not partner:
        raise Exception("AccessDenied")

    return partner


def get_vendor_by_name(req, name):
    """
    Find the partner record for the supplied vendor name.
    @param req: object
    @param name: string of vendor's name
    @return: partner record
    """
    partner = None
    fields = fields_get(req, 'res.partner')
    try:
        partner = do_search_read(req, 'res.partner', fields, 0, False, [('name', '=', name), ('supplier', '=', True)],
                                 None)
    except Exception:
        _logger.debug('<get_vendor_by_name> Partner not found for ID: %s', name)

    if not partner:
        raise Exception("AccessDenied")

    return partner


def get_partner_id(req, uid=None, **kwargs):
    """
    Find the partner associated to the current logged-in user
    :param req:
    :param uid: user_id
    :param kwargs:
    :return:
    """
    partner_ids = None
    try:
        partner_ids = do_search_read(req, 'res.users', ['partner_id'], 0, False, [('id', '=', uid)], None)
    except Exception:
        _logger.debug('<get_partner_id> Session expired or Partner not found for user ID: %s', uid)
        raise ('<get_partner_id> Session expired or Partner not found for user ID: %s', uid)

    record = partner_ids['records'][0]
    pid = record['partner_id'][0]
    parent_id = check_partner_parent(req, pid)
    if parent_id:
        p = get_partner(req, parent_id)
        parent = p['records'][0]
        record['company'] = parent['name']
        record['company_id'] = parent['id']
        # record['remained_audit'] = parent['mobile']
        # record['last_record'] = parent['birthdate']
        partner_ids['records'].append(record)
        partner_ids['records'].pop(0)

    _logger.debug('Partner ID: %s', partner_ids)
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
    # _logger.debug('stock locations: %s', str(stock_locations['records']))
    return stock_locations


def get_stock_locations_by_name(req, pid, name):
    """

    @param req: object
    @param pid: partner ID
    @param kwargs:
    @return: search result of matched stock.location instances
    """
    stock_locations = None
    fields = ['name', 'id', 'location_id', 'partner_id']
    domain = [('name', 'ilike', name)]
    try:
        stock_locations = do_search_read(req, 'stock.location', fields, 0, False, domain, None)
    except Exception:
        _logger.debug('stock locations not found for name: %s', name)

    if not stock_locations:
        raise Exception("AccessDenied")
    # _logger.debug('stock locations: %s', str(stock_locations['records']))
    return stock_locations


def get_stocks(req, ids):
    """
    function to get all stock warehouses in stock.location
    :param req:
    :param ids:
    :return: search result of matched stock.warehouse instances
    """
    stocks = None
    stock_locations_obj = req.session.model('stock.location')
    fields = ['name', 'id', 'partner_id']
    try:
        stocks = do_search_read(req, 'stock.location', fields, 0, False, [('name', 'like', '% Stock')], None)
    except Exception:
        _logger.debug('stock warehouses not found for ids: %s', ids)

    if not stocks:
        raise Exception("AccessDenied")

    return stocks


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
    # _logger.debug('stock locations: %s', str(stock_locations['records']))
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


def get_product_by_pn(req, pn, all=False):
    """
    Search for products with specific ids.
    @param req: object
    @param pn: location_ids
    @param all: selects all fields in result
    @return: search result of specified product.product record(s).
    """
    products = None
    fields = ['name', 'id', 'default_code', 'vendor_part_number', 'description', 'categ_id', 'seller_ids',
              'standard_price', 'uom_id']
    if all:
        fields = fields_get(req, 'product.product')

    try:
        products = do_search_read(req, 'product.product', fields, 0, False, [('default_code', '=', pn)], None)
    except Exception:
        _logger.debug('<get_product_by_id> products not found for ids: %s', pn)

    if not products:
        raise Exception("AccessDenied")
    return products


def search_products_by_septa_pn(req, pn, all=False):
    """
    Search for products with specific part numbers.
    @param req: object
    @param pn: part number string
    @param all: selects all fields in result
    @return: search result of specified product.product record(s).
    """
    #store all numbers in list and filter empty one
    part_numbers = filter(lambda value: value != '', [x.strip() for x in pn.split(';')])
    products = None
    fields = ['name', 'id', 'default_code', 'vendor_part_number', 'description', 'categ_id', 'seller_ids',
              'standard_price', 'uom_id']
    if all:
        fields = fields_get(req, 'product.product')

    if len(part_numbers) == 1:
        try:  # Try finding records with SEPTA P/N.
            products = do_search_read(req, 'product.product', fields, 0, False, [('default_code', 'ilike', part_numbers[0])], None)
        except Exception:
            _logger.debug('<search_products_by_pn> products not found for SEPTA part number: %s', pn)
        found_parts = [products['records'][0]['default_code'] if len(products['records']) == 1 else None]
    else:
        try:  # Try finding records with SEPTA P/Ns.
            products = do_search_read(req, 'product.product', fields, 0, False, [('default_code', 'in', part_numbers)], None)
        except Exception:
            _logger.debug('<search_products_by_pn> products not found for SEPTA part number: %s', pn)
        found_parts = [x['default_code'] for x in products['records']]

    # Find missing data
    missing_parts = list(set(part_numbers) - set(found_parts))
    if len(missing_parts) > 0:
        products['missing_septa_pn'] = missing_parts

    return products


def search_products_by_vendor_pn(req, pn, all=False):
    """
    Search for products with specific part numbers.
    @param req: object
    @param pn: part number string
    @param all: selects all fields in result
    @return: search result of specified product.product record(s).
    """
    #store all numbers in list and filter empty one
    part_numbers = filter(lambda value: value != '', [x.strip() for x in pn.split(';')])
    products = None
    fields = ['name', 'id', 'default_code', 'vendor_part_number', 'description', 'categ_id', 'seller_ids',
              'standard_price', 'uom_id']
    if all:
        fields = fields_get(req, 'product.product')

    if len(part_numbers) == 1:
        try:  # Try finding records with VENDOR P/N.
            products = do_search_read(req, 'product.product', fields, 0, False, [('vendor_part_number', 'ilike', part_numbers[0])], None)
        except Exception:
            _logger.debug('<search_products_by_vendor_pn> products not found for SEPTA part number: %s', pn)
        found_parts = [products['records'][0]['vendor_part_number'] if len(products['records']) == 1 else None]
    else:
        try:  # Try finding records with VENDOR P/Ns.
            products = do_search_read(req, 'product.product', fields, 0, False, [('vendor_part_number', 'in', part_numbers)], None)
        except Exception:
            _logger.debug('<search_products_by_septa_pn> products not found for SEPTA part number: %s', pn)
        found_parts = [x['vendor_part_number'] for x in products['records']]
    #find missing data
    missing_parts = list(set(part_numbers) - set(found_parts))
    if len(missing_parts) > 0:
        products['missing_vendor_pn'] = missing_parts

    return products


def get_client_page(req, page):
    """
    Search for vmi.client.page instances for client page.
    @param req: object
    @param page: string
    @return: search result of matched client page instances
    """
    client = None
    fields = fields_get(req, 'vmi.client.page')
    try:
        client = do_search_read(req, 'vmi.client.page', fields, 0, False, [('name', '=', page)], None)
    except Exception:
        _logger.debug('<get_client_page> VMI Page not found for ID: %s', page)

    if not client:
        raise Exception("AccessDenied")

    return client


def get_stock_moves_by_id(req, ids):
    """
    search stock.moves with specific ids.
    @param req: object
    @param ids: stock.move ids
    """
    moves = None
    stock_move_obj = req.session.model('stock.move')
    product_obj = req.session.model('product.product')
    fields = ['id', 'origin', 'create_date', 'product_id', 'product_qty', 'product_uom', 'location_dest_id',
              'audit_fail', 'vendor_part_number']
    try:
        moves = stock_move_obj.read(ids, fields, None)
        # moves = do_search_read(req, 'stock.move', fields, 0, False, [('id', 'in', ids)], None)
    except Exception:
        _logger.debug('<get_stock_moves_by_id> Moves not found for ids: %s', ids)

    for line in moves:
        if line['product_id']:
            product = product_obj.read(line['product_id'][0],
                                       ['default_code', 'vendor_part_number', 'categ_id', 'description'], None)
            line['septa_part_number'] = product['default_code']
            line['vendor_part_number'] = product['vendor_part_number']
            line['categ_id'] = product['categ_id']
            line['description'] = product['description']

    if not moves:
        raise Exception("AccessDenied")

    return moves


def get_invoice_line(req, ids, uid):
    """
    get invoice.line by id
    :param req: object
    :param ids: account.invoice.line
    :return: search result of matched invoice line instances
    """
    lines = None
    account_invoice_line_obj = req.session.model('account.invoice.line')
    move_obj = req.session.model('stock.move')
    product_obj = req.session.model('product.product')
    picking_obj = req.session.model('stock.picking')
    fields = ['invoice_id', 'price_unit', 'price_subtotal', 'discount', 'quantity', 'product_id', 'stock_move_id']
    try:
        lines = account_invoice_line_obj.read(ids, fields, None)
    except Exception:
        _logger.debug('<get_invoice_line> Invoice_lines not found for ids: %s', ids)

    if not lines:
        raise Exception("Access Denied")

    for line in lines:
        if line['stock_move_id']:

            move = move_obj.read(line['stock_move_id'][0], ['date', 'origin', 'product_uom', 'product_qty', 'picking_id'], None)
            product = product_obj.read(line['product_id'][0], ['default_code', 'vendor_part_number'], None)
            picking = picking_obj.read(move['picking_id'][0], ['date_done'], None)

            line['date_received'] = picking['date_done'].split(' ')[0]
            line['picking_number'] = move['origin']
            line['septa_part_number'] = product['default_code']
            line['vendor_part_number'] = product['vendor_part_number']
            line['unit_of_measure'] = move['product_uom']
            line['quantity_received'] = move['product_qty']

    return lines


'''def get_stock_pickings_ori(req, pid):
    """
    Search for last 100 packing slip uploads for the vendor.
    @param req: object
    @param pid: partner_id
    @return: dict
    """
    today = date.today()
    two_years_before = str(today.replace(year=today.year - 2))
    pickings = None
    _logger.debug('<get_stock_pickings> partner ID: %s', pid)
    fields = ['date', 'origin', 'invoice_state', 'state', 'partner_id', 'move_lines', 'product_id']
    try:
        pickings = do_search_read(req, 'stock.picking.in', fields, 0, False, [('partner_id.id', '=', pid),
                                                                              ('type', '=', 'in'),
                                                                              ('date_done', '>', two_years_before)
        ], None)
    except Exception:
        _logger.debug('<get_stock_pickings> No stock.picking.in instances found for partner ID: %s', pid)

    if not pickings:
        raise Exception("AccessDenied")

    return pickings'''


def get_stock_pickings(req, pid):
    """
    get picking info from stock.picking, receive data from review page
    :param req:
    :param pid:
    :return: search result of matched packaging slips
    """
    pickings = {}
    context = req.context
    current_year = date.today().year
    current_month = date.today().month
    # get data for current month
    if 'year' not in context or 'month' not in context:
        context['year'] = current_year
        context['month'] = current_month
        filters = [('date_done', 'like', '%(year)s-%(month)s-' % {'year': str(context['year']),
                                                                  'month': '%02d' % int(context['month'])} + '%')]
    # get user requested data
    else:
        if context['day'] != '0':
            filters = [('date_done', 'like', '%(year)s-%(month)s-%(day)s' % {'year': str(context['year']),
                                                                             'month': '%02d' % int(context['month']),
                                                                             'day': '%02d' % int(
                                                                                 context['day'])} + '%')]
        else:
            filters = [('date_done', 'like', '%(year)s-%(month)s-' % {'year': str(context['year']),
                                                                      'month': '%02d' % int(context['month'])} + '%')]
        if context['location'] != '0':
            filters.append(('location_dest_id', '=', context['location']))
        if context['audit'] != '0':
            filters.append(('contains_audit', '=', context['audit']))
        if context['invoice'] != '0':
            filters.append(('invoice_state', '=', context['invoice']))
    filters.append(('partner_id', '=', int(pid)))
    fields = ['date_done', 'origin', 'invoice_state', 'state', 'partner_id', 'move_lines', 'contains_audit',
              'location_dest_id']
    try:
        pickings = do_search_read(req, 'stock.picking.in', fields, 0, False, filters, None)
        for picking in pickings['records']:
            picking['location_dest_id'] = str(picking['location_dest_id'][1]).split('/')[1]
    except Exception:
        _logger.debug('<get_stock_pickings> No stock.picking.in instances found for partner ID: %s', pid)

    if not pickings:
        raise Exception("AccessDenied")

    return pickings


def get_stock_picking_by_number(req, pid):
    """
    search by packaging slip number
    :param req:
    :param pid:
    :param picking_id:
    :return: search result of matched packaging slips
    """
    picking_no = req.context['picking_no']
    pickings = None
    fields = ['date_done', 'origin', 'invoice_state', 'state', 'partner_id', 'move_lines', 'contains_audit',
              'location_dest_id']
    try:
        pickings = do_search_read(req, 'stock.picking.in', fields, 0, False, [('origin', '=', picking_no)], None)
        for picking in pickings['records']:
            picking['location_dest_id'] = str(picking['location_dest_id'][1]).split('/')[1]
    except Exception:
        _logger.debug('<get_stock_pickings> No stock.picking.in instances found for No.: %s', picking_no)

    if not pickings:
        raise Exception("Access Denied")

    return pickings


def get_account_invoice(req, pid):
    """
    Search for invoices that marked as Manager Approved, Vendor Approved, Ready
    :param req: object
    :param pid: partner_id
    :return: search result of matched invoices
    """

    # get all paras and build filter
    year = req.context['year']
    month = req.context['month']
    state = req.context['state']
    filters = [('partner_id', '=', pid), ('date_invoice', 'like', '%(year)s-%(month)s-' % {'year': year, 'month': '%02d' % int(month)} + '%')]
    # if the vendor select 'vendor_approved' invoices, return invoices in ['vendor_approved', 'ready', 'sent']
    # and mask them as 'Vendor Approved' in the portal
    if state == '0':
        filters.append(('state', 'in', ['manager_approved', 'vendor_approved', 'vendor_denied', 'ready', 'sent']))
    elif state == 'vendor_approved':
        filters.append(('state', 'in', ['vendor_approved', 'ready', 'sent']))
    else:
        filters.append(('state', '=', state))

    invoices = None
    fields = ['name', 'number', 'date_invoice', 'state', 'partner_id', 'invoice_line', 'move_id', 'amount_untaxed',
              'amount_tax', 'amount_total', 'location_id', 'category_id']
    try:
        invoices = do_search_read(req, 'account.invoice', fields, 0, False, filters, None)
    except Exception:
        _logger.debug('<get_account_invoice> No account.invoice instances found for partner ID: %s', pid)

    if not invoices:
        raise Exception("AccessDenied")

    return invoices


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
        if format == formats[1]:  # Generate string comprised of random letters.
            allowed = string.ascii_letters
        elif format == formats[0]:  # Generate string comprised of random letters and numbers.
            allowed = string.hexdigits
        elif format == formats[2]:  # Generate string comprised of random numbers.
            allowed = string.digits

    else:
        raise TypeError

    return ''.join([allowed[random.randint(0, len(allowed) - 1)] for x in xrange(size)])


# -----------------------------------------------| VMI Session Object.
class Session(vmiweb.Controller):
    _cp_path = "/vmi/session"

    def session_info(self, req):
        """

        :param req:
        :return: a dict of all info about user-session
        """
        req.session.ensure_valid()
        uid = req.session._uid
        args = req.httprequest.args
        res = {}
        request_id = str(req.jsonrequest['id'])
        if request_id == 'VMI':  # Check to see if user is a VMI vendor
            try:  # Get Partner ID for session
                vendor = get_partner_id(req, uid)['records'][0]
            except Exception, e:
                _logger.debug('Partner not found for user ID: %s', uid)
                return {
                    'code': 400,
                    'message': "OpenERP WebClient Error",
                    'data': {
                        'type': 'Partner Not Found',
                        'text': 'No Partner found for this User ID!'
                    }
                }
            company = ""
            if vendor.has_key('company'):
                company = vendor['company']
            res = {
                "session_id": req.session_id,
                "uid": req.session._uid,
                "user_context": req.session.get_context() if req.session._uid else {},
                "username": req.session._login,
                "partner_id": vendor['partner_id'][0],
                "company": vendor['partner_id'][1],
                "company_id": vendor['company_id'],
            }
        else:  # Allow login for valid user without Vendor or Partner such as Admin or Manager
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
        # An RESTful API to check request and respond a session_id
        check = check_request(req, 'get_session_info')
        if check:
            return check
        else:
            return self.session_info(req)

    @vmiweb.jsonrequest
    def authenticate(self, req, login, password, base_location=None):
        """
        An RESTful API for vendor authentication
        :param req:
        :param login: username
        :param password: password
        :param base_location: an env var, None by default
        :return:
        """
        check = check_request(req, 'authenticate')
        if check:
            return check
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
    _default_stock_location_suffix = ' Stock'  # This must match the naming convention for locations inside OpenERP.
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

    def _get_stocks(self, req):
        """

        :param req:
        :param pid:
        :return:
        """
        return get_stocks(req, [])

    def _get_upload_history(self, req, pid):
        """
        Return the vendors packing slip submission history with associated moves details.
        @param req: object
        @param pid: partner_id
        @return: search result object
        """
        res = get_stock_pickings(req, pid)['records']

        #_logger.debug('_get_upload_history final result: %s', str(res))
        return res

    def _get_invoice(self, req, pid):
        """
        Return the Invoice that manager approved
        :param req: object
        :param pid: partner_id
        :return: search result object
        """
        return get_account_invoice(req, pid)['records']


    def _create_attachment(self, req, model, id, descr, ufile):
        """
        Create a attachment in openerp, based on the packaging slip file
        @param req:
        @param model:
        @param id:
        @param descr: description
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

    def _validate_products_old(self, req, csv_rows, pid):
        """
        validate products from csv file
        @param req: object
        @param csv_rows: list
        @param pid: partner id
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
            # _logger.debug('<_validate_products> Packing slip missing part numbers for partner: %s', str(pid))
            raise IndexError("<_validate_products> Product not found in (%r)!" % str(csv_part_numbers))
        else:
            unique_part_numbers = list(set(csv_part_numbers))
            try:
                res = do_search_read(req, 'product.product', fields, 0, False,
                                     [('default_code', 'in', unique_part_numbers)], None)
            except xmlrpclib.Fault, e:
                args.update({'error': e.faultCode})
                _logger.debug('<_validate_products> Error finding products in: %s', str(unique_part_numbers))
                return args

            if res is not None:
                for record in res['records']:
                    db_part_numbers.append(record['default_code'])
            else:
                raise IndexError("<_validate_products> No products returned from search: (%r)!" % str(res))

            # _logger.debug('<_validate_products> db_part_numbers: %s', db_part_numbers)
            #_logger.debug('<_validate_products> csv_part_numbers: %s', unique_part_numbers)
            if cmp(db_part_numbers.sort(), unique_part_numbers.sort()) == 0:
                results.update({'records': res['records'], 'length': len(res), 'valid': True})
            else:
                bad_products = [x for x in unique_part_numbers if x not in db_part_numbers]
                results.update({'records': bad_products, 'length': len(bad_products), 'valid': False})
                _logger.debug('<_validate_products> Invalid products found in packing slip: %s', str(bad_products))

        return results

    '''def _create_stock_picking(self, req, csv_rows, pid):
        """
        Create stock.picking.in instances for each unique packing slip # in the CSV file data.
        @param req: object
        @param csv_rows: list (each line of CSV file)
        @param pid: int
        @return: list
        """
        model_name = 'stock.picking.in'
        Model = req.session.model(model_name)
        destination_id = None
        location_id = None
        location_partner = None
        locations = get_stock_locations(req, pid)
        all_locations = []
        pickings = []
        res = []
        error = []
        if len(csv_rows) > 0:
            for row in csv_rows:  # Each unique packing slip number becomes a stock.picking.in instance.
                rnd = random_string(8, 'digits')
                vendor = str(row['supplier']).strip()
                try:
                    partner = get_vendor_by_name(req, vendor)['records'][0]
                except Exception, e:
                    error.append('Supplier')
                    return [{'error': (
                        error, 'Supplier does not exist for Packaging Slip: ' + row['packing_list_number'].strip())}]
                destination_name = str(row['destination']).strip() + self._default_stock_location_suffix
                try:
                    destination = get_stock_locations_by_name(req, pid, destination_name)
                    destination_id = destination['records'][0]['id']
                except Exception, e:
                    error.append('Destination')
                    return [{'error': (
                        error, 'Destination does not exist for Packaging Slip: ' + row['packing_list_number'].strip())}]
                location_name = str(row['supplier']).strip()
                try:
                    location = get_stock_locations_by_name(req, pid, location_name)
                    location_id = location['records'][0]['id']
                except Exception, e:
                    error.append('Destination')
                    return [{'error': (
                        error, 'Location does not exist for Packaging Slip: ' + row['packing_list_number'].strip())}]
                # if partner['id'] != pid: # Check if supplier is the same as current user's parent partner.
                #    _logger.debug('<_create_stock_picking> Supplier ID does not match PID: %s | %s', partner, pid)
                #    continue
                # Construct date from individual M D Y fields in CSV data.
                try:
                    datetime.datetime(int(str(row['year']).strip()), int(str(row['month']).strip()),
                                      int(str(row['day']).strip()))
                    delivery_date = str(row['year']).strip() + '/' + str(row['month']).strip() + '/' + str(
                        row['day']).strip()
                except Exception, e:
                    error.append('date')
                    return [
                        {'error': (error, 'Invalid date for Packaging Slip: ' + row['packing_list_number'].strip())}]
                pickings.append({
                    'name': row['packing_list_number'].strip() + '.' + delivery_date + '.' + rnd,
                    'date_done': delivery_date,
                    'min_date': delivery_date,
                    'partner_id': partner['id'],
                    'origin': row['packing_list_number'].strip(),
                    'location_id': location_id,
                    'location_dest_id': destination_id,
                    'note': row['purchase_order'].strip(),

                })
            if len(pickings) > 0:
                for picking in pickings:
                    picking_id = Model.create({
                                                  'name': picking['name'],
                                                  'date_done': picking['date_done'],
                                                  'min_date': picking['min_date'],
                                                  'partner_id': picking['partner_id'],
                                                  'origin': picking['origin'],
                                                  'invoice_state': '2binvoiced',
                                                  'state': 'done',
                                                  'contains_audit': 'no',
                                                  'location_id': picking['location_id'],
                                                  'location_dest_id': picking['location_dest_id'],
                                                  'note': picking['note'],

                                              }, req.context)
                    res.append({'picking_id': picking_id, 'packing_list': picking['origin'],
                                'partner': partner['id']})
                    # _logger.debug('<_create_stock_picking> picking_id: %s', res)

        return res'''

    def _create_move_line(self, req, line):
        """
        Create an OpenERP stock.move instance for each line item within the packing slip.
        @param req: object
        @param line: line from packing slip data
        @return: stock.move ID
        """
        moves = []
        model_name = 'stock.move'
        Model = req.session.model(model_name)
        if line:
            move_id = Model.create({
                            'product_id': line['product_id'],
                            'name': line['name'],
                            'product_uom': line['product_uom'],
                            'product_qty': line['product_qty'],
                            'location_dest_id': line['location_dest_id'],
                            'location_id': line['location_id'],
                            'partner_id': line['partner_id'],
                            'picking_id': line['picking_id'],
                            'vendor_id': line['vendor_id'],
                            'date_expected': line['date_expected'],
                            'scrapped': line['scrapped'],
                            'invoice_status': '2binvoiced'
                    })

        return move_id

    def _parse_packing_slip(self, req, src, pid):
        """
        main function to parse packaging slips from csv file
        :param req:
        :param src: data from csv file
        :param pid: vendor id
        :return: dict of parsed result
        """
        picking_model = req.session.model('stock.picking.in')
        result = {'stock_picking': [], 'move_lines': {'moves': []}}
        if src:
            # a dict stores created packing slips: stock.picking id
            created_slips = {}
            lines = []
            fmt = "%Y-%m-%d %H:%M:%S"
            # Validate and prepare each field in each line
            for record in src:
                packaging_slip = str(record['packing_list_number']).strip()
                product_number = str(record['septa_part_number']).strip()
                rnd = random_string(8, 'digits')
                error_msg = {'error': 'Invalid data on Part {0}, List {1}: '.format(product_number, packaging_slip)}

                # check supplier's name
                vendor = str(record['supplier']).strip()
                try:
                    partner = get_vendor_by_name(req, vendor)['records'][0]
                except Exception, e:
                    error_msg['error'] += 'Supplier {0} does not exist!'.format(vendor)
                    return error_msg

                # check destination
                destination_name = str(record['destination']).strip() + self._default_stock_location_suffix
                try:
                    destination = get_stock_locations_by_name(req, pid, destination_name)
                    destination_id = destination['records'][0]['id']
                except Exception, e:
                    error_msg['error'] += 'Destination {0} does not exist!'.format(destination_name)
                    return error_msg

                # check vendor's location
                location_name = str(record['supplier']).strip()
                try:
                    location = get_stock_locations_by_name(req, pid, location_name)
                    location_id = location['records'][0]['id']
                except Exception, e:
                    error_msg['error'] += 'Location {0} does not exist!'.format(location_name)
                    return error_msg

                # check delivery time
                # Construct date from individual M D Y fields in CSV data.
                # All data field are stored in UTC and displayed in system's timezone.
                # To avoid the timezone bug, convert time to UTC before write to database
                try:
                    naive_time = datetime(int(str(record['year']).strip()), int(str(record['month']).strip()), int(str(record['day']).strip()))
                    partner_tz = timezone(partner['tz'])
                    utc = timezone('UTC')
                    #localize naive time before converting to utc, this will avoid daylight saving issue
                    delivery_date_utc = partner_tz.localize(naive_time).astimezone(utc)
                except Exception, e:
                    error_msg['error'] += 'Invalid date!'
                    return error_msg

                # check product id
                try:
                    product = get_product_by_pn(req, product_number)
                    product_id = product['records'][0]['id']
                    product_uom = product['records'][0]['uom_id'][0]
                except Exception, e:
                    error_msg['error'] += 'Product {0} does not exist!'.format(product_number)
                    return error_msg

                # check product quantity, must > 0
                product_qty = float(record['quantity_shipped'].replace(',', ''))
                if product_qty < 1:
                    error_msg['error'] += 'Quantity Shipped is at least 1!'
                    return error_msg

                # generate a dict of all data in this line
                lines.append({'name': record['packing_list_number'].strip() + '.' + naive_time.strftime(fmt) + '.' + rnd,
                              'date_done': delivery_date_utc.strftime(fmt),
                              'min_date': delivery_date_utc.strftime(fmt),
                              'partner_id': partner['id'],
                              'origin': record['packing_list_number'].strip(),
                              'location_id': location_id,
                              'location_dest_id': destination_id,
                              'product_id': product_id,
                              'product_uom': product_uom,
                              'product_qty': product_qty,
                              'picking_id': None,
                              'vendor_id': pid,
                              'date_expected': delivery_date_utc.strftime(fmt),
                              'scrapped': False,
                              'note': '',
                })

            for line in lines:
                # Create stock.picking based on packaging slip number
                # New Picking
                if line['origin'] not in created_slips:
                    # create stock.picking
                    try:
                        picking_id = picking_model.create({'name': line['name'],
                                                       'date_done': line['date_done'],
                                                       'min_date': line['min_date'],
                                                       'partner_id': line['partner_id'],
                                                       'origin': line['origin'],
                                                       'invoice_state': '2binvoiced',
                                                       'state': 'done',
                                                       'contains_audit': 'no',
                                                       'location_id': line['location_id'],
                                                       'location_dest_id': line['location_dest_id'],
                                                       'note': line['note'],
                                                      }, req.context)
                    except Exception, except_osv:
                        #error = except_osv.faultCode.replace('\n', '')
                        _logger.debug('moves created failed: %s!', except_osv.faultCode)
                        error_msg['error'] += 'Fail to create picking slips: {0}'.format(except_osv.faultCode)
                        return error_msg
                    # create line
                    if picking_id:
                        created_slips[line['origin']] = picking_id
                        result['stock_picking'].append({'packing_list': line['origin'], 'picking_id': picking_id})
                        line['picking_id'] = picking_id
                        try:
                            move_id = self._create_move_line(req,line)
                        except Exception, e:
                            _logger.debug('moves created failed: %s!')
                # picking exists
                else:
                    # create line
                    line['picking_id'] = created_slips[line['origin']]
                    try:
                        move_id = self._create_move_line(req,line)
                    except Exception, e:
                        _logger.debug('move created failed: %s!', str(e))
                result['move_lines']['moves'].append(move_id)

        return result


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
        """
        Controller for VMI Home Page
        @param req: request object
        @param mod: mode selector (N, D, T)
        @param kwargs:
        @return: TAL Template
        """

        # check if session created
        # First time to this page, create a session
        if not kwargs:
            uid = newSession(req)
            _logger.debug('Session created')
        # logged in
        else:
            req.session.ensure_valid()
            uid = req.session._uid

        #compare session_id from request and from local
        params = dict(req.httprequest.args)
        temp_sid = ''
        if params.has_key('session_id'):
            temp_sid = params['session_id']
            _logger.debug('session_id from url is: %s', temp_sid)  #session_id from request
        _logger.debug('req.session_id is: %s', req.session_id)  #session_id from local

        # Get page from template
        if temp_sid and (temp_sid == req.session_id):
            page_name = 'main_menu'
        else:
            page_name = 'index'
        _logger.debug('page name is: %s', page_name)

        temp_globals = dict.fromkeys(self._template_keys, None)
        vmi_client_page = self._get_vmi_client_page(req, page_name)['records']

        if vmi_client_page:  # Set the mode for the controller and template.
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
        # javascript var
        js = 'var db = "%s"\n' % db
        js += 'var mode = "%s";\n' % mod

        temp_location = os.path.join(vmi_client_page[0]['template_path'], vmi_client_page[0]['template_name'])
        input = ''
        try:
            input = open(temp_location, 'r')
        except IOError, e:
            _logger.debug('opening the template file %s returned an error: %s, with message %s', e.filename, e.strerror,
                          e.message)
        finally:
            pass

        # If the template file not found or readable then redirect to error page.
        if not input:
            return req.not_found()

        template = simpleTAL.compileHTMLTemplate(input)
        input.close()

        context = simpleTALES.Context()
        # Add a string to the context under the variable title
        context.addGlobal("mode", mod)
        context.addGlobal("title", temp_globals['title'])
        context.addGlobal("script", js)
        context.addGlobal("header", temp_globals['header'])
        context.addGlobal("form_flag", temp_globals['form_flag'])
        context.addGlobal("form_action", temp_globals['form_action'])
        context.addGlobal("form_legend", temp_globals['form_legend'])

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
        # get session info and make sure user logged in.
        req.session.ensure_valid()
        uid = req.session._uid
        vendor_record = get_partner_id(req, uid)['records'][0]

        # Get page template
        page_name = 'upload'
        temp_globals = dict.fromkeys(self._template_keys, None)
        vmi_client_page = self._get_vmi_client_page(req, page_name)['records']
        if vmi_client_page:  # Set the mode for the controller and template.
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
            _logger.debug('opening the template file %s returned an error: %s, with message %s', e.filename, e.strerror,
                          e.message)
        finally:
            pass

        # If the template file not found or readable then redirect to error page.
        if not input:
            return req.not_found()

        template = simpleTAL.compileHTMLTemplate(input)
        input.close()
        sid = req.session_id
        pid = vendor_record['company_id']
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

        # get session info and make sure user logged in.
        uid = req.session._uid
        pid = None
        local_vals = {}
        if kwargs is not None:
            local_vals.update(kwargs)
            pid = local_vals.get('pid')
            _logger.debug('Partner found ID: %s', pid)
        else:
            try:  # Get Partner ID for session
                vendor_record = get_partner_id(req, uid)['records'][0]
                pid = vendor_record['company_id']
            except IndexError:
                _logger.debug('Partner not found for user ID: %s', uid)
                return {'error': _('No Partner found for this User ID!'), 'title': _('Partner Not Found')}

        page_name = 'result'
        temp_globals = dict.fromkeys(self._template_keys, None)
        vmi_client_page = self._get_vmi_client_page(req, page_name)['records']
        if vmi_client_page:  # Set the mode for the controller and template.
            for key in temp_globals:
                temp_globals[key] = vmi_client_page[0][key]
        else:
            _logger.debug('No vmi.client.page record found for page name %s!', page_name)
            return req.not_found()

        temp_location = os.path.join(vmi_client_page[0]['template_path'], vmi_client_page[0]['template_name'])
        input = ''
        try:
            input = open(temp_location, 'r')
        except IOError, e:
            _logger.debug('opening the template file %s returned an error: %s, with message %s', e.filename, e.strerror,
                          e.message)
        finally:
            pass

        # If the template file not found or readable then redirect to error page.
        if not input:
            _logger.debug('No template found for page name %s!', page_name)
            return req.not_found()

        template = simpleTAL.compileHTMLTemplate(input)
        input.close()

        #Get all warehouses and converted to javascript
        stocks = simplejson.dumps(self._get_stocks(req))
        js = 'var stocks = %s;\n' % stocks
        js += 'var mode = "%s";\n' % mod
        sid = req.session_id
        context = simpleTALES.Context()
        if 'audit_result' in local_vals:  # Append the result of audit flagging.
            js += 'var audit = "%s";\n' % simplejson.dumps(local_vals['audit_result'])
            context.addGlobal("audit_result", local_vals['audit_result'])
        if 'error' in local_vals:  # Append errors generated by the parsing of the file.
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
    def invoice(self, req, mod=None, **kwargs):
        """
        Controller for VMI Packing Slip Upload Page
        @param req: request object
        @param mod: mode selector (N, D, T)
        @param kwargs:
        @return: TAL Template
        """

        # get session info and make sure user logged in.
        if mod is not None:
            if mod not in self._modes:
                raise KeyError
        uid = req.session._uid
        local_vals = {}
        if kwargs is not None:
            local_vals.update(kwargs)
            pid = local_vals.get('company_id')
            _logger.debug('Partner found ID: %s', pid)
        else:
            try:  # Get Partner ID for session
                vendor_record = get_partner_id(req, uid)['records'][0]
                pid = vendor_record['company_id']
            except IndexError:
                _logger.debug('Partner not found for user ID: %s', uid)
                return {'error': _('No Partner found for this User ID!'), 'title': _('Partner Not Found')}

        page_name = 'invoice'
        req.session.ensure_valid()
        temp_globals = dict.fromkeys(self._template_keys, None)
        vmi_client_page = self._get_vmi_client_page(req, page_name)['records']

        if vmi_client_page:  # Set the mode for the controller and template.
            for key in temp_globals:
                temp_globals[key] = vmi_client_page[0][key]

            if mod is None:
                mod = vmi_client_page[0]['mode']
        else:
            _logger.debug('No vmi.client.page record found for page name %s!', page_name)
            return req.not_found()

        temp_location = os.path.join(vmi_client_page[0]['template_path'], vmi_client_page[0]['template_name'])
        input = ''
        try:
            input = open(temp_location, 'r')
        except IOError, e:
            _logger.debug('opening the template file %s returned an error: %s, with message %s', e.filename, e.strerror,
                          e.message)
        finally:
            pass

        # If the template file not found or readable then redirect to error page.
        if not input:
            return req.not_found()

        template = simpleTAL.compileHTMLTemplate(input)
        input.close()

        # Get the invoices and converted to javascript
        # invoice = simplejson.dumps(self._get_invoice(req, pid))
        # js = 'var invoice_data = %s;\n' % invoice
        js = 'var mode = "%s";\n' % mod
        sid = req.session_id
        context = simpleTALES.Context()

        # Add a string to the context under the variable title
        if 'error' in local_vals:  # Append errors generated by the parsing of the file.
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


    '''@vmiweb.httprequest
    def upload_document(self, req, pid, uid, contents_length, callback, ufile):

        """
        This function is replaced by upload_file to upload the packaging slip data.
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
        req.session.ensure_valid()

        mod = None
        args = {}
        args.update({'pid': pid})
        args.update({'uid': uid})
        #uid = newSession(req)
        uid = req.session._uid
        uname = req.session._login
        upwd = req.session._password
        udb = req.session._db
        _logger.debug('This is uid %s!', str(uid))
        vmi_client_page = self._get_vmi_client_page(req, page_name)['records']
        if vmi_client_page:  # Set the mode for the controller and template.
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
        uid = req.session._uid
        _logger.debug('<upload_document2>This is uid %s!', str(uid))
        if contents_length:
            if ufile:
                result = None
                #import pdb; pdb.set_trace()
                try:
                    result = self._parse_packing_slip(req, ufile, pid)  # Parse CSV file contents.
                except Exception, e:
                    args.update({'error': str(e)})
                    _logger.debug('<upload_document>_parse_packing_slip failed: %s!', str(e))
                    _logger.debug('Error on line %s', sys.exc_traceback.tb_lineno)

                args.update({'parse_result': result})
                # Session flashed after parse packing slip, need to revalidation
                req.session.authenticate(udb, uname, upwd)
            else:
                args.update({'error': 'File is empty or invalid!'})

        if 'error' not in args:
            result = None
            vals = args.copy()
            vals['pid'] = pid
            try:
                result = self._call_methods(req, 'stock.move', 'action_flag_audit', [vals, None])  # Flag audits.
            except Exception, e:
                args.update({'error': str(e)})
                _logger.debug('<upload_document>_call_methods failed: %s!', str(e))

            args.update({'audit_result': result})
        #_logger.debug('<upload_document> args after flag: %s!', args)
        if 'audit_result' in args:  # Call the Done method on moves that weren't flagged for audit.

            if 'move_lines' in args['parse_result']:
                result = None
                moves = args['parse_result']['move_lines']
                unflagged = []
                for move in moves['moves']:
                    if move not in args['audit_result']:
                        unflagged.append(move)

                try:
                    #rewrite function: action_done
                    result = self._call_methods(req, 'stock.move', 'action_done', [unflagged, None])
                    pass
                except Exception, e:
                    args.update({'error': str(e)})
                    _logger.debug('<upload_document>_call_methods failed: %s!', str(e))

                    #_logger.debug('<upload_document>unflagged moves set to done: %s!', str(unflagged))

        _logger.debug('<upload_document3>This is uid %s!', str(uid))
        req.session.ensure_valid()
        kwargs = args.copy()
        return self.result(req, mod, **kwargs)'''


    @vmiweb.httprequest
    def products(self, req, mod=None, **kwargs):
        """
        Product search page
        :param req: request object
        :param mod: mode selector (N, D, T)
        :param kwargs:
        :return: product page
        """
        # get session info and make sure user logged in.
        if mod is not None:
            if mod not in self._modes:
                raise KeyError
        uid = req.session._uid
        local_vals = {}
        if kwargs is not None:
            local_vals.update(kwargs)
            pid = local_vals.get('pid')
            _logger.debug('Partner found ID: %s', pid)
        else:
            try:  # Get Partner ID for session
                vendor_record = get_partner_id(req, uid)['records'][0]
                pid = vendor_record['company_id']
            except IndexError:
                _logger.debug('Partner not found for user ID: %s', uid)
                return {'error': _('No Partner found for this User ID!'), 'title': _('Partner Not Found')}

        page_name = 'products'
        temp_globals = dict.fromkeys(self._template_keys, None)
        vmi_client_page = self._get_vmi_client_page(req, page_name)['records']
        if vmi_client_page:  # Set the mode for the controller and template.
            for key in temp_globals:
                temp_globals[key] = vmi_client_page[0][key]
        else:
            _logger.debug('No vmi.client.page record found for page name %s!', page_name)
            return req.not_found()

        temp_location = os.path.join(vmi_client_page[0]['template_path'], vmi_client_page[0]['template_name'])
        input = ''
        try:
            input = open(temp_location, 'r')
        except IOError, e:
            _logger.debug('opening the template file %s returned an error: %s, with message %s', e.filename, e.strerror,
                          e.message)
        finally:
            pass

        # If the template file not found or readable then redirect to error page.
        if not input:
            _logger.debug('No template found for page name %s!', page_name)
            return req.not_found()

        template = simpleTAL.compileHTMLTemplate(input)
        input.close()

        js = 'var mode = "%s";\n' % mod
        search_result = simplejson.dumps(None)
        js += 'var search_result = "%s";\n' % search_result
        sid = req.session_id
        context = simpleTALES.Context()
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
    def invoice_processing(self, req, uid, company_id, callback, invoice_id, comment, result):

        """
        An old way to process the invoice, like function upload_document
        :param req: object
        :param uid: user id
        :param company_id: partner id
        :param callback:
        :param invoice_id: invoice id that need to be processed
        :param comment: a comment that explained why vendor denied the current invoice
        :param result: vendor's decision on current invoice
        :return:
        """
        page_name = 'invoice_processing'
        # session_data = Session.session_info(req.session)
        req.session.ensure_valid()

        mod = None
        args = {}
        args.update({'company_id': company_id})
        args.update({'uid': uid})
        #uid = req.session._uid
        _logger.debug('This is uid %s!', str(uid))
        vmi_client_page = self._get_vmi_client_page(req, page_name)['records']
        if vmi_client_page:  # Set the mode for the controller and template.
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
                _logger.debug('<invoice_processing>The mode is not set to a recognized value: %s!', str(mod))
                raise KeyError
                #            else:
                #                args.update({'mod': mod})

        req.session.ensure_valid()
        uid = req.session._uid
        if invoice_id:
            res = None
            ids = invoice_id
            # invoice processing
            if result == "approved":
                res = self._call_methods(req, 'account.invoice', 'invoice_vendor_approve', [ids, None])
            elif result == "denied":
                res = self._call_methods(req, 'account.invoice', 'invoice_vendor_deny', [ids, {'comment': comment}])
            else:
                _logger.debug('<invoice_processing>Unrecognized action!')
                raise KeyError

        kwargs = args.copy()
        return self.invoice(req, mod, **kwargs)

    @vmiweb.jsonrequest
    def upload_file(self, req, company_id, data):
        """
        A RESTful API to upload the csv file
        :param req:
        :param company_id: Vendor's id
        :param data: csv data
        :return: pass or fail, if fail return error message
        """

        args = {}
        if len(data) > 0:
            try:
                result = self._parse_packing_slip(req, data, company_id)
            except Exception, e:
                args.update({'error': str(e)})
                _logger.debug('Error on line %s', sys.exc_traceback.tb_lineno)
            if 'error' in result:
                return {
                    'code': 400,
                    'message': "OpenERP WebClient Error",
                    'data': {
                        'type': 'Invalid Data',
                        'text': result['error'],
                    }
                }
            else:
                args.update({'parse_result': result})
        else:
            args.update({'error': 'File is empty or invalid!'})

        # successfully parsed, flag the item to be audited
        if 'error' not in args:
            result = None
            vals = args.copy()
            vals['pid'] = company_id
            try:
                result = self._call_methods(req, 'stock.move', 'action_flag_audit', [vals, None])  # Flag audits.
            except Exception, e:
                args.update({'error': str(e)})
                _logger.debug('<upload_file>_call_methods failed: %s!', str(e))

            args.update({'audit_result': result})

        # Call the Done method on moves that weren't flagged for audit.
        if 'audit_result' in args:

            if 'move_lines' in args['parse_result']:
                result = None
                moves = args['parse_result']['move_lines']
                unflagged = []
                for move in moves['moves']:
                    if move not in args['audit_result']:
                        unflagged.append(move)
                try:
                    # rewrite function: action_done
                    result = self._call_methods(req, 'stock.move', 'action_done', [unflagged, None])
                    pass
                except Exception, e:
                    args.update({'error': str(e)})
                    _logger.debug('<upload_file>_call_methods failed: %s!', str(e))
        return args

    @vmiweb.jsonrequest
    def get_invoices(self, req, company_id):
        """
        Return the Invoice that manager approved, Not being used
        :param req: object
        :param pid: partner_id
        :return: search result object
        """
        return get_account_invoice(req, int(company_id))['records']

    @vmiweb.jsonrequest
    def process_invoice(self, req, ids, company_id, decision, comment):
        """
        A RESTful API to process invoice.
        :param req:
        :param ids: invoice id
        :param company_id: Vendor id
        :param decision: pass or fail
        :param comment: Fail reason
        :return: Pass or Fail
        """
        if decision == 'true':
            res = self._call_methods(req, 'account.invoice', 'invoice_vendor_approve', [int(ids), None])
        else:
            res = self._call_methods(req, 'account.invoice', 'invoice_vendor_deny', [int(ids), {'comment': comment}])
        return res

    @vmiweb.jsonrequest
    def get_invoice_lines(self, req, ids, uid):
        """
        function to process invoice lines searching when detail button clicked on invoice page.
        :param req:
        :param ids:
        :param uid:
        :return:
        """
        ids = [int(n) for n in ids.split(",")]
        return get_invoice_line(req, ids, uid)

    @vmiweb.jsonrequest
    def get_move_lines(self, req, ids):
        """
        function to process move lines searching when detail button clicked on review page.
        :param req:
        :param ids:
        :param uid:
        :return:
        """
        ids = [int(n) for n in ids.split(",")]
        return get_stock_moves_by_id(req, ids)

    @vmiweb.jsonrequest
    def get_upload_history(self, req, company_id):
        """
        function to process picking slip searching
        :param req:
        :param ids:
        :param uid:
        :return:
        """

        return get_stock_pickings(req, company_id)

    @vmiweb.jsonrequest
    def get_picking_no(self, req, company_id):
        """

        :param req:
        :param company_id:
        :return:
        """
        return get_stock_picking_by_number(req, company_id)

    @vmiweb.jsonrequest
    def get_product(self, req, company_id):
        """

        :param req:
        :param company_id:
        :return:
        """
        septa = {}
        vendor = {}
        result = {}

        # read user input to decide which part numbers should be used
        if req.context['septa_pn'] != '':
            septa = search_products_by_septa_pn(req, req.context['septa_pn'])
        if req.context['vendor_pn'] != '':
            vendor = search_products_by_vendor_pn(req, req.context['vendor_pn'])

        # get all missing parts if exists
        if 'missing_septa_pn' in septa:
            result['missing_septa_pn'] = septa['missing_septa_pn']
        if 'missing_vendor_pn' in vendor:
            result['missing_vendor_pn'] = vendor['missing_vendor_pn']

        # merge all found parts and remove duplicates
        result['records'] = septa.get('records', []) + vendor.get('records', [])
        part_numbers = []
        id_to_remove = []
        for i in xrange(len(result['records'])):
            if result['records'][i]['default_code'] in part_numbers:
                id_to_remove.append(i)
        for j in id_to_remove:
            del result['records'][j]

        return result