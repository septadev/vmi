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

def get_client_page(page):
    return True


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

    def _get_vmi_client_page(self, page):

        return get_client_page(page)

    def _create_attachment(self, req, model, id, descr, ufile):
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
        res = {}
        results = {}
        prod_list = []
        fields = ['id', 'default_code', 'uom_id']
        default_codes = []
        for row in csv_rows:
            prod_list.append(row['septa_part_number'].strip())

        if len(prod_list) == 0:
            _logger.debug('<_validate_products> Packing slip missing part numbers for partner: %s', str(pid))
            raise IndexError("<_validate_products> Product not found in (%r)!" % str(prod_list))
        else:
            #try:
            res = do_search_read(req, 'product.product', fields, 0, False, [('default_code', 'in', prod_list)], None)
            #except Exception:
            _logger.debug('<_validate_products> Error finding products in: %s', res['records'])

            if res is not None:
                for record in res['records']:
                    default_codes.append(record['default_code'])
            else:
                raise IndexError("<_validate_products> No products returned from search: (%r)!" % str(res))

            _logger.debug('<_validate_products> default_codes: %s', default_codes)
            _logger.debug('<_validate_products> prod_list: %s', prod_list)
            if cmp(default_codes, prod_list) == 0:
                results.update({'records': res['records'], 'length': len(res), 'valid': True})
            else:
                bad_products = [x for x in prod_list if x not in default_codes]
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
        model_name = 'stock.picking.in'
        Model = req.session.model(model_name)
        res = []
        if len(csv_rows) > 0:
            for row in csv_rows:
                rnd = random_string(8, 'hex')
                delivery_date = str(row['year']).strip() + '/' + str(row['month']).strip() + '/' + str(
                    row['day']).strip()
                #_logger.debug('<_create_stock_picking> CSV file: %s', str(row))
                picking_id = Model.create({
                                          'name': row['packing_list_number'].strip() + '.' + delivery_date + '.' + rnd,
                                          'date': delivery_date,
                                          'partner_id': pid,
                                          'origin': row['packing_list_number'].strip(),
                                          'invoice_state': 'none',
                                          'note': row['purchase_order'].strip()
                                          }, req.context)
                res.append({'picking_id': picking_id, 'packing_list': row['packing_list_number'].strip()})

        return res

    def _create_move_line(self, req, csv_rows, pid):
        moves = []
        model_name = 'stock.move'
        Model = req.session.model(model_name)
        location_id = None
        location_partner = None
        locations = get_stock_locations(req, pid)
        products = self._validate_products(req, csv_rows, pid)
        if len(csv_rows) > 0 and products['valid']:
            product = None
            for csv_row in csv_rows:
                for prod in products['records']:
                    _logger.debug('<_create_move_line> Current product: %s', prod['default_code'])
                if prod['default_code'] == csv_row['septa_part_number'].strip():
                    product = prod
                    break

                for location in locations['records']:
                    if location['name'] == str(csv_row['destination']).strip():
                        location_id = location['id']
                        location_partner = location['partner_id'][0]
                        _logger.debug('<_create_move_line> location: %s', str(location_id))
                        break

                if not location_id:
                    raise ValueError(
                        "(%r) is not a proper value for destination location!" % str(csv_row['destination']))
                delivery_date = str(csv_row['year']).strip() + '/' + str(csv_row['month']).strip() + '/' + str(
                    csv_row['day']).strip()
                move_id = Model.create({
                'product_id': product['id'],
                'name': csv_row['packing_list_number'].strip() + '|' + delivery_date,
                'product_uom': product['uom_id'][0],
                'product_qty': float(csv_row['quantity_shipped']),
                'location_dest_id': location_id,
                'location_id': 8,
                'partner_id': location_partner,
                'picking_id': csv_row['picking_id'],
                'date': delivery_date,
                })
                moves.append(move_id)

        else:
            _logger.debug('<_create_move_line> Moves not created due to bad products: %s', products['records'])

        return moves


    def _parse_packing_slip(self, req, filedata, pid):
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

        return True

    @vmiweb.httprequest
    def index(self, req, mod=None, **kwargs):
        vmi_client_page = self._get_vmi_client_page('index')
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
        input = open(
            '/home/amir/dev/parts/openerp-7.0-20131118-002448/openerp/addons/vmi/vmi_web/template/index.html', 'r')
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
    def packing_slip(self, req, mod=None, **kwargs):
        vmi_client_page = self._get_vmi_client_page('upload')
        js = 'var csvFields = new Array%s;' str(self._packing_slip_fields)
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
        vmi_client_page = self._get_vmi_client_page('invoice')
        input = open(
            '/home/amir/dev/parts/openerp-7.0-20131118-002448/openerp/addons/vmi/vmi_web/template/vmi_invoice.html', 'r')
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
        vmi_client_page = self._get_vmi_client_page('upload')
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
        #try:
            picking_id = self._parse_packing_slip(req, ufile, pid)
            #except Exception, e:
            #	args = {'error': e.message}

            input = open(
                '/home/amir/dev/parts/openerp-7.0-20131118-002448/openerp/addons/vmi/vmi_web/template/upload.html', 'r')


        template = simpleTAL.compileHTMLTemplate(input)
        input.close()
        context = simpleTALES.Context()

        #try:
        #attachment_id = Model.create(parsedata, req.context)
        #except xmlrpclib.Fault, e:
        #args = {'error':e.faultCode }
        #if args['error']:
        #	form_flag = False
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

