import logging
from openerp.osv import osv
from openerp.osv import fields
from openerp import SUPERUSER_ID
from openerp import pooler, tools, netsvc
from openerp.tools.translate import _
from openerp.tools.config import configmanager
import openerp.addons.decimal_precision as dp
import optparse
import time
import base64
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
    _order = 'date desc'

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

    def action_flag_audit(self, cr, uid, vals, context=None):

        """
        move this function from stock_picking. Rewrite function using openerp ORM method instead of SQL query.
        @param self:
        @param cr:
        @param user:
        @param vals:
        @param context:
        """
        result = []
        pickings = []
        stock_picking_obj = self.pool.get('stock.picking')
        if 'pid' in vals:
            res_partner_obj = self.pool.get('res.partner')
            partner = res_partner_obj.browse(cr, uid, int(vals['pid']), None)
            remained_audit = partner.mobile
            last_record = partner.birthdate
        '''for picking in vals['parse_result']['stock_pickings']:
            picking_id = picking['picking_id']'''
        if 'parse_result' in vals:
            p = vals.get('parse_result')
            if 'move_lines' in p:
                new_moves_id = self.search(cr, uid, [('vendor_id', '=', int(vals['pid'])), ('id', '>', int(last_record)), ('audit_fail', '=', False)], None)
                new_moves = self.browse(cr, uid, new_moves_id, None)
                total_qty = sum(move.product_qty for move in new_moves)
                last_record = max(move.id for move in new_moves)
                number_to_flag = int(round(total_qty * 0.1) + float(remained_audit))
                new_moves = sorted(new_moves, key=lambda k: k.product_qty, reverse=True)
                for move in new_moves:
                    if number_to_flag > 0 and move.product_qty <= number_to_flag:
                        result.append(move.id)
                        number_to_flag -= move.product_qty
                        if move.picking_id.id not in pickings:
                            pickings.append(move.picking_id.id)

                if result:
                    self.write(cr, uid, result, {'audit': True}, None)
                stock_picking_obj.write(cr, uid, pickings, {'contains_audit': 'yes'}, None)
                res_partner_obj.write(cr, uid, int(vals['pid']), {'mobile': str(int(number_to_flag)), 'birthdate': last_record}, None)

        return result

    def flag_for_audit(self, cr, uid, ids, vals=[], context=None):
        return self.write(cr, uid, ids, {'audit': True}, context=context)

    def unflag_for_audit(self, cr, uid, ids, vals=[], context=None):
        user_obj = self.pool.get('res.users')
        storekeeper = user_obj.browse(cr, uid, uid).login
        note = "Audit conducted at %s by %s." % (str(time.strftime('%Y-%m-%d %H:%M:%S')), storekeeper.capitalize())
        return self.write(cr, uid, ids, {'audit': False, 'note': note}, context=context)

    def flag_fail_audit(self, cr, uid, ids, vals, context=None):
        return self.write(cr, uid, ids, {'audit_fail': True}, context=context)

    def action_audit(self, cr, uid, ids, quantity, location, context=None):
        """
        Audit processing
        :param cr:
        :param uid:
        :param ids:
        :param quantity:
        :param location:
        :param context:
        :return:
        """
        if context is None:
            context = {}
        # audit quantity should be less than or equal to shipped quant.
        if quantity < 0:
            raise osv.except_osv(_('Warning!'), _('Please provide a non-negative quantity.'))
        stock_picking_obj = self.pool.get('stock.picking')
        partner_obj = self.pool.get('res.partner')
        template_obj = self.pool.get('email.template')
        #check which manager need a notification
        recipient_ids = []
        admin_id = partner_obj.search(cr, uid, [('name', '=', 'SEPTA Admin')])
        admin = partner_obj.browse(cr, uid, admin_id, context=None)[0]
        manager_child_ids = admin.child_ids
        for child in manager_child_ids:
            if child.audit_notification:
                recipient_ids.append(int(child.id))
        move = self.browse(cr, uid, ids[0], context=context)
        vendor_child_ids = move.vendor_id.child_ids
        for child in vendor_child_ids:
            if child.audit_notification:
                recipient_ids.append(int(child.id))
        res = []
        user_obj = self.pool.get('res.users')


        if move:
        #for move in self.browse(cr, uid, ids, context=context):
            move_qty = move.product_qty
            uos_qty = quantity / move_qty * move.product_uos_qty
            if move_qty != quantity:
                difference_quant = move_qty - quantity
                difference_uos = difference_quant * move.product_uos_qty
                storekeeper = user_obj.browse(cr, uid, uid).login
                note = "Missing %s product(s). Audit conducted at %s by %s." % (difference_quant, str(time.strftime('%Y-%m-%d %H:%M:%S')), storekeeper.capitalize())
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
                self.write(cr, uid, ids, {'product_qty': quantity, 'note': note, 'audit': False}, context)
                self.action_done(cr, uid, ids, context)
                res += [new_move]
                note += " On stock.move ID %d" % move.id
                _logger.debug('<action_audit> %s', note)
                stock_picking_obj.change_picking_audit_result(cr, uid, move.picking_id.id, False, None)
                product_obj = self.pool.get('product.product')
                for product in product_obj.browse(cr, uid, [move.product_id.id], context=context):
                    if move.picking_id:
                        uom = product.uom_id.name if product.uom_id else ''
                        message = _("%s %s %s has been moved to <b>Failed Audits</b>.") % (quantity, uom, product.name)
                        move.picking_id.message_post(body=message)
                #find template id and send email
                if len(recipient_ids) > 0:
                    context['recipient_ids'] = recipient_ids
                    template_id = template_obj.search(cr, uid, [('name', '=', 'Notification for Audit Fail')])
                    if template_id:
                        mail = template_obj.send_mail(cr, uid, template_id[0], move.id, True, context=context)
                    else:
                        raise osv.except_osv(_('Error!'), _('No Email Template Found, Please configure a email template under Email tab and named "Notification for Audit Fail"'))

            else:
                move.unflag_for_audit()
                move.action_done()
                stock_picking_obj.change_picking_audit_result(cr, uid, move.picking_id.id, True, None)
                '''
                if len(recipient_ids) > 0:
                    context['recipient_ids'] = recipient_ids
                    template_id = template_obj.search(cr, uid, [('name', '=', 'Notification for Audit Pass')])
                    if template_id:
                        mail = template_obj.send_mail(cr, uid, template_id[0], move.id, True, context=context)
                    else:
                        raise osv.except_osv(_('Error!'), _('No Email Template Found, Please configure a email template under Email tab and named "Notification for Audit Pass"'))
                '''
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

    _columns = {
        'contains_audit': fields.selection([
            ('no', 'No Audit'),
            ('yes', 'Auditing'),
            ('pass', 'Pass Audit'),
            ('fail', 'Fail Audit')], 'Contains Audit',
            help="Specify whether this package contains Audited goods, If contains, Pass or Fail"),
    }


        #add attr to vendor in database:
        # mobile: number of product need to be audited
        # birthdate: last record before upload

    def action_flag_audit(self, cr, uid, vals, context=None):

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

        '''if 'pid' in vals:
            res_partner_obj = self.pool.get('res_partner')
            partner = res_partner_obj.browse(cr, uid, [vals['pid']], None)
            remained_audit = partner.mobile
            last_record = partner.birthdate
        for picking in vals['parse_result']['stock_pickings']:
            picking_id = picking['picking_id']'''
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
                            """ % (int(number_to_flag), last_record, pid)
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
        'contains_audit': 'no',
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

    _columns = {
        'contains_audit': fields.selection([
            ('no', 'No Audit'),
            ('yes', 'Auditing'),
            ('pass', 'Pass Audit'),
            ('fail', 'Fail Audit')], 'Contains Audit',
            help="Specify whether this package contains Audited goods, If contains, Pass or Fail"),
    }

    _defaults = {
        'contains_audit': 'no'
    }

    def change_picking_audit_result(self, cr, uid, ids, audit_pass, context=None):
        """
        When an audit performed, call this function to change the audit state in the picking slip
        :param cr:
        :param uid:
        :param ids:
        :param context:
        :return:
        """
        picking = self.browse(cr, uid, ids, None)
        if picking.contains_audit == u'yes':
            if audit_pass is False:
                self.write(cr, uid, ids, {'contains_audit': 'fail'})
            else:
                for move in picking.move_lines:
                    if move.audit is True:
                        return picking.contains_audit
                self.write(cr, uid, ids, {'contains_audit': 'pass'})
        return picking.contains_audit


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
        # check whether there is product to be audited
        for picking in self.browse(cr, uid, ids, context=context):
            if picking.invoice_state != '2binvoiced':
                raise osv.except_osv(_('error!'),_("There is at least one shipment has been invoiced"))
            if picking.contains_audit == 'yes':
                raise osv.except_osv(_('error!'),_("There is at least one product to be audited"))
        #Create Invoices
        for picking in self.browse(cr, uid, ids, context=context):
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
                if invoice_name not in invoices_group.keys():
                    context['invoice_name'] = invoice_name
                    context['invoice_category'] = move_line.product_id.categ_id.id
                    context['invoice_location'] = picking.location_dest_id.id
                    _logger.debug('<action_invoice_create> invoice_name: %s', str(context['invoice_name']))
                    invoice_vals = self._prepare_invoice(cr, uid, picking, partner, inv_type, journal_id, context=context)
                    invoice_id = invoice_obj.create(cr, uid, invoice_vals, context=context)
                    invoices_group[invoice_name] = invoice_id
                #invoice already existed
                elif group:
                    _logger.debug('<action_invoice_create> Same group')
                    invoice_id = invoices_group[invoice_name]
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
        #_logger.debug('<_prepare_invoice_line> into _prepare_invoice_line')

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
            _logger.debug('<_prepare_invoice_line> product_id: %s', move_line.product_id)
            account_id = invoice_vals['account_id']
            '''fp_obj = self.pool.get('account.fiscal.position')
            fiscal_position = fp_obj.browse(cr, uid, invoice_vals['fiscal_position'], context=context)
            #account_id = fp_obj.map_account(cr, uid, fiscal_position, account_id)'''
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
            ('ready', 'Ready for AP'),
            ('cancel', 'Cancelled'),
            ], 'Status', select=True, readonly=True, track_visibility='onchange',
            help=' * The \'Draft\' status is used when a user is encoding a new and unconfirmed Invoice, waiting for confirmation by manager. \
            \n* The \'Septa Manager Approved\' status indicates that this invoice has been approved by manager and waiting for confirmation by vendor. \
            \n* The \'Vendor Denied\' status indicates that this invoice has been denied by vendor. Manager need to review it and re-validate. \
            \n* The \'Vendor Approved\' status indicates that this invoice has been approved by vendor. \
            \n* The \'Paid\' status is set automatically when the invoice is paid. Its related journal entries may or may not be reconciled. \
            \n* The \'Cancelled\' status is used when user cancel invoice.'),
        'invoice_line': fields.one2many('account.invoice.line', 'invoice_id', 'Invoice Lines', states={'draft':[('readonly',False)]}),
        'account_line': fields.one2many('account.invoice.account.line', 'invoice_id', 'Account Lines'),
        'location_id': fields.many2one('stock.location', 'Location', states={'done': [('readonly', True)]}, select=True, track_visibility='always', help="Location that stocks the finished products in current invoice."),
        'category_id': fields.many2one('product.category','Category', states={'done': [('readonly', True)]}, select=True, track_visibility='always', help="Select category for the current product"),
    }

    def action_move_create(self, cr, uid, ids, context=None):
        """Creates invoice related analytics and financial move lines"""
        ait_obj = self.pool.get('account.invoice.tax')
        cur_obj = self.pool.get('res.currency')
        period_obj = self.pool.get('account.period')
        payment_term_obj = self.pool.get('account.payment.term')
        journal_obj = self.pool.get('account.journal')
        move_obj = self.pool.get('account.move')
        if context is None:
            context = {}
        for inv in self.browse(cr, uid, ids, context=context):
            if not inv.journal_id.sequence_id:
                raise osv.except_osv(_('Error!'), _('Please define sequence on the journal related to this invoice.'))
            if not inv.invoice_line:
                raise osv.except_osv(_('No Invoice Lines!'), _('Please create some invoice lines.'))
            if inv.move_id:
                continue

            ctx = context.copy()
            ctx.update({'lang': inv.partner_id.lang})
            if not inv.date_invoice:
                self.write(cr, uid, [inv.id], {'date_invoice': fields.date.context_today(self,cr,uid,context=context)}, context=ctx)
            company_currency = self.pool['res.company'].browse(cr, uid, inv.company_id.id).currency_id.id
            # create the analytical lines
            # one move line per invoice line
            iml = self._get_analytic_lines(cr, uid, inv.id, context=ctx)
            # check if taxes are all computed
            compute_taxes = ait_obj.compute(cr, uid, inv.id, context=ctx)
            self.check_tax_lines(cr, uid, inv, compute_taxes, ait_obj)

            # Disabled the check_total feature
            '''group_check_total_id = self.pool.get('ir.model.data').get_object_reference(cr, uid, 'account', 'group_supplier_inv_check_total')[1]
            group_check_total = self.pool.get('res.groups').browse(cr, uid, group_check_total_id, context=context)
            if group_check_total and uid in [x.id for x in group_check_total.users]:
                if (inv.type in ('in_invoice', 'in_refund') and abs(inv.check_total - inv.amount_total) >= (inv.currency_id.rounding/2.0)):
                    raise osv.except_osv(_('Bad Total!'), _('Please verify the price of the invoice!\nThe encoded total does not match the computed total.'))'''

            if inv.payment_term:
                total_fixed = total_percent = 0
                for line in inv.payment_term.line_ids:
                    if line.value == 'fixed':
                        total_fixed += line.value_amount
                    if line.value == 'procent':
                        total_percent += line.value_amount
                total_fixed = (total_fixed * 100) / (inv.amount_total or 1.0)
                if (total_fixed + total_percent) > 100:
                    raise osv.except_osv(_('Error!'), _("Cannot create the invoice.\nThe related payment term is probably misconfigured as it gives a computed amount greater than the total invoiced amount. In order to avoid rounding issues, the latest line of your payment term must be of type 'balance'."))

            # one move line per tax line
            iml += ait_obj.move_line_get(cr, uid, inv.id)

            entry_type = ''
            if inv.type in ('in_invoice', 'in_refund'):
                ref = inv.reference
                entry_type = 'journal_pur_voucher'
                if inv.type == 'in_refund':
                    entry_type = 'cont_voucher'
            else:
                ref = self._convert_ref(cr, uid, inv.number)
                entry_type = 'journal_sale_vou'
                if inv.type == 'out_refund':
                    entry_type = 'cont_voucher'

            diff_currency_p = inv.currency_id.id <> company_currency
            # create one move line for the total and possibly adjust the other lines amount
            total = 0
            total_currency = 0
            total, total_currency, iml = self.compute_invoice_totals(cr, uid, inv, company_currency, ref, iml, context=ctx)
            acc_id = inv.account_id.id

            name = inv['name'] or inv['supplier_invoice_number'] or '/'
            totlines = False
            if inv.payment_term:
                totlines = payment_term_obj.compute(cr,
                        uid, inv.payment_term.id, total, inv.date_invoice or False, context=ctx)
            if totlines:
                res_amount_currency = total_currency
                i = 0
                ctx.update({'date': inv.date_invoice})
                for t in totlines:
                    if inv.currency_id.id != company_currency:
                        amount_currency = cur_obj.compute(cr, uid, company_currency, inv.currency_id.id, t[1], context=ctx)
                    else:
                        amount_currency = False

                    # last line add the diff
                    res_amount_currency -= amount_currency or 0
                    i += 1
                    if i == len(totlines):
                        amount_currency += res_amount_currency

                    iml.append({
                        'type': 'dest',
                        'name': name,
                        'price': t[1],
                        'account_id': acc_id,
                        'date_maturity': t[0],
                        'amount_currency': diff_currency_p \
                                and amount_currency or False,
                        'currency_id': diff_currency_p \
                                and inv.currency_id.id or False,
                        'ref': ref,
                    })
            else:
                iml.append({
                    'type': 'dest',
                    'name': name,
                    'price': total,
                    'account_id': acc_id,
                    'date_maturity': inv.date_due or False,
                    'amount_currency': diff_currency_p \
                            and total_currency or False,
                    'currency_id': diff_currency_p \
                            and inv.currency_id.id or False,
                    'ref': ref
            })

            date = inv.date_invoice or time.strftime('%Y-%m-%d')

            part = self.pool.get("res.partner")._find_accounting_partner(inv.partner_id)

            line = map(lambda x:(0,0,self.line_get_convert(cr, uid, x, part.id, date, context=ctx)),iml)

            line = self.group_lines(cr, uid, iml, line, inv)

            journal_id = inv.journal_id.id
            journal = journal_obj.browse(cr, uid, journal_id, context=ctx)
            if journal.centralisation:
                raise osv.except_osv(_('User Error!'),
                        _('You cannot create an invoice on a centralized journal. Uncheck the centralized counterpart box in the related journal from the configuration menu.'))

            line = self.finalize_invoice_move_lines(cr, uid, inv, line)

            move = {
                'ref': inv.reference and inv.reference or inv.name,
                'line_id': line,
                'journal_id': journal_id,
                'date': date,
                'narration': inv.comment,
                'company_id': inv.company_id.id,
            }
            period_id = inv.period_id and inv.period_id.id or False
            ctx.update(company_id=inv.company_id.id,
                       account_period_prefer_normal=True)
            if not period_id:
                period_ids = period_obj.find(cr, uid, inv.date_invoice, context=ctx)
                period_id = period_ids and period_ids[0] or False
            if period_id:
                move['period_id'] = period_id
                for i in line:
                    i[2]['period_id'] = period_id

            ctx.update(invoice=inv)
            move_id = move_obj.create(cr, uid, move, context=ctx)
            new_move_name = move_obj.browse(cr, uid, move_id, context=ctx).name
            # make the invoice point to that move
            self.write(cr, uid, [inv.id], {'move_id': move_id,'period_id':period_id, 'move_name':new_move_name}, context=ctx)
            # Pass invoice in context in method post: used if you want to get the same
            # account move reference when creating the same invoice after a cancelled one:
            move_obj.post(cr, uid, [move_id], context=ctx)
        self._log_event(cr, uid, ids)
        return True

    def finalize_invoice_move_lines(self, cr, uid, invoice_browse, move_lines):

        return move_lines

    def invoice_validate(self, cr, uid, ids, context=None):
        """
        When button "Validate" clicked, call this function to change the state and send notification if needed
        :param cr:
        :param uid:
        :param ids:
        :param context:
        :return:
        """
        if context is None:
            context = {}
        invoice = self.browse(cr, uid, ids, context)[0]

        #Check which partner need a notification
        child_ids = invoice.partner_id.child_ids
        recipient_ids = []
        for child in child_ids:
            if child.notification:
                recipient_ids.append(int(child.id))

        res = self.write(cr, uid, ids, {'state': 'manager_approved'}, context=context)
        if res and len(recipient_ids) > 0:
            context['recipient_ids'] = recipient_ids

            #get email template, render it and send it
            template_obj = self.pool.get('email.template')
            template_id = template_obj.search(cr, uid, [('name', '=', 'Notification for Septa Manager Approved')])
            if template_id:
                mail = template_obj.send_mail(cr, uid, template_id[0], ids[0], True, context=context)
            else:
                raise osv.except_osv(_('Error!'), _('No Email Template Found, Please configure a email template under Email tab and named "Notification for Septa Manager Approved"'))
        return True

    # vendor approved the current invoice
    def invoice_vendor_approve(self, cr, uid, ids, context=None):
        """
        When receiving a vendor approved invoice, call this function to change the state and send notification if needed
        :param cr:
        :param uid:
        :param ids:
        :param context:
        :return:
        """
        if context is None:
            context = {}

        #check which manager need a notification
        recipient_ids = []
        partner_obj = self.pool.get('res.partner')
        admin_id = partner_obj.search(cr, uid, [('name', '=', 'SEPTA Admin')])
        admin = partner_obj.browse(cr, uid, admin_id, context=None)[0]
        child_ids = admin.child_ids
        for child in child_ids:
            if child.notification:
                recipient_ids.append(int(child.id))

        res = self.write(cr, uid, [int(ids)], {'state': 'vendor_approved'}, context=context)
        if res and len(recipient_ids) > 0:
            context['recipient_ids'] = recipient_ids
            template_obj = self.pool.get('email.template')
            template_id = template_obj.search(cr, uid, [('name', '=', 'Notification for Vendor Approved')])
            if template_id:
                mail = template_obj.send_mail(cr, uid, template_id[0], int(ids), True, context=context)
            else:
                raise osv.except_osv(_('Error!'), _('No Email Template Found, Please configure a email template under Email tab and named "Notification for Vendor Approved"'))
        return True

    def invoice_vendor_deny(self, cr, uid, ids, context=None):
        """
        vendor denied the current invoice
        (must cancel the invoice first, then set it to vendor_denied, otherwise the invoice can not be re-validate)
        :param cr:
        :param uid:
        :param ids:
        :param context:
        :return:
        """
        if context is None:
            context = {}
        #make "ids" a list ids (required if using existing method in any model)
        ids = [int(ids)]
        recipient_ids = []
        partner_obj = self.pool.get('res.partner')
        admin_id = partner_obj.search(cr, uid, [('name', '=', 'SEPTA Admin')])
        admin = partner_obj.browse(cr, uid, admin_id, context=None)[0]
        child_ids = admin.child_ids
        for child in child_ids:
            if child.notification:
                recipient_ids.append(int(child.id))
        # cancel the current invoice
        canceled = self.action_cancel(cr, uid, ids, None)
        if canceled:
            # set invoice from canceled to vendor_denied
            res = self.write(cr, uid, ids, {'state': 'vendor_denied', 'comment': context['comment']}, None)
            wf_service = netsvc.LocalService("workflow")
            for inv_id in ids:
                wf_service.trg_delete(uid, 'account.invoice', inv_id, cr)
                wf_service.trg_create(uid, 'account.invoice', inv_id, cr)
            if res and len(recipient_ids) > 0:
                context['recipient_ids'] = recipient_ids
                template_obj = self.pool.get('email.template')
                template_id = template_obj.search(cr, uid, [('name', '=', 'Notification for Vendor Denied')])
                if template_id:
                    mail = template_obj.send_mail(cr, uid, template_id[0], ids[0], True, context=context)
                else:
                    raise osv.except_osv(_('Error!'), _('No Email Template Found, Please configure a email template under Email tab and named "Notification for Vendor Denied"'))
        return True

    def calculate_service_fee(self, cr, uid, ids, context=None):
        wf_service = netsvc.LocalService('workflow')
        if context is None:
            context = {}
        account_invoice_obj = self.pool.get('account.invoice')
        #valid_ids = []
        data_inv = self.pool.get('account.invoice').read(cr, uid, context['active_ids'], ['state'], context=context)
        for record in data_inv:
            if record['state'] != 'vendor_approved':
                raise osv.except_osv(_('Warning!'), _("Selected invoice(s) cannot be allocated as they are not in 'Vendor Approved' state."))
            account_invoice_obj.prepare_to_pay(cr, uid, record['id'])

        return {'type': 'ir.actions.act_window_close'}

    def prepare_to_pay(self, cr, uid, ids, context=None):

        invoice = self.browse(cr, uid, ids[0], None)
        '''if str(invoice.category_id.name) == 'Delivery Fee':
            selected = self.match_delivery_fee(cr, uid, ids, context)
            ir_model_data_obj = self.pool.get('ir.model.data')
            view_ref = ir_model_data_obj.get_object_reference(cr, uid, 'vmi', 'view_delivery_fee_tree')
            view_id = view_ref and view_ref[1] or False
            filter_ref = ir_model_data_obj.get_object_reference(cr, uid, 'vmi', 'view_account_invoice_filter_inherit')
            filter_id = filter_ref and filter_ref[1] or False
            return {
            'name': 'Invoice',
            'view_type': 'tree',
            'view_mode': 'tree',
            'res_model': 'account.invoice',
            #'domain': "('id', 'in', %s)" % selected,
            'domain': [('state', '=', 'vendor_approved')],
            'context': {'state': 'vendor_approved'},
            #'view_id': False,
            'view_id': view_id,
            #'search_view_id': filter_id,
            'type': 'ir.actions.act_window',
            'target': 'new'
            }'''
        account_obj = self.pool.get('account.account')
        account_invoice_line_obj = self.pool.get('account.invoice.line')
        account_invoice_account_line_obj = self.pool.get('account.invoice.account.line')

        #get all special products
        account_product_id = account_obj.search(cr, uid, [('product_ids', '!=', False)], None)
        account_product = account_obj.browse(cr, uid, account_product_id, None)
        products = {}
        for account_p in account_product:
            for product in account_p.product_ids:
                products[product.id] = account_p.id
        #Find the account number for this location & category
        account_ids = account_obj.search(cr, uid, [], None)
        accounts = account_obj.browse(cr, uid, account_ids, None)
        for account in accounts:
            for location in account.location_ids:
                if location.id == invoice.location_id.location_id.id:
                    for category in account.category_ids:
                        if category.id == invoice.category_id.id:
                            group_account_id = account.id

        values = []
        for line in invoice['invoice_line']:
            #Check if special product exist
            if line.product_id.id in products.keys():
                account_id = products[line.product_id.id]
            else:
                account_id = group_account_id

            #Check if id exist
            account_exist = False
            for value in values:
                if value['account_id'] == account_id:
                    value['items'] += 1
                    value['total'] += line.price_subtotal
                    account_exist = True
            if not account_exist:
                items = 1
                total = line.price_subtotal
                values.append({'invoice_id': ids[0], 'account_id': account_id, 'items': items, 'total': total})

            #update account_id to this line
            res = account_invoice_line_obj.write(cr, uid, line.id, {'account_id': account_id}, None)

        if res:
            for value in values:
                account_invoice_account_line_obj.create(cr, uid, value, None)
            change_state = self.write(cr, uid, ids, {'state': 'ready'}, None)

        return True

vmi_account_invoice()


class vmi_account_invoice_line(osv.osv):

    _name = "account.invoice.line"
    _inherit = "account.invoice.line"
    _description = "Invoice Line"
    _columns = {
        'stock_move_id': fields.many2one('stock.move', 'Reference', select=True,states={'done': [('readonly', True)]}),
    }

vmi_account_invoice_line()


class vmi_account_move(osv.osv):
    _name = "account.move"
    _inherit = "account.move"
    _description = "Account Entry"

    def button_cancel(self, cr, uid, ids, context=None):
        if ids:
            cr.execute('UPDATE account_move '\
                       'SET state=%s '\
                       'WHERE id IN %s', ('draft', tuple(ids),))
        return True

vmi_account_move()


class vmi_email_template(osv.osv):
    "Templates for sending email"
    _name = "email.template"
    _inherit = "email.template"
    _description = 'Email Templates'

    def send_mail(self, cr, uid, template_id, res_id, force_send=False, context=None):
        """Generates a new mail message for the given template and record,
           and schedules it for delivery through the ``mail`` module's scheduler.

           :param int template_id: id of the template to render
           :param int res_id: id of the record to render the template with
                              (model is taken from the template)
           :param bool force_send: if True, the generated mail.message is
                immediately sent after being created, as if the scheduler
                was executed for this message only.
           :returns: id of the mail.message that was created
        """
        if context is None:
            context = {}
        mail_mail = self.pool.get('mail.mail')
        ir_attachment = self.pool.get('ir.attachment')
        invoice_obj = self.pool.get('account.invoice')
        partner_obj = self.pool.get('res.partner')
        recipient_ids = []

        # create a mail_mail based on values, without attachments
        values = self.generate_email(cr, uid, template_id, res_id, context=context)
        if not values.get('email_from'):
            raise osv.except_osv(_('Warning!'),_("Sender email is missing or empty after template rendering. Specify one to deliver your message"))
        # process email_recipients field that is a comma separated list of partner_ids -> recipient_ids
        # NOTE: only usable if force_send is True, because otherwise the value is
        # not stored on the mail_mail, and therefore lost -> fixed in v8
        if 'recipient_ids'in context.keys():
            recipient_ids = context['recipient_ids']

        email_recipients = values.pop('email_recipients', '')
        if email_recipients:
            for partner_id in email_recipients.split(','):
                if partner_id:  # placeholders could generate '', 3, 2 due to some empty field values
                    recipient_ids.append(int(partner_id))

        attachment_ids = values.pop('attachment_ids', [])
        attachments = values.pop('attachments', [])
        msg_id = mail_mail.create(cr, uid, values, context=context)
        mail = mail_mail.browse(cr, uid, msg_id, context=context)

        message_obj = self.pool.get('mail.message')
        for pid in recipient_ids:
            message_obj.write(cr, uid, [mail.mail_message_id.id], {'partner_ids': [(4, pid)]}, None)

        # manage attachments
        for attachment in attachments:
            attachment_data = {
                'name': attachment[0],
                'datas_fname': attachment[0],
                'datas': attachment[1],
                'res_model': 'mail.message',
                'res_id': mail.mail_message_id.id,
            }
            context.pop('default_type', None)
            attachment_ids.append(ir_attachment.create(cr, uid, attachment_data, context=context))
        if attachment_ids:
            values['attachment_ids'] = [(6, 0, attachment_ids)]
            mail_mail.write(cr, uid, msg_id, {'attachment_ids': [(6, 0, attachment_ids)]}, context=context)

        if force_send:
            mail_mail.send(cr, uid, [msg_id], recipient_ids=recipient_ids, context=context)
        return msg_id

vmi_email_template()


class vmi_mail_mail(osv.osv):
    _name = "mail.mail"
    _inherit = "mail.mail"

    def send_get_mail_body(self, cr, uid, mail, partner=None, context=None):
        return mail.body_html


class vmi_res_partner(osv.osv):
    """Add notification field to res.partner"""
    _name = "res.partner"
    _inherit = "res.partner"
    _columns = {
        'notification': fields.boolean('Email Notification for Invoice', help="Check this box to enable email notifications for invoices"),
        'audit_notification': fields.boolean('Email Notification for Auditing', help="Check this box to enable email notifications for auditing")
    }

vmi_res_partner()


class account_invoice_allocate(osv.osv_memory):
    """
    This wizard will allocate the all the selected invoices to matched account
    """

    _name = "account.invoice.allocate"
    _description = "Allocate the selected invoices to accounts"

    def invoice_allocate(self, cr, uid, ids, context=None):
        wf_service = netsvc.LocalService('workflow')
        if context is None:
            context = {}
        account_invoice_obj = self.pool.get('account.invoice')
        #valid_ids = []
        data_inv = self.pool.get('account.invoice').read(cr, uid, context['active_ids'], ['state'], context=context)

        for record in data_inv:
            if record['state'] != 'vendor_approved':
                raise osv.except_osv(_('Warning!'), _("Selected invoice(s) cannot be allocated as they are not in 'Vendor Approved' state."))
            account_invoice_obj.prepare_to_pay(cr, uid, record['id'])

        return {'type': 'ir.actions.act_window_close'}

account_invoice_allocate()


class account_invoice_calculate(osv.osv_memory):
    """
    This wizard will allocate the all the selected invoices to matched account
    """

    _name = "account.invoice.calculate"
    _description = "Calculate the service fee based on selected invoiced"

    def invoice_calculate(self, cr, uid, ids, context=None):
        if context is None:
            context = {}
        account_invoice_obj = self.pool.get('account.invoice')
        product_category_obj = self.pool.get('product.category')
        stock_location_obj = self.pool.get('stock.location')
        account_account_obj = self.pool.get('account.account')
        account_invoice_account_line_obj = self.pool.get('account.invoice.account.line')
        #account = account_account_obj.search(cr, uid, [('category_ids', 'in', [22]), ('location_ids', 'in', [58])])
        #Get id of category "Delivery Fee"
        category_delivery = product_category_obj.search(cr, uid, [('name', '=', 'Delivery Fee')])
        data_inv = account_invoice_obj.browse(cr, uid, context['active_ids'], context=context)
        invoice_delivery = []
        category_sum = {}
        location_ratio = {}
        #Check if selections are valid, record service fee invoice and calculate sum for each category
        for record in data_inv:
            if record.state not in ['vendor_approved', 'ready']:
                raise osv.except_osv(_('Warning!'), _("Selected invoice(s) cannot be allocated as they are not in 'Vendor Approved' state."))
            #found invoice for service fee
            if record.category_id.id == category_delivery[0]:
                invoice_delivery.append(record.id)
                '''for item in record.invoice_line:
                    item_info = str(item.product_id.name).split('-')
                    if len(item_info) == 3:
                        invoice_delivery.append({'id': record.id, 'line_id': item.id, 'category': item_info[0]})'''
            #found normal invoice
            elif record.category_id.id in category_sum.keys():
                category_sum[record.category_id.id] += record.amount_total
            else:
                category_sum[record.category_id.id] = record.amount_total

        if len(invoice_delivery) == 0:
            raise osv.except_osv(_('Warning!'), _('Please make sure to select at least one "Service Fee Invoice"!'))

        #Calculate ratio
        for record in data_inv:
            if record.category_id.id in category_sum.keys():
                location_ratio[(record.category_id.id, record.location_id.location_id.id)] = record.amount_total/category_sum[record.category_id.id]

        #Match accounts
        #account_ids = account_account_obj.search(cr, uid, [], None)
        #accounts = account_account_obj.browse(cr, uid, account_ids, None)
        invoices = account_invoice_obj.browse(cr, uid, invoice_delivery)
        for invoice in invoices:
            values = []
            for line in invoice['invoice_line']:
                account_amount = {}
                line_info = str(line.product_id.name).split('-')
                line_category = product_category_obj.search(cr, uid, [('name', '=', line_info[0])])
                for cate_loc in location_ratio.keys():
                    account = account_account_obj.search(cr, uid, [('category_ids', 'in', category_delivery), ('location_ids', 'in', [cate_loc[1]])])
                    if line_category[0] == cate_loc[0]:
                        amount = location_ratio[cate_loc]*line.price_subtotal
                        if account[0] in account_amount.keys():
                            account_amount[account[0]] += amount
                        else:
                            account_amount[account[0]] = amount
                for key in account_amount.keys():
                    values.append({'invoice_id': invoice['id'], 'account_id': key, 'total': account_amount[key]})
            if len(values)>0:
                for value in values:
                    account_line = account_invoice_account_line_obj.create(cr, uid, value, None)
                change_state = self.write(cr, uid, invoice['id'], {'state': 'ready'}, None)

                    #account_amount.append({'invoice_id': invoice['id'], 'account_id': account[0], 'total': amount})
            '''for account in accounts:
                for category in account.category_ids:
                    if category.id == category_delivery[0]:
                        for location in account.location_ids:
                            if location in location_ratio:'''

        return {'type': 'ir.actions.act_window_close'}

account_invoice_allocate()

class account_invoice_account_line(osv.osv):
    _name = 'account.invoice.account.line'
    _description = 'Account Line'
    _columns = {
        'account_id': fields.many2one('account.account', 'Account', required=True, help="This account related to the selected invoice"),
        'invoice_id': fields.many2one('account.invoice', 'Invoice Reference', ondelete='cascade', select=True),
        'items': fields.integer('Total Items'),
        'total': fields.float('Total Amount', digits_compute=dp.get_precision('Account'))
    }

account_invoice_account_line()


class vmi_account_account(osv.osv):
    _name = 'account.account'
    _inherit = 'account.account'
    _columns = {
        'location_ids': fields.many2many('stock.location', 'account_account_location_rel', 'account_id', 'location_id'),
        'category_ids': fields.many2many('product.category', 'account_account_category_rel', 'account_id', 'category_id'),
        'product_ids': fields.many2many('product.product', 'account_account_product_rel', 'account_id', 'product_id')
    }

vmi_account_account()