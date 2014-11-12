import logging
from openerp.osv import osv
from openerp.osv import fields
from openerp import SUPERUSER_ID
from openerp import pooler, tools, netsvc
from openerp.tools.translate import _
import openerp.addons.decimal_precision as dp
import time
import datetime
import functools

_logger = logging.getLogger(__name__)


class vmi_client_page(osv.osv):
    """object to hold dynamic values inserted into client side templates"""
    _name = 'vmi.client.page'
    _table = 'vmi_client_pages'
    _description = 'VMI Client Page'
    _log_access = True

    _columns = {
        'name': fields.char('Name', size=128, translate=False, required=True, readonly=False),
        'title': fields.char('Title', size=128, translate=False, required=True, readonly=False),
        'header': fields.text('Header'),
        'form_action': fields.char('Form Action', size=64, translate=False, required=True, readonly=False),
        'form_flag': fields.boolean('Enable Forms'),
        'form_legend': fields.char('Form Legend', size=64, translate=False, required=True, readonly=False),
        'template_path': fields.char('Path To Template', size=357, translate=False, required=True, readonly=False),
        'template_name': fields.char('Template Name', size=128, translate=False, required=True, readonly=False),
        'mode': fields.selection([('N', 'Normal'), ('D', 'Debug'), ('T', 'Test')], 'Mode',
                                 help="Select the mode for this controller."),
        'active': fields.boolean('Enable Controller'),
        'write_date': fields.date('Last Update', required=False, readonly=True),
        'write_uid': fields.many2one('res.users', 'Updated', readonly=True),

    }
    _defaults = {
        'active': lambda *a: True,
        'mode': lambda *a: "N",
        'form_flag': lambda *a: True,
    }


class vmi_product(osv.osv):
    """Override of product.product"""
    _name = 'product.product'
    _inherit = 'product.product'
    _columns = {
        'vendor_part_number': fields.char('Vendor P/N', size=128, translate=False, required=False, readonly=False,
                                          select=True),
        'default_code': fields.char('SEPTA P/N', size=64, translate=False, required=False, readonly=False, select=True),
    }


class vmi_stock_move(osv.osv):
    """Override of stock.move"""
    _name = 'stock.move'
    _inherit = 'stock.move'
    _columns = {
        'vendor_id': fields.many2one('res.partner', 'Vendor', required=False, readonly=True),
        'audit': fields.boolean('Audit'),
        'audit_fail': fields.boolean('Failed Audit'),
        #'scrapped': fields.related('location_dest_id', 'scrap_location', type='boolean', relation='stock.location',
                                   #string='Scrapped', readonly=False),
    }
    _defaults = {
        'audit': False,
        'audit_fail': False,
        'scrapped': False,
    }

    def _default_destination_address(self, cr, uid, context=None):
        res = None
        user = self.pool.get('res.users').browse(cr, uid, uid, context=context)
        partner = self.pool.get('res.partner').browse(cr, uid, user.company_id.partner_id.id, context=context)
        if partner.is_company and partner.customer:
            res = user.company_id.partner_id.id
        elif partner.is_company and partner.supplier:
            res = self._default_location_destination
        else:
            res = partner.parent_id or None

        if res is None:
            res = uid

        return res

    def flag_for_audit(self, cr, uid, ids, vals=[], context=None):
        return self.write(cr, uid, ids, {'audit': True}, context=context)

    def unflag_for_audit(self, cr, uid, ids, vals=[], context=None):
        return self.write(cr, uid, ids, {'audit': False}, context=context)

    def flag_fail_audit(self, cr, uid, ids, vals, context=None):
        return self.write(cr, uid, ids, {'audit_fail': True}, context=context)

    def action_audit(self, cr, uid, ids, quantity, location, context=None):
        if context is None:
            context = {}
        # audit quantity should be less than or equal to shipped quant.
        if quantity <= 0:
            raise osv.except_osv(_('Warning!'), _('Please provide a positive quantity.'))
        res = []
        user_obj = self.pool.get('res.users')
        storekeeper = user_obj.browse(cr, uid, uid).login
        note = "Audit conducted at %s by %s." % (str(time.strftime('%Y-%m-%d %H:%M:%S')), storekeeper.capitalize())
        for move in self.browse(cr, uid, ids, context=context):
            move_qty = move.product_qty
            uos_qty = quantity / move_qty * move.product_uos_qty
            if move_qty != quantity:
                difference_quant = move_qty - quantity
                difference_uos = difference_quant * move.product_uos_qty
                default_val = {
                    'product_qty': difference_quant,
                    'product_uos_qty': difference_uos,
                    'state': move.state,
                    'scrapped': False,
                    'audit': False,
                    'audit_fail': True,
                    'tracking_id': move.tracking_id.id,
                    'prodlot_id': move.prodlot_id.id,
                    'location_dest_id': location,
                    'note': note,
                }
                new_move = self.copy(cr, uid, move.id, default_val)
                self.write(cr, uid, ids, {'product_qty': quantity, 'note': note}, context)
                self.action_done(cr, uid, ids, context)
                res += [new_move]
                note += " On stock.move ID %d" % move.id
                _logger.debug('<action_audit> %s', note)
                product_obj = self.pool.get('product.product')
                for product in product_obj.browse(cr, uid, [move.product_id.id], context=context):
                    if move.picking_id:
                        uom = product.uom_id.name if product.uom_id else ''
                        message = _("%s %s %s has been moved to <b>Failed Audits</b>.") % (quantity, uom, product.name)
                        move.picking_id.message_post(body=message)

            else:
                move.unflag_for_audit()
                move.action_done()

        #self.unflag_for_audit(cr, uid, ids, [], context)
        #self.action_done(cr, uid, res, context)
        return res

    def action_done(self, cr, uid, unflagged, context=None):

        """
        args.parse_result:
        {'stock_pickings': [{'picking_id': picking_id, 'packing_list': packing_list_number}],
         'move_lines': {'moves': [id], 'locations', [id]
         'pid': id}
        @param self:
        @param cr:
        @param user:
        @param unflagged:
        @param context:
        """

        #_logger.debug('<action_done> unflagged: %s', unflagged)
        ids = ', '.join(str(x) for x in unflagged)
        if len(unflagged) > 0:
            update_sql = """
                UPDATE
                    stock_move
                SET
                    state = 'done'
                WHERE
                    id in (%s);
                """ % ids
            cr.execute(update_sql)

        return True

class vmi_stock_picking_in(osv.osv):
    """Override of stock.picking.in"""
    _name = 'stock.picking.in'
    _inherit = 'stock.picking.in'
    _table = "stock_picking"
    _order = 'date desc'

    '''def _flag_next_audit(self, cr, uid, ids, last_audited, partner, location, context):
        """
        audit flagging mechanism

        @param cr:
        @param uid:
        @param ids:
        @param last_audited:
        @param partner:
        @param location:
        @param context:
        @return: list
        """
        if context is None:
            context = {}
        res = []
        i = 1
        date_format = "%Y-%m-%d %H:%M:%S"
        now = datetime.datetime.now()
        # add condition id > last_audited['id'], and order by id ASC
        sql_req = """
			select 
			m.id
			,m.date 
			from 
			stock_move m
			where 
			(m.location_dest_id = %s)
			and 
			(m.vendor_id = %s)
			and
			 (m.date between '%s' and '%s')
			and
			(m.id >= %s)
			order by m.id ASC;
			""" % (location, partner, last_audited['date'], now.strftime(date_format), last_audited['id'])
        cr.execute(sql_req)
        sql_res = cr.dictfetchall()
        if len(sql_res) > 0:
            while i < len(sql_res):

                if i % 10 == 0:
                    res.append(sql_res[i]['id'])
                    _logger.debug('<_flag_next_audit> This is %s th product from last audit: %s', i, str(sql_res[i]['id']))
                i += 1

            if res:
                vals = ', '.join(str(x) for x in res)
                _logger.debug('<_flag_next_audit> vals: %s', str(vals))
                update_sql = """
                     update
                       stock_move
                     set
                       audit = True
                     where
                       id in (%s);
                    """ % vals
                cr.execute(update_sql)

        return res'''


    '''def _get_last_audited(self, cr, uid, ids, partner, location, context):
        """
        Retrieve the most recently audited moves for this location and vendor
        @param self:
        @param cr:
        @param uid:
        @param ids:
        @param partner:
        @param location:
        @param context:
        @return:
        """
        if context is None:
            context = {}
        res = []
        last_audited = None
        # import pdb; pdb.set_trace()
        if partner and location:
            sql_req = """
                SELECT
                m.id
                ,m.date
                FROM
                stock_move m
                WHERE
                m.audit = TRUE
                AND
                (m.location_dest_id = %s)
                AND
                (m.vendor_id = %s)
                ORDER BY date DESC LIMIT 1;
                """ % (location, partner)

            cr.execute(sql_req)
            sql_res = cr.dictfetchone()
            if sql_res:
                res.append({'id': sql_res['id'], 'date': sql_res['date']})
                _logger.debug('<_get_last_audited> last audit found: %s : %s : %s', str(sql_res), str(location), str(partner))

            sql_req = """
                select
                m.id
                ,m.date
                from
                stock_move m
                where
                m.audit_fail = True
                and
                (m.location_dest_id = %s)
                and
                (m.vendor_id = %s)
                order by date DESC limit 1;
                """ % (location, partner)

            cr.execute(sql_req)
            sql_res = cr.dictfetchone()
            if sql_res:
                res.append({'id': sql_res['id'], 'date': sql_res['date']})
                _logger.debug('<_get_last_audited> last audit_fail found: %s : %s : %s', str(sql_res), str(location), str(partner))

            if len(res) > 0:
                if len(res) > 1:
                    if res[0]['date'].date() < res[1]['date'].date():
                        last_audited = res.pop(1)
                    else:
                        last_audited = res.pop(0)
                else:
                    last_audited = res.pop(0)

        _logger.debug('<_get_last_audited> %s : %s : %s', str(last_audited), str(location), str(partner))
        return last_audited'''

    '''def _flag_first_audit(self, cr, user, partner, location, context):
        """
        Method to begin auditing by selecting the 1st appropriate move record matching
        partner and location criteria and setting the audit flag.
        @param user:
        @param pid:
        @param location:
        @param context:
        """
        if context is None:
            context = {}
        result = []
        # Select the oldest record matching the criteria and flag it.
        if partner and location:
            sql_req = """
                SELECT
                m.id
                ,m.date
                FROM
                stock_move m
                WHERE
                m.audit = FALSE
                AND
                (m.location_dest_id = %s)
                AND
                (m.vendor_id = %s)
                AND
                (m.state != 'done')
                ORDER BY date ASC LIMIT 1;
                """ % (location, partner)
            cr.execute(sql_req)
            sql_res = cr.dictfetchone()
            if sql_res:  # Set the audit flag for move record obtained.
                result.append(sql_res['id'])
                update_sql = """
                     update
                       stock_move
                     set
                       audit = True
                     where
                       id = (%s);
                    """ % result[0]
                cr.execute(update_sql)
                _logger.debug('<_flag_first_audit> First audit flagged: %s', str(result[0]))

        if not result:
            _logger.debug('<_flag_first_audit> No move records matching criteria exist: %s, %s', str(partner),
                          str(location))

        return result'''

        #add attr to vendor in database:
        # mobile: number of product need to be audited
        # birthdate: last record before upload

    def action_flag_audit(self, cr, user, vals, context=None):

        """
        args.parse_result:
        {'stock_pickings': [{'picking_id': picking_id, 'packing_list': packing_list_number}],
         'move_lines': {'moves': [id], 'locations', [id]
         'pid': id}
        @param self:
        @param cr:
        @param user:
        @param vals:
        @param context:
        """

        #_logger.debug('<action_flag_audit> vals: %s', vals)
        result = []
        i = 0
        if 'pid' in vals:
            pid = vals.get('pid')
            #get remained_audit and last record
            sql_req = """
                SELECT
                    p.mobile
                    ,p.birthdate
                FROM
                    res_partner p
                WHERE
                    id = (%s);
            """ % pid
            try:
                cr.execute(sql_req)
            except Exception:
                _logger.debug('<action_flag_audit> Unable to get remained_audit and last_record')
            sql_res = cr.dictfetchone()
            remained_audit = int(sql_res['mobile'])
            last_record = int(sql_res['birthdate'])
            #_logger.debug('<action_flag_audit> remained_audit: %s , last_record: %s', remained_audit, last_record)
            if 'parse_result' in vals:
                p = vals.get('parse_result')
                #get newly uploaded record and order by the product quantity
                if 'move_lines' in p:
                    sql_req = """
                        SELECT
                            m.id
                            ,m.product_qty
                        FROM
                            stock_move m
                        WHERE
                            (m.vendor_id = %s)
                        AND
                            (m.id > %s)
                        ORDER BY m.product_qty DESC;
                    """% (pid, last_record)
                    cr.execute(sql_req)
                    sql_res = cr.dictfetchall()
                    #_logger.debug('<action_flag_audit> select result: %s', str(sql_res))
                    total_qty = sum(item['product_qty'] for item in sql_res)
                    #_logger.debug('<action_flag_audit> total_qty: %s', total_qty)
                    last_record = max(id['id'] for id in sql_res)

                    if sql_res > 0:
                        #calculate number of product to be flagged this time and get them
                        number_to_flag = int(round(total_qty * 0.1) + remained_audit)
                        #_logger.debug('<action_flag_audit> number_to_flag: %s', number_to_flag)
                        while i < len(sql_res) and number_to_flag > 0:
                            if sql_res[i]['product_qty'] <= number_to_flag:
                                result.append(sql_res[i]['id'])
                                #_logger.debug('<action_flag_audit> id to flag: %s', str(sql_res[i]['id']))
                                number_to_flag -= sql_res[i]['product_qty']
                            i += 1
                        #_logger.debug('<action_flag_audit> remained to be audited: %s', number_to_flag)

                        if result:
                            ids = ', '.join(str(x) for x in result)
                            #_logger.debug('<action_flag_audit> result to be audited: %s', str(ids))
                            #flagging
                            update_sql = """
                                UPDATE
                                    stock_move
                                SET
                                    audit = True
                                WHERE
                                    id in (%s);
                                """ % ids
                            cr.execute(update_sql)

                        #update remained_audited and last_record
                        update_sql = """
                            UPDATE
                                res_partner
                            SET
                                mobile = '%s'
                                , birthdate = '%s'
                            WHERE
                                id = %s;
                            """ % (remained_audit, last_record, pid)
                        cr.execute(update_sql)

        return result

    def create(self, cr, user, vals, context=None):
        if ('name' not in vals) or (vals.get('name') == '/'):
            seq_obj_name = self._name
            vals['name'] = self.pool.get('ir.sequence').get(cr, user, seq_obj_name)
        new_id = super(vmi_stock_picking_in, self).create(cr, user, vals, context)

        return new_id

    _defaults = {
        'invoice_state': '2binvoiced',
    }


vmi_stock_picking_in()


class vmi_move_consume(osv.osv_memory):
    _name = "vmi.move.consume"
    _description = "Consume Products"

    _columns = {
        'product_id': fields.many2one('product.product', 'Product', required=True, select=True),
        'product_qty': fields.float('Quantity', digits_compute=dp.get_precision('Product Unit of Measure'),
                                    required=True),
        'product_uom': fields.many2one('product.uom', 'Product Unit of Measure', required=True),
        'location_id': fields.many2one('stock.location', 'Location', required=True)
    }

    # TOFIX: product_uom should not have differemt category of default UOM of product. Qty should be convert into UOM of original move line before going in consume and scrap
    def default_get(self, cr, uid, fields, context=None):
        """ Get default values
        @param self: The object pointer.
        @param cr: A database cursor
        @param uid: ID of the user currently logged in
        @param fields: List of fields for default value
        @param context: A standard dictionary
        @return: default values of fields
        """
        if context is None:
            context = {}
        res = super(vmi_move_consume, self).default_get(cr, uid, fields, context=context)
        move = self.pool.get('stock.move').browse(cr, uid, context['active_id'], context=context)
        if 'product_id' in fields:
            res.update({'product_id': move.product_id.id})
        if 'product_uom' in fields:
            res.update({'product_uom': move.product_uom.id})
        if 'product_qty' in fields:
            res.update({'product_qty': move.product_qty})
        if 'location_id' in fields:
            res.update({'location_id': move.location_id.id})

        return res

    def do_move_consume(self, cr, uid, ids, context=None):
        """ To move consumed products
        @param self: The object pointer.
        @param cr: A database cursor
        @param uid: ID of the user currently logged in
        @param ids: the ID or list of IDs if we want more than one
        @param context: A standard dictionary
        @return:
        """
        if context is None:
            context = {}
        move_obj = self.pool.get('stock.move')
        move_ids = context['active_ids']
        for data in self.browse(cr, uid, ids, context=context):
            move_obj.action_consume(cr, uid, move_ids,
                                    data.product_qty, data.location_id.id,
                                    context=context)
        return {'type': 'ir.actions.client', 'tag': 'reload'}


vmi_move_consume()


class stock_move_audit(osv.osv_memory):
    _name = "stock.move.audit"
    _description = "Audit Product Line Items"
    _inherit = "vmi.move.consume"

    _defaults = {
        'location_id': lambda *x: False
    }

    def default_get(self, cr, uid, fields, context=None):
        """ Get default values
        @param self: The object pointer.
        @param cr: A database cursor
        @param uid: ID of the user currently logged in
        @param fields: List of fields for default value
        @param context: A standard dictionary
        @return: default values of fields
        """
        _logger.debug('<default_get> get fields: %s', fields)
        _logger.debug('<default_get> get context: %s', context)
        if context is None:
            context = {}
        res = super(vmi_move_consume, self).default_get(cr, uid, fields, context=context)
        move = self.pool.get('stock.move').browse(cr, uid, context['active_id'], context=context)
        location_obj = self.pool.get('stock.location')
        location_ids = location_obj.search(cr, uid, [('id', '=', move.location_dest_id.id)])
        _logger.debug('<stock_move_audit> location_ids: %s', str(location_ids))
        l = self.pool.get('stock.location').browse(cr, uid, location_ids, context=context)
        parent_location = l[0].location_id.id
        _logger.debug('<stock_move_audit> parent_location: %s', str(parent_location))
        audit_location = location_obj.search(cr, uid, [('location_id', '=', parent_location), ('name', '=', 'Audit')])
        _logger.debug('<stock_move_audit> audit_location: %s', str(audit_location))

        if 'product_id' in fields:
            res.update({'product_id': move.product_id.id})
        if 'product_uom' in fields:
            res.update({'product_uom': move.product_uom.id})
        if 'product_qty' in fields:
            res.update({'product_qty': move.product_qty})
        if 'location_id' in fields and location_ids:
            res.update({'location_id': audit_location[0]})
            # if scrpaed_location_ids:
            #    res.update({'location_id': scrpaed_location_ids[0]})
            #else:
            #    res.update({'location_id': False})
        _logger.debug('<default_get> final res: %s', res)
        return res

    def move_audited(self, cr, uid, ids, context=None):
        """ To move audited products
        @param self: The object pointer.
        @param cr: A database cursor
        @param uid: ID of the user currently logged in
        @param ids: the ID or list of IDs if we want more than one
        @param context: A standard dictionary
        @return:
        """
        if context is None:
            context = {}
        move_obj = self.pool.get('stock.move')
        move_ids = context['active_ids']
        for data in self.browse(cr, uid, ids):
            move_obj.action_audit(cr, uid, move_ids,
                                  data.product_qty, data.location_id.id,
                                  context)
        return {'type': 'ir.actions.client', 'tag': 'reload'}


stock_move_audit()


class vmi_stock_picking(osv.osv):

    _name = 'stock.picking'
    _inherit = 'stock.picking'
    _table = "stock_picking"
    #_order = 'id desc'

    _columns = {}

    def action_invoice_create(self, cr, uid, ids, journal_id=False,
            group=False, type='in_invoice', context=None):
        """

        :param cr:
        :param uid:
        :param ids:
        :param journal_id:
        :param group:
        :param type:
        :param context:
        :return:
        """
        if context is None:
            context = {}
        res = {}
        _logger.debug('<action_invoice_create> inherited')
        _logger.debug('<action_invoice_create> Group or not: %s', group)
        _logger.debug('<action_invoice_create> uid: %s, id: %s', uid, ids)
        invoice_obj = self.pool.get('account.invoice')
        invoice_line_obj = self.pool.get('account.invoice.line')
        partner_obj = self.pool.get('res.partner')
        invoice_name = []
        new_picking = []
        invoices_group = {}
        product_category = None
        res = {}
        inv_type = type
        for picking in self.browse(cr, uid, ids, context=context):
            _logger.debug('<action_invoice_create> Into the picking loop')
            if picking.invoice_state != '2binvoiced':
                continue
            partner = self._get_partner_to_invoice(cr, uid, picking, context=context)
            if isinstance(partner, int):
                partner = partner_obj.browse(cr, uid, [partner], context=context)[0]
            if not partner:
                raise osv.except_osv(_('Error, no partner!'),
                    _('Please put a partner on the picking list if you want to generate invoice.'))
            if not inv_type:
                inv_type = self._get_invoice_type(picking)
            pricelist_id = partner.property_product_pricelist_purchase.id
            for move_line in picking.move_lines:
                _logger.debug('<action_invoice_create> invoices_group: %s', str(invoices_group))
                invoice_name = '-'.join([str(partner.name), str(picking.location_dest_id.name),
                                        str(move_line.product_id.categ_id.name)])
                #create new invoice
                if new_picking not in invoices_group.keys():
                    context['invoice_name'] = invoice_name
                    context['invoice_category'] = move_line.product_id.categ_id.id
                    context['invoice_location'] = picking.location_dest_id.id
                    _logger.debug('<action_invoice_create> invoice_name: %s', str(context['invoice_name']))
                    invoice_vals = self._prepare_invoice(cr, uid, picking, partner, inv_type, journal_id, context=context)
                    invoice_id = invoice_obj.create(cr, uid, invoice_vals, context=context)
                    #invoices_group[partner.id] = invoice_id
                    invoices_group[invoice_name] = invoice_id
                #invoice already existed
                elif group:
                    _logger.debug('<action_invoice_create> Same group')
                    invoice_id = invoices_group[new_picking]
                    invoice = invoice_obj.browse(cr, uid, invoice_id)
                    invoice_vals_group = self._prepare_invoice_group(cr, uid, picking, partner, invoice, context=context)
                    _logger.debug('<action_invoice_create> invoice_vals_group: %s', str(invoice_vals_group))
                    invoice_obj.write(cr, uid, [invoice_id], invoice_vals_group, context=context)

                res[picking.id] = invoice_id
                invoice_vals['pricelist_id'] = pricelist_id
                if move_line.state == 'cancel':
                    _logger.debug('<action_invoice_create> canceled')
                    continue
                if move_line.scrapped:
                    _logger.debug('<action_invoice_create> scrapped')
                    # do no invoice scrapped products
                    continue
                #product_category = move_line.product_id.categ_id.name
                '''if product_category not in invoice_vals['name']:
                    _logger.debug('<action_invoice_create> Add product category')
                    if new_picking in invoices_group.keys() and len(invoices_group) > 1:
                        _logger.debug('<action_invoice_create> In move_line: different category')
                        invoice_name = new_picking + '-' + product_category
                        context['invoice_name'] = invoice_name
                        _logger.debug('<action_invoice_create> In Move_line: Different category invoice_name: %s',
                                      str(context['invoice_name']))
                        invoice_vals = self._prepare_invoice(cr, uid, picking, partner, inv_type,
                                                             journal_id, context=context)
                        invoice_id = invoice_obj.create(cr, uid, invoice_vals, context=context)
                        invoices_group[invoice_name] = invoice_id
                    else:
                        _logger.debug('<action_invoice_create> In move_line: new category')
                        invoice_obj.write(cr, uid, [invoice_id], {
                            'name': invoice_vals['name'] + '-' + product_category
                        }, context=context)
                    if len(invoices_group) == 1 or new_picking not in invoices_group.keys():
                        _logger.debug('<action_invoice_create> In move_line: new category')
                        invoice_obj.write(cr, uid, [invoice_id], {
                            'name': invoice_vals['name'] + '-' + product_category
                        }, context=context)
                        #invoice_vals['name'] = invoice_vals['name'] + '-' + product_category
                    #Product category is different
                    else:
                        _logger.debug('<action_invoice_create> In move_line: different category')
                        invoice_name = new_picking + '-' + product_category
                        context['invoice_name'] = invoice_name
                        _logger.debug('<action_invoice_create> In Move_line: Different category invoice_name: %s',
                                      str(context['invoice_name']))
                        invoice_vals = self._prepare_invoice(cr, uid, picking, partner, inv_type,
                                                             journal_id, context=context)
                        invoice_id = invoice_obj.create(cr, uid, invoice_vals, context=context)
                        invoices_group[invoice_name] = invoice_id'''
                vals = self._prepare_invoice_line(cr, uid, group, picking, move_line,
                                invoice_id, invoice_vals, context=context)
                _logger.debug('<action_invoice_create> vals: %s', str(vals))
                if vals:
                    _logger.debug('<action_invoice_create> vals existed: %s', str(vals))
                    invoice_line_id = invoice_line_obj.create(cr, uid, vals, context=context)
                    self._invoice_line_hook(cr, uid, move_line, invoice_line_id)

            invoice_obj.button_compute(cr, uid, [invoice_id], context=context,
                    set_total=(inv_type in ('in_invoice', 'in_refund')))
            self.write(cr, uid, [picking.id], {
                'invoice_state': 'invoiced',
                }, context=context)
            self._invoice_hook(cr, uid, picking, invoice_id)
        self.write(cr, uid, res.keys(), {
            'invoice_state': 'invoiced',
            }, context=context)
        return res


    def _prepare_invoice_line(self, cr, uid, group, picking, move_line, invoice_id,
        invoice_vals, context=None):
        """ Builds the dict containing the values for the invoice line
            @param group: True or False
            @param picking: picking object
            @param: move_line: move_line object
            @param: invoice_id: ID of the related invoice
            @param: invoice_vals: dict used to created the invoice
            @return: dict that will be used to create the invoice line
        """
        _logger.debug('<_prepare_invoice_line> into _prepare_invoice_line')

        product_pricelist = self.pool.get('product.pricelist')
        pricelist_id = invoice_vals['pricelist_id']

        name = picking.name
        _logger.debug('<_prepare_invoice_line> name: %s', str(name))
        origin = move_line.picking_id.name or ''
        if move_line.picking_id.origin:
            origin += ':' + move_line.picking_id.origin

        if invoice_vals['type'] in ('out_invoice', 'out_refund'):
            account_id = move_line.product_id.property_account_income.id
            if not account_id:
                account_id = move_line.product_id.categ_id.\
                        property_account_income_categ.id
        else:
            _logger.debug('<_prepare_invoice_line> type is not out')
            _logger.debug('<_prepare_invoice_line> product_id: %s', move_line.product_id)
            account_id = invoice_vals['account_id']
            #account_id = move_line.product_id.property_account_expense.id
            '''if not account_id:
                _logger.debug('<_prepare_invoice_line> do not find account_id in '
                              'move_line.product_id.property_account_expense.id')
                account_id = move_line.product_id.categ_id.\
                        property_account_expense_categ.id'''
        if invoice_vals['fiscal_position']:
            #_logger.debug('<_prepare_invoice_line> fiscal_position')
            fp_obj = self.pool.get('account.fiscal.position')
            fiscal_position = fp_obj.browse(cr, uid, invoice_vals['fiscal_position'], context=context)
            account_id = fp_obj.map_account(cr, uid, fiscal_position, account_id)
        _logger.debug('<_prepare_invoice_line> account_id: %s', str(account_id))
        # Check if there is an active pricelist for current supplier
        if pricelist_id:
            price = product_pricelist.price_get(cr, uid, [pricelist_id],
                    move_line.product_id.id, move_line.product_uos_qty or move_line.product_qty,
                    invoice_vals['partner_id'] or False)[pricelist_id]
        else:
            price = move_line.product_id.standard_price

        return {
            'name': name,
            'origin': origin,
            'invoice_id': invoice_id,
            # uos_id is used for storing picking information instead.
            'stock_move_id': move_line.id,
            'product_id': move_line.product_id.id,
            'account_id': account_id,
            'price_unit': price,
            #'price_unit': self._get_price_unit_invoice(cr, uid, move_line, invoice_vals['type']),
            'discount': self._get_discount_invoice(cr, uid, move_line),
            'quantity': move_line.product_uos_qty or move_line.product_qty,
            'invoice_line_tax_id': [(6, 0, self._get_taxes_invoice(cr, uid, move_line, invoice_vals['type']))],
            'account_analytic_id': self._get_account_analytic_invoice(cr, uid, picking, move_line),
        }

    def _prepare_invoice_group(self, cr, uid, picking, partner, invoice, context=None):
        """ Builds the dict for grouped invoices
            @param picking: picking object
            @param partner: object of the partner to invoice (not used here, but may be usefull if this function is inherited)
            @param invoice: object of the invoice that we are updating
            @return: dict that will be used to update the invoice
        """
        comment = self._get_comment_invoice(cr, uid, picking)
        return {
            'name': invoice.name,
            'origin': (invoice.origin or '') + ', ' + (picking.name or '') + (picking.origin and (':' + picking.origin) or ''),
            'comment': (comment and (invoice.comment and invoice.comment + "\n" + comment or comment)) or (invoice.comment and invoice.comment or ''),
            'date_invoice': context.get('date_inv', False),
            'user_id': uid,
        }

    def _prepare_invoice(self, cr, uid, picking, partner, inv_type, journal_id, context=None):
        """ Builds the dict containing the values for the invoice
            @param picking: picking object
            @param partner: object of the partner to invoice
            @param inv_type: type of the invoice ('out_invoice', 'in_invoice', ...)
            @param journal_id: ID of the accounting journal
            @return: dict that will be used to create the invoice object
        """
        if isinstance(partner, int):
            partner = self.pool.get('res.partner').browse(cr, uid, partner, context=context)
        if inv_type in ('out_invoice', 'out_refund'):
            account_id = partner.property_account_receivable.id
            payment_term = partner.property_payment_term.id or False
        else:
            account_id = partner.property_account_payable.id
            payment_term = partner.property_supplier_payment_term.id or False
        comment = self._get_comment_invoice(cr, uid, picking)
        invoice_vals = {
            'name': context['invoice_name'],
            'origin': (picking.name or '') + (picking.origin and (':' + picking.origin) or ''),
            'type': inv_type,
            'account_id': account_id,
            'partner_id': partner.id,
            'comment': comment,
            'payment_term': payment_term,
            'fiscal_position': partner.property_account_position.id,
            'date_invoice': context.get('date_inv', False),
            'company_id': picking.company_id.id,
            'user_id': uid,
            'category_id': context['invoice_category'],
            'location_id': context['invoice_location'],
        }
        cur_id = self.get_currency_id(cr, uid, picking)
        if cur_id:
            invoice_vals['currency_id'] = cur_id
        if journal_id:
            invoice_vals['journal_id'] = journal_id
        return invoice_vals

vmi_stock_picking()

class vmi_account_invoice(osv.osv):
    _name = 'account.invoice'
    _inherit = 'account.invoice'

    _columns = {
        'state': fields.selection([
            ('draft', 'Draft'),
            ('manager_approved', 'Septa Manager Approved'),
            ('vendor_denied', 'Vendor Denied'),
            ('vendor_approved', 'Vendor Approved'),
            ('paid', 'Paid'),
            ('cancel', 'Cancelled'),
            ], 'Status', select=True, readonly=True, track_visibility='onchange',
            help=' * The \'Draft\' status is used when a user is encoding a new and unconfirmed Invoice, waiting for confirmation by manager. \
            \n* The \'Septa Manager Approved\' status indicates that this invoice has been approved by manager and waiting for confirmation by vendor. \
            \n* The \'Vendor Denied\' status indicates that this invoice has been denied by vendor. Manager need to review it and re-validate. \
            \n* The \'Vendor Approved\' status indicates that this invoice has been approved by vendor. \
            \n* The \'Paid\' status is set automatically when the invoice is paid. Its related journal entries may or may not be reconciled. \
            \n* The \'Cancelled\' status is used when user cancel invoice.'),
        'invoice_line': fields.one2many('account.invoice.line', 'invoice_id', 'Invoice Lines', states={'draft':[('readonly',False)]}),
        'location_id': fields.many2one('stock.location', 'Location', states={'done': [('readonly', True)]}, select=True, track_visibility='always', help="Location that stocks the finished products in current invoice."),
        'category_id': fields.many2one('product.category','Category', states={'done': [('readonly', True)]}, select=True, track_visibility='always', help="Select category for the current product"),
    }

    def invoice_validate(self, cr, uid, ids, context=None):
        self.write(cr, uid, ids, {'state': 'manager_approved'}, context=context)
        return True

    # vendor approved the current invoice
    def invoice_vendor_approve(self, cr, uid, ids, context=None):
        self.write(cr, uid, [int(ids)], {'state': 'vendor_approved'}, context=context)
        return True

    # vendor denied the current invoice
    # (must cancel the invoice first, then set it to vendor_denied, otherwise the invoice can not be re-validate)
    def invoice_vendor_deny(self, cr, uid, ids, context=None):
        #make "ids" a list ids (required if using existing method in any model)
        ids = [int(ids)]
        # cancel the current invoice
        canceled = self.action_cancel(cr, uid, ids, None)
        if canceled:
            # set invoice from canceled to vendor_denied
            self.write(cr, uid, ids, {'state': 'vendor_denied', 'comment': context['comment']}, None)
            wf_service = netsvc.LocalService("workflow")
            for inv_id in ids:
                wf_service.trg_delete(uid, 'account.invoice', inv_id, cr)
                wf_service.trg_create(uid, 'account.invoice', inv_id, cr)
        return True

vmi_account_invoice()


class account_invoice_line(osv.osv):

    _name = "account.invoice.line"
    _inherit = "account.invoice.line"
    _description = "Invoice Line"
    _columns = {
        'stock_move_id': fields.many2one('stock.move', 'Reference', select=True,states={'done': [('readonly', True)]}),
    }

class vmi_account_move(osv.osv):
    _name = "account.move"
    _inherit = "account.move"
    _description = "Account Entry"

    def button_cancel(self, cr, uid, ids, context=None):
        '''for line in self.browse(cr, uid, ids, context=context):
            if not line.journal_id.update_posted:
                raise osv.except_osv(_('Error!'), _('You cannot modify a posted entry of this journal.\nFirst you should set the journal to allow cancelling entries.'))'''
        if ids:
            cr.execute('UPDATE account_move '\
                       'SET state=%s '\
                       'WHERE id IN %s', ('draft', tuple(ids),))
        return True

vmi_account_move()