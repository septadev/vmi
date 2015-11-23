import logging
import time
import sys
import os
import random
import base64
from datetime import date
from ftplib import FTP

from openerp.osv import osv
from openerp.osv import fields
from openerp import netsvc
from openerp.tools.translate import _
import openerp.addons.decimal_precision as dp
from openerp.tools.config import configmanager

_logger = logging.getLogger(__name__)


def get_config():
    # get configs
    result = {}
    command = sys.argv
    if '-c' in command:
        config_file = command[command.index('-c') + 1]
        config = configmanager()
        config.parse_config(['-c', config_file])
        result['db'] = config.options['client_db']
        result['ap_file'] = config.options['ap_file']
        result['ap_ftp'] = config.options['ap_ftp']
        result['ap_ftp_path'] = config.options['ap_ftp_path']
        result['ap_ftp_username'] = config.options['ap_ftp_username']
        result['ap_ftp_password'] = config.options['ap_ftp_password']
    else:
        raise Exception("Please specify the config file")
    return result


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


class vmi_product_product(osv.osv):
    """Override of product.product, add two fields and make default_code unique"""
    _name = 'product.product'
    _inherit = 'product.product'
    _columns = {
        'vendor_part_number': fields.char('Vendor P/N', size=128, translate=False, required=False, readonly=False,
                                          select=True, help="Vendor's part number"),
        'default_code': fields.char('SEPTA P/N', size=64, translate=False, required=False, readonly=False, select=True,
                                    help="Septa's part number"),
    }
    _sql_constraints = [
        ('default_code_unique', 'unique (default_code)', 'SEPTA P/N must be unique!')
    ]


vmi_product_product()


class vmi_product_category(osv.osv):
    """Override of product.product, add 'code' for creating invoice number"""
    _name = 'product.category'
    _inherit = 'product.category'
    _columns = {
        'code': fields.char('Category Code', size=2, help="'code' for creating invoice number")
    }


vmi_product_category()


class vmi_product_pricelist_item(osv.osv):
    """
    Override of product.pricelist.item and make price discount 6-digit decimal pricision
    """
    _name = 'product.pricelist.item'
    _inherit = 'product.pricelist.item'
    _columns = {
        'price_discount': fields.float('Price Discount', digits=(16, 6)),
    }


vmi_product_pricelist_item()


class vmi_stock_location(osv.osv):
    """Override of stock.location"""
    _name = 'stock.location'
    _inherit = 'stock.location'
    _columns = {
        'code': fields.char('Location Code', size=2, help="code' for creating invoice number")
    }


vmi_stock_location()


class vmi_stock_move(osv.osv):
    """Override of stock.move"""
    _name = 'stock.move'
    _inherit = 'stock.move'
    _columns = {
        'vendor_id': fields.many2one('res.partner', 'Vendor', required=False, readonly=True, help="Vendor's id"),
        'audit': fields.boolean('Audit', help="Set True if a move need to be audit"),
        'audit_fail': fields.boolean('Failed Audit', help="Set True if the product failed the audit"),
        'audit_overwritten': fields.boolean('Audit Overwritten', help="Set True if the product overwritten by manager"),
        'invoice_status': fields.selection([
                                               ("invoiced", "Invoiced"),
                                               ("2binvoiced", "To Be Invoiced"),
                                               ("none", "Not Applicable")], "Invoice Control",
                                           select=True, required=True, readonly=True),
    }
    _defaults = {
        'audit': False,
        'audit_fail': False,
        'audit_overwritten': False,
        'scrapped': False,
        'invoice_status': '2binvoiced',
    }
    _order = 'date desc'

    def action_flag_audit(self, cr, uid, vals, context=None):
        """
        flag 10% of total lines in one packaging slip.
        @param self:
        @param cr: database cursor
        @param uid: user id
        @param vals: parsed result
        @param context: context
        """
        result = []
        stock_picking_obj = self.pool.get('stock.picking')
        if 'parse_result' in vals:
            # get all picking id
            picking_ids = [picking_id['picking_id'] for picking_id in vals['parse_result']['stock_picking']]
            for picking in stock_picking_obj.browse(cr, uid, picking_ids):
                move_ids = [line.id for line in picking.move_lines]
                # make sure numbers to flag is at least 10% of total lines and get how many moves should be marked
                num_to_flag = int(len(move_ids) * 0.1) if int(len(move_ids) * 0.1) == len(move_ids) * 0.1 else int(
                    len(move_ids) * 0.1) + 1
                # randomly select moves
                result += random.sample(move_ids, num_to_flag)

            # mark the line and the pickings to be audited
            if result:
                self.write(cr, uid, result, {'audit': True}, None)
                stock_picking_obj.write(cr, uid, picking_ids, {'contains_audit': 'yes'}, None)

        return result

    def action_audit(self, cr, uid, ids, quantity, location, context=None):
        """
        Audit processing by storekeeper
        :param cr: database cursor
        :param uid: user id
        :param ids: Stock.move id
        :param quantity: quantity recieved
        :param location: warehouse location
        :param context:
        :return:
        """
        if context is None:
            context = {}

        # audit quantity should be less than or equal to shipped quantity.
        if quantity < 0:
            raise osv.except_osv(_('Warning!'), _('Please provide a non-negative quantity.'))

        stock_picking_obj = self.pool.get('stock.picking')
        partner_obj = self.pool.get('res.partner')
        template_obj = self.pool.get('email.template')

        # check which manager need a notification
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
            # for move in self.browse(cr, uid, ids, context=context):
            move_qty = move.product_qty
            uos_qty = quantity / move_qty * move.product_uos_qty
            # audit fail
            if move_qty != quantity:
                # calculate difference
                difference_quant = move_qty - quantity
                difference_uos = difference_quant * move.product_uos_qty

                # get which storekeeper perform this audit and write note
                storekeeper = user_obj.browse(cr, uid, uid).login
                note = "Missing %s product(s). Audit conducted at %s by %s." % (
                    difference_quant, str(time.strftime('%Y-%m-%d %H:%M:%S')), storekeeper.capitalize())

                # create a new move that record failed items, these items won't be invoiced
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

                # update currenct move and picking
                self.write(cr, uid, ids, {'product_qty': quantity, 'note': note, 'audit': False, 'state': 'done'}, context)
                res += [new_move]
                stock_picking_obj.change_picking_audit_result(cr, uid, move.picking_id.id, False, None)

                # post a message of failed audit
                product_obj = self.pool.get('product.product')
                for product in product_obj.browse(cr, uid, [move.product_id.id], context=context):
                    if move.picking_id:
                        uom = product.uom_id.name if product.uom_id else ''
                        message = _("%s %s %s has been moved to <b>Failed Audits</b>.") % (quantity, uom, product.name)
                        move.picking_id.message_post(body=message)

                # find template id and send email
                if len(recipient_ids) > 0:
                    context['recipient_ids'] = recipient_ids
                    template_id = template_obj.search(cr, uid, [('name', '=', 'Notification for Audit Fail')])
                    if template_id:
                        mail = template_obj.send_mail(cr, uid, template_id[0], move.id, True, context=context)
                    else:
                        raise osv.except_osv(_('Error!'), _(
                            'No Email Template Found, Please configure a email template under Email tab and named "Notification for Audit Fail"'))
            # pass the audit
            else:
                # get which storekeeper perform this audit and update the current move and picking
                storekeeper = user_obj.browse(cr, uid, uid).login
                note = "Audit conducted at %s by %s." % (
                    str(time.strftime('%Y-%m-%d %H:%M:%S')), storekeeper.capitalize())
                self.write(cr, uid, ids, {'audit': False, 'note': note, 'state': 'done'}, context=context)
                stock_picking_obj.change_picking_audit_result(cr, uid, move.picking_id.id, True, None)

        return res

    def action_audit_overwrite(self, cr, uid, ids, context=None):
        """
        Audit overwrite by manager
        :param cr: database cursor
        :param uid: user id
        :param ids: Stock.move id
        :param context: context
        :return:
        """
        if context is None:
            context = {}
        stock_picking_obj = self.pool.get('stock.picking')
        user_obj = self.pool.get('res.users')

        move = self.browse(cr, uid, ids[0], context=context)
        if move is not None:
            # set move to audit_overwritten
            manager = user_obj.browse(cr, uid, uid).login
            note = "Audit overwritten at %s by %s." % (str(time.strftime('%Y-%m-%d %H:%M:%S')), manager.capitalize())
            _logger.info("Audit overwritten at %s by %s." % (
                str(time.strftime('%Y-%m-%d %H:%M:%S')), manager.capitalize()))
            self.write(cr, uid, ids, {'audit': False, 'note': note, 'audit_overwritten': True, 'state': 'done'}, context=context)
            #change the audit status of picking
            stock_picking_obj.change_picking_audit_result(cr, uid, move.picking_id.id, True, None)

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
                                               ('fail', 'Fail Audit'),
                                               ('overwritten', 'Audit Overwritten')], 'Contains Audit',
                                           help="Specify whether this package contains Audited goods, If contains, Pass or Fail"),
        'date_done': fields.date('Delivery Date', help="Date of Completion",
                                 states={'done': [('readonly', True)], 'cancel': [('readonly', True)]})
    }
    _sql_constraints = [
        ('origin_uniq', 'unique(origin, partner_id)', 'Packaging Slip Number must be unique per Company!'),
    ]


    def action_flag_audit_original_by_mike(self, cr, uid, vals, context=None):

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
            # get remained_audit and last record
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
            # _logger.debug('<action_flag_audit> remained_audit: %s , last_record: %s', remained_audit, last_record)
            if 'parse_result' in vals:
                p = vals.get('parse_result')
                # get newly uploaded record and order by the product quantity
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
                    """ % (pid, last_record)
                    cr.execute(sql_req)
                    sql_res = cr.dictfetchall()
                    # _logger.debug('<action_flag_audit> select result: %s', str(sql_res))
                    total_qty = sum(item['product_qty'] for item in sql_res)
                    # _logger.debug('<action_flag_audit> total_qty: %s', total_qty)
                    last_record = max(id['id'] for id in sql_res)

                    if sql_res > 0:
                        # calculate number of product to be flagged this time and get them
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

# don't use now
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

    # Can be removed???
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
        audit_location = location_obj.search(cr, uid,
                                             [('location_id', '=', parent_location), ('name', 'like', 'Audit')])
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
            # res.update({'location_id': scrpaed_location_ids[0]})
            # else:
            # res.update({'location_id': False})
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

    def audit_overwrite(self, cr, uid, ids, context=None):
        """ To Overwrite to be audited products
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
            move_obj.action_audit_overwrite(cr, uid, move_ids, context)
        return {'type': 'ir.actions.client', 'tag': 'reload'}


stock_move_audit()


class vmi_stock_picking(osv.osv):
    _name = 'stock.picking'
    _inherit = 'stock.picking'
    _table = "stock_picking"
    # _order = 'id desc'

    _columns = {
        'contains_audit': fields.selection([('no', 'No Audit'),
                                            ('yes', 'Auditing'),
                                            ('pass', 'Pass Audit'),
                                            ('fail', 'Fail Audit'),
                                            ('overwritten', 'Audit Overwritten')], 'Contains Audit',
                                           help="Specify whether this package contains Audited goods, If contains, Pass or Fail"),
        'date_done': fields.date('Delivery Date', help="Date of Completion",
                                 states={'done': [('readonly', True)], 'cancel': [('readonly', True)]})
    }

    _defaults = {
        'contains_audit': 'no'
    }

    def change_picking_audit_result(self, cr, uid, ids, audit, context=None):
        """
        When an audit performed, call this function to change the audit state in the picking slip
        :param cr:
        :param uid:
        :param ids: picking_id to change
        :param context:
        :return: changed ids
        """
        picking = self.browse(cr, uid, ids, None)
        if picking.contains_audit == u'yes':
            # found a audit_fail move
            if audit is False:
                self.write(cr, uid, ids, {'contains_audit': 'fail'})
            else:
                # check if there is other move(s) need to be audited
                for move in picking.move_lines:
                    if move.audit is True:
                        return picking.contains_audit
                # there is no auditing move, check if there is overwritten move
                for move in picking.move_lines:
                    if move.audit_overwritten is True:
                        self.write(cr, uid, ids, {'contains_audit': 'overwritten'})
                        return picking.contains_audit
                # all pass
                self.write(cr, uid, ids, {'contains_audit': 'pass'})

        return picking.contains_audit

    def action_invoice_create(self, cr, uid, ids, journal_id=False,
                              group=True, type='in_invoice', context=None):
        """
        To create draft invoice from picking slips
        :param cr: database cursor
        :param uid: user id
        :param ids: packaging slips to generate invoices
        :param journal_id: if specify journal, use this
        :param group: if dont want to group products, use this
        :param type: in_invoice
        :param context:
        :return:
        """
        if context is None:
            context = {}
        invoice_obj = self.pool.get('account.invoice')
        invoice_line_obj = self.pool.get('account.invoice.line')
        partner_obj = self.pool.get('res.partner')
        stock_move_obj = self.pool.get('stock.move')
        invoices_group = {}
        res = {}
        inv_type = type
        group = True

        # get journal_id
        if not journal_id:
            journal_id = self.search(cr, uid, [('type', '=', 'purchase'), ('name', '=', 'Purchase Journal')], context)

        # check whether there is product to be audited
        for picking in self.browse(cr, uid, ids, context=context):
            if picking.invoice_state != '2binvoiced':
                raise osv.except_osv(_('error!'), _("There is at least one shipment has been invoiced"))
            if picking.contains_audit == 'yes':
                raise osv.except_osv(_('error!'), _("There is at least one product to be audited"))

        # Create Invoices
        for picking in self.browse(cr, uid, ids, context=context):
            # Get the vendor's name
            partner = self._get_partner_to_invoice(cr, uid, picking, context=context)
            if isinstance(partner, int):
                partner = partner_obj.browse(cr, uid, [partner], context=context)[0]
            if not partner:
                raise osv.except_osv(_('Error, no partner!'),
                                     _('Please put a partner on the picking list if you want to generate invoice.'))
            if not inv_type:
                inv_type = self._get_invoice_type(picking)

            # Get the vendor's pricelist
            pricelist_id = partner.property_product_pricelist_purchase.id

            for move_line in picking.move_lines:
                # only invoice those un-invoiced lines
                if move_line.invoice_status == '2binvoiced':
                    _logger.debug('<action_invoice_create> invoices_group: %s', str(invoices_group))
                    invoice_name = '-'.join([str(partner.name), str(picking.location_dest_id.name),
                                             str(move_line.product_id.categ_id.name)])
                    # create new invoice
                    if invoice_name not in invoices_group.keys():
                        # generate invoice number:
                        """ VMI +
                            two digit represent year of the invoice+
                            two digit represent month of the invoice+
                            three digit of sequence numbers +
                            two digit represent vendor id +
                            two digit represent location id +
                            two digit represent product category id"""
                        context['invoice_name'] = invoice_name
                        context['invoice_category'] = move_line.product_id.categ_id.id
                        context['invoice_location'] = picking.location_dest_id.id
                        invoice_date = context['date_inv'].split('-')
                        internal_number = 'VMI' + \
                                          invoice_date[0][2:] + \
                                          invoice_date[1]
                        seq = ''
                        # check if there is a sequence number created in the same date
                        old_seq = invoice_obj.search(cr, uid, [('internal_number', 'like', internal_number)],
                                                     order='internal_number')
                        # if found old sequence number, add 1
                        if old_seq:
                            old_num = invoice_obj.read(cr, uid, old_seq[-1], ['internal_number'])
                            seq = str(int(old_num['internal_number'][7:10]) + 1)
                        # append the sequence, partner code, location code, category code
                        internal_number += seq.rjust(3, '0') + \
                                           partner.code.rjust(2, '0') + \
                                           picking.location_dest_id.location_id.code.rjust(2, '0') + \
                                           move_line.product_id.categ_id.code.rjust(2, '0')

                        context['internal_number'] = internal_number

                        # prepare and create invoice
                        invoice_vals = self._prepare_invoice(cr, uid, picking, partner, inv_type, journal_id,
                                                             context=context)
                        invoice_id = invoice_obj.create(cr, uid, invoice_vals, context=context)
                        invoices_group[invoice_name] = invoice_id

                    # invoice already existed then add current move information to this invoice
                    elif group:
                        invoice_id = invoices_group[invoice_name]
                        invoice = invoice_obj.browse(cr, uid, invoice_id)
                        invoice_vals_group = self._prepare_invoice_group(cr, uid, picking, partner, invoice,
                                                                         context=context)
                        invoice_obj.write(cr, uid, [invoice_id], invoice_vals_group, context=context)

                    res[picking.id] = invoice_id
                    invoice_vals['pricelist_id'] = pricelist_id

                    # skip lines that has special status, rarely happen
                    if move_line.state == 'cancel':
                        continue
                    if move_line.scrapped:
                        continue

                    # create invoices
                    vals = self._prepare_invoice_line(cr, uid, group, picking, move_line,
                                                      invoice_id, invoice_vals, context=context)
                    if vals:
                        invoice_line_id = invoice_line_obj.create(cr, uid, vals, context=context)
                        self._invoice_line_hook(cr, uid, move_line, invoice_line_id)
                        # Set move_line's invoiced states to True
                        stock_move_obj.write(cr, uid, move_line.id, {'invoice_status': 'invoiced'})

            invoice_obj.button_compute(cr, uid, [invoice_id], context=context,
                                       set_total=(inv_type in ('in_invoice', 'in_refund')))
            # Change state
            self.write(cr, uid, [picking.id], {'invoice_state': 'invoiced', }, context=context)
            self._invoice_hook(cr, uid, picking, invoice_id)

        self.write(cr, uid, res.keys(), {'invoice_state': 'invoiced', }, context=context)

        return res


    def _prepare_invoice_line(self, cr, uid, group, picking, move_line, invoice_id,
                              invoice_vals, context=None):
        """ Rewrite this function to adjust the pricelist

            Builds the dict containing the values for the invoice line
            @param group: True or False
            @param picking: picking object
            @param: move_line: move_line object
            @param: invoice_id: ID of the related invoice
            @param: invoice_vals: dict used to created the invoice
            @return: dict that will be used to create the invoice line
        """
        product_pricelist = self.pool.get('product.pricelist')
        pricelist_id = invoice_vals['pricelist_id']

        name = picking.name
        origin = move_line.picking_id.name or ''
        if move_line.picking_id.origin:
            origin += ':' + move_line.picking_id.origin

        # Get account id
        if invoice_vals['type'] in ('out_invoice', 'out_refund'):
            account_id = move_line.product_id.property_account_income.id
            if not account_id:
                account_id = move_line.product_id.categ_id. \
                    property_account_income_categ.id
        else:
            account_id = invoice_vals['account_id']

        # if there is an active pricelist for current supplier, adjust the product's price
        if pricelist_id:
            price = product_pricelist.price_get(cr, uid, [pricelist_id],
                                                move_line.product_id.id,
                                                move_line.product_uos_qty or move_line.product_qty,
                                                invoice_vals['partner_id'] or False)[pricelist_id]
        else:
            price = move_line.product_id.list_price

        if not price:
            price = move_line.product_id.list_price

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
            'origin': (invoice.origin or '') + ', ' + (picking.name or '') + (
                picking.origin and (':' + picking.origin) or ''),
            'comment': (comment and (invoice.comment and invoice.comment + "\n" + comment or comment)) or (
                invoice.comment and invoice.comment or ''),
            'date_due': context.get('date_due', False),
            'date_inv': context.get('date_inv', False),
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
            'date_due': context.get('date_due', False),
            'date_invoice': context.get('date_inv', False),
            'company_id': picking.company_id.id,
            'user_id': uid,
            'category_id': context['invoice_category'],
            'location_id': context['invoice_location'],
            'internal_number': context['internal_number'],
        }
        cur_id = self.get_currency_id(cr, uid, picking)
        if cur_id:
            invoice_vals['currency_id'] = cur_id
        if journal_id:
            invoice_vals['journal_id'] = journal_id
        return invoice_vals


vmi_stock_picking()


class vmi_stock_invoice_onshipping(osv.osv):
    _name = 'stock.invoice.onshipping'
    _inherit = 'stock.invoice.onshipping'
    _columns = {
        'due_date': fields.date('Due Date'),
    }
    # Inherit vmi_stock_invoice_onshipping, let the user select invoice date.

    def create_invoice(self, cr, uid, ids, context=None):
        """
        controller to grab data from stock.picking and create draft invoice
        :param cr: a database cursor
        :param uid:  user id
        :param ids: picking ids
        :param context:
        :return:
        """
        if context is None:
            context = {}
        picking_pool = self.pool.get('stock.picking')

        # get user input, specially invoice_date
        onshipdata_obj = self.read(cr, uid, ids, ['journal_id', 'group', 'invoice_date'])
        if context.get('new_picking', False):
            onshipdata_obj['id'] = onshipdata_obj.new_picking
            onshipdata_obj[ids] = onshipdata_obj.new_picking

        # pass invoice date, we don't use due date but the program requires it
        context['date_inv'] = onshipdata_obj[0]['invoice_date']
        context['date_due'] = context['date_inv']

        # get invoice type
        active_ids = context.get('active_ids', [])
        active_picking = picking_pool.browse(cr, uid, context.get('active_id', False), context=context)
        inv_type = picking_pool._get_invoice_type(active_picking)
        context['inv_type'] = inv_type
        if isinstance(onshipdata_obj[0]['journal_id'], tuple):
            onshipdata_obj[0]['journal_id'] = onshipdata_obj[0]['journal_id'][0]

        # call function to create invoice
        res = picking_pool.action_invoice_create(cr, uid, active_ids,
                                                 journal_id=onshipdata_obj[0]['journal_id'],
                                                 group=onshipdata_obj[0]['group'],
                                                 type=inv_type,
                                                 context=context)
        return res


class stock_audit_overwrite(osv.osv_memory):
    """
    This wizard will overwrite all selected stock moves
    """

    _name = "stock.audit.overwrite"
    _description = "Overwrite All Incoming Products"

    def overwrite_all(self, cr, uid, ids, context=None):
        if context is None:
            context = {}

        stock_move_obj = self.pool.get('stock.move')
        data_inv = self.pool.get('stock.move').read(cr, uid, context['active_ids'], ['audit'], context=context)

        for record in data_inv:
            # check if the selected product needs audit
            if not record['audit']:
                raise osv.except_osv(_('Warning!'), _(
                    "Selected product(s) have been audited"))
            stock_move_obj.action_audit_overwrite(cr, uid, [record['id']], context)

        return {'type': 'ir.actions.act_window_close'}


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
                                      ('sent', 'AP File Generated'),
                                      ('paid', 'Invoice Paid'),
                                      ('cancel', 'Cancelled'),
                                  ], 'Status', select=True, readonly=True, track_visibility='onchange',
                                  help=' * The \'Draft\' status is used when a user is encoding a new and unconfirmed Invoice, waiting for confirmation by manager. \
            \n* The \'Septa Manager Approved\' status indicates that this invoice has been approved by manager and waiting for confirmation by vendor. \
            \n* The \'Vendor Denied\' status indicates that this invoice has been denied by vendor. Manager need to review it and re-validate. \
            \n* The \'Vendor Approved\' status indicates that this invoice has been approved by vendor. \
            \n* The \'Ready for AP\' status is set automatically when the account information is attached. \
            \n* The \'AP File Sent\' status indicates that an ap file has been generated and uploaded to FTP server. \
            \n* The \'Cancelled\' status is used when user cancel invoice.'),
        'invoice_line': fields.one2many('account.invoice.line', 'invoice_id', 'Invoice Lines',
                                        states={'ready': [('readonly', True)],
                                                'vendor_approved': [('readonly', True)]}),
        'account_line': fields.one2many('account.invoice.account.line', 'invoice_id', 'Account Lines',
                                        states={'ready': [('readonly', True)],
                                                'vendor_approved': [('readonly', True)]},
                                        help="Accounts will be used to pay for this invoice"),
        'location_id': fields.many2one('stock.location', 'Location', states={'vendor_approved': [('readonly', True)],
                                                                             'vendor_approved': [('readonly', True)]},
                                       select=True, track_visibility='always',
                                       help="Location that stocks the finished products in current invoice."),
        'category_id': fields.many2one('product.category', 'Category', states={'vendor_approved': [('readonly', True)],
                                                                               'vendor_approved': [('readonly', True)]},
                                       select=True, track_visibility='always',
                                       help="Select category for the current product"),
    }

    def action_move_create(self, cr, uid, ids, context=None):
        # rewrite this function to disabled the check_total feature
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
                self.write(cr, uid, [inv.id],
                           {'date_invoice': fields.date.context_today(self, cr, uid, context=context)}, context=ctx)
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
                    raise osv.except_osv(_('Error!'), _(
                        "Cannot create the invoice.\nThe related payment term is probably misconfigured as it gives a computed amount greater than the total invoiced amount. In order to avoid rounding issues, the latest line of your payment term must be of type 'balance'."))

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
            total, total_currency, iml = self.compute_invoice_totals(cr, uid, inv, company_currency, ref, iml,
                                                                     context=ctx)
            acc_id = inv.account_id.id

            name = inv['name'] or inv['supplier_invoice_number'] or '/'
            totlines = False
            if inv.payment_term:
                totlines = payment_term_obj.compute(cr,
                                                    uid, inv.payment_term.id, total, inv.date_invoice or False,
                                                    context=ctx)
            if totlines:
                res_amount_currency = total_currency
                i = 0
                ctx.update({'date': inv.date_invoice})
                for t in totlines:
                    if inv.currency_id.id != company_currency:
                        amount_currency = cur_obj.compute(cr, uid, company_currency, inv.currency_id.id, t[1],
                                                          context=ctx)
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

            line = map(lambda x: (0, 0, self.line_get_convert(cr, uid, x, part.id, date, context=ctx)), iml)

            line = self.group_lines(cr, uid, iml, line, inv)

            journal_id = inv.journal_id.id
            journal = journal_obj.browse(cr, uid, journal_id, context=ctx)
            if journal.centralisation:
                raise osv.except_osv(_('User Error!'),
                                     _(
                                         'You cannot create an invoice on a centralized journal. Uncheck the centralized counterpart box in the related journal from the configuration menu.'))

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
            self.write(cr, uid, [inv.id], {'move_id': move_id, 'period_id': period_id, 'move_name': new_move_name},
                       context=ctx)
            # Pass invoice in context in method post: used if you want to get the same
            # account move reference when creating the same invoice after a cancelled one:
            move_obj.post(cr, uid, [move_id], context=ctx)
        self._log_event(cr, uid, ids)
        return True

    def finalize_invoice_move_lines(self, cr, uid, invoice_browse, move_lines):
        '''res = []
        for line in move_lines:
            if line[2]['product_id']:
                res.append(line)
        return res'''
        return move_lines

    def invoice_validate(self, cr, uid, ids, context=None):
        """
        When button "Validate" clicked, call this function to change the state and send notification if needed
        :param cr: database cursor
        :param uid: user id
        :param ids: invoice id
        :param context:
        :return:
        """
        if context is None:
            context = {}
        invoice = self.browse(cr, uid, ids, context)[0]

        # Check which partner need a notification
        child_ids = invoice.partner_id.child_ids
        recipient_ids = []
        for child in child_ids:
            if child.notification:
                recipient_ids.append(int(child.id))
        # Change state
        res = self.write(cr, uid, ids, {'state': 'manager_approved'}, context=context)

        # Send email if found recipient
        if res and len(recipient_ids) > 0:
            context['recipient_ids'] = recipient_ids

            # get email template, render it and send it
            template_obj = self.pool.get('email.template')
            template_id = template_obj.search(cr, uid, [('name', '=', 'Notification for Septa Manager Approved')])
            if template_id:
                mail = template_obj.send_mail(cr, uid, template_id[0], ids[0], True, context=context)
            else:
                raise osv.except_osv(_('Error!'), _(
                    'No Email Template Found, Please configure a email template under Email tab and named "Notification for Septa Manager Approved"'))
        return True

    def invoice_vendor_approve(self, cr, uid, ids, context=None):
        """
        When receiving a vendor approved invoice, call this function to change the state and send notification if needed
        :param cr: database cursor
        :param uid: user id
        :param ids: invoice id
        :param context:
        :return:
        """
        if context is None:
            context = {}

        # check which manager need a notification
        recipient_ids = []
        partner_obj = self.pool.get('res.partner')
        admin_id = partner_obj.search(cr, uid, [('name', '=', 'SEPTA Admin')])
        admin = partner_obj.browse(cr, uid, admin_id, context=None)[0]
        child_ids = admin.child_ids
        for child in child_ids:
            if child.notification:
                recipient_ids.append(int(child.id))

        # change state
        res = self.write(cr, uid, [int(ids)], {'state': 'vendor_approved'}, context=context)

        # Send email if found recipient
        if res and len(recipient_ids) > 0:
            context['recipient_ids'] = recipient_ids
            template_obj = self.pool.get('email.template')
            template_id = template_obj.search(cr, uid, [('name', '=', 'Notification for Vendor Approved')])
            if template_id:
                mail = template_obj.send_mail(cr, uid, template_id[0], int(ids), True, context=context)
            else:
                raise osv.except_osv(_('Error!'), _(
                    'No Email Template Found, Please configure a email template under Email tab and named "Notification for Vendor Approved"'))
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

        # make "ids" a list ids (required if using existing method in any model)
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

            # Send email if found recipient
            if res and len(recipient_ids) > 0:
                context['recipient_ids'] = recipient_ids
                template_obj = self.pool.get('email.template')
                template_id = template_obj.search(cr, uid, [('name', '=', 'Notification for Vendor Denied')])
                if template_id:
                    mail = template_obj.send_mail(cr, uid, template_id[0], ids[0], True, context=context)
                else:
                    raise osv.except_osv(_('Error!'), _(
                        'No Email Template Found, Please configure a email template under Email tab and named "Notification for Vendor Denied"'))
        return True

    def prepare_to_pay(self, cr, uid, ids, context=None):
        """
        Allocate the accounts to each invoice based on the location, category and even product
        :param cr:
        :param uid: user id
        :param ids: invoice id to pay
        :param context:
        :return:
        """
        account_invoice_account_line_obj = self.pool.get('account.invoice.account.line')
        account_rule_line_obj = self.pool.get('account.account.rule.line')
        if not isinstance(ids, int):
            ids = ids[0]
        invoice = self.browse(cr, uid, ids, None)

        # Get all rule lines find if there is a rule for product
        products = {}
        product_rules_id = account_rule_line_obj.search(cr, uid, [('product_id', '!=', None)], None)
        if product_rules_id:
            product_rules = account_rule_line_obj.browse(cr, uid, product_rules_id, None)
            for rule in product_rules:
                products[rule.product_id.id] = rule.account_id

        # match location and category find account(s)
        account_rules_id = account_rule_line_obj.search(cr, uid,
                                                        [('location_id', '=', invoice.location_id.location_id.id),
                                                         ('category_id', '=', invoice.category_id.id)], None)
        if account_rules_id:
            account_rules = account_rule_line_obj.browse(cr, uid, account_rules_id, None)
        else:
            account_rules = []

        accounts = {}
        total = 0
        for line in invoice['invoice_line']:
            # Check if special product exist
            if line.product_id.id in products.keys():
                if products[line.product_id.id] in accounts.keys():
                    accounts[products[line.product_id.id]] += line.price_subtotal
                else:
                    accounts[products[line.product_id.id]] = line.price_subtotal
            # no special product, sum the price
            else:
                total += line.price_subtotal

        # Match account and calculate total by ratio
        if total > 0 and account_rules:
            for rule in account_rules:
                if rule.account_id.id in accounts.keys():
                    accounts[rule.account_id.id] += total * rule.ratio
                else:
                    accounts[rule.account_id.id] = total * rule.ratio

        # Check if account line exists and the total
        if accounts:
            # compare invoice total and total after allocating account. if doesn't match, something wrong with the accounts
            account_total = sum(accounts.values())
            if abs(total - account_total) > 1:
                raise osv.except_osv(_('Error!'), _(
                    'Please check the accounts for location %s and category %s in "Account Rule Line" section'
                    % (invoice.location_id.name, invoice.category_id.name)))
            # check up the rounding issue
            elif abs(total - account_total) > 0.00001 and abs(total - account_total) < 1:
                accounts[rule.account_id.id] += (total - account_total)
        else:
            raise osv.except_osv(_('Error!'), _(
                'Please check the accounts for location %s and category %s in "Account Rule Line" section'
                % (invoice.location_id.name, invoice.category_id.name)))
        # create account line
        for account in accounts:
            account_invoice_account_line_obj.create(cr, uid, {'invoice_id': ids, 'account_id': account,
                                                              'total': accounts[account]}, None)
        self.write(cr, uid, ids, {'state': 'ready'}, None)

        return True

    def generate_ap_file(self, cr, uid, ids, context=None):
        """
        Generate ap file and upload to ftp server if needed, ap file is text file with strict layout
        :param cr: database cursor
        :param uid: user id
        :param ids: invoice ids
        :param context:
        :return: a dict contains (vendor_name, PO_number): gross amount
        """

        # Get AP default values and their PO numbers
        account_invoice_ap_obj = self.pool.get('account.invoice.ap')
        account_invoice_ap_po_obj = self.pool.get('account.invoice.ap.po')
        invoice_ap_id = account_invoice_ap_obj.search(cr, uid, [])
        invoice_ap = account_invoice_ap_obj.read(cr, uid, invoice_ap_id, [], context)
        for ap in invoice_ap:
            ap['po'] = {}
            po_numbers = account_invoice_ap_po_obj.read(cr, uid, ap['po_numbers'], [], context)
            for po in po_numbers:
                key = po['category_id'][1].split(' / ')[1]
                ap['po'][key] = po['po_number']


        # Check if file exist, rename it before generate a new one
        ap_config = get_config()
        if os.path.isfile(ap_config['ap_file']):
            today = date.today()
            os.rename(ap_config['ap_file'], ap_config['ap_file'][:-4] + '-' + str(today) + '.' +
                      str(random.randrange(0, 99, 2)) + ap_config['ap_file'][-4:])
        f = open(ap_config['ap_file'], 'w+')

        # positions for CG, IH, IL
        ih_fields = {
            'paying_entity': (1, 4),
            'control_date': (5, 12),
            'control_number': (13, 16),
            'invoice_sequence_number': (25, 30),
            'record_type': (37, 38),
            'vendor_number': (49, 58),
            'vendor_group': (59, 60),
            'invoice_number': (61, 76),
            'invoice_date': (77, 84),
            'gross_amount': (398, 412),
            'cm_dm': 504,
            'one_invoice': 506,
            # 'payment_due_date': (507, 514),
            'bank_payment_code': (536, 538),
            # 'gl_effective_date': (624, 631),
        }
        il_fields = {
            'paying_entity': (1, 4),
            'control_date': (5, 12),
            'control_number': (13, 16),
            'invoice_sequence_number': (25, 30),
            'line_number': (31, 36),
            'record_type': (37, 38),
            'vendor_number': (49, 58),
            'vendor_group': (59, 60),
            'invoice_number': (61, 76),
            'invoice_date': (77, 84),
            'project_company': (202, 205),
            'project_number': (206, 217),
            'expense_company': (247, 250),
            'expense_account': (251, 268),
            'expense_center': (269, 280),
            'expense_amount': (284, 298),
        }
        cg_fields = {
            'paying_entity': (1, 4),
            'control_date': (5, 12),
            'control_number': (13, 16),
            'record_type': (37, 38),
            'application_area': (51, 52),
            # 'gl_effective_date': (53, 60),
            'control_amount': (61, 75),
            'operator_id': (335, 340),
        }

        # get control date
        control_date = '%02d' % date.today().month + '%02d' % date.today().day + str(date.today().year)
        timedelta = 6 - date.today().isoweekday()
        gl_effective_date = '%02d' % date.today().month + '%02d' % (date.today().day + timedelta) + str(
            date.today().year)
        invoice_sequence_number = 1
        control_amount = 0

        header = ''
        ap_lines = ''
        '''
        # generate ruler
        for position in range(1, 820):
            if position % 5 == 0 and position % 10 != 0:
                header += '+'
            elif position % 10 == 0:
                header += str(position / 10 % 10)
            else:
                header += '-'
        ap_lines += header + '\n'
        '''
        # sort invoice ids by invoice number in ascending order
        invoices = self.read(cr, uid, ids, ['internal_number'])
        sorted_invoices = sorted(invoices, key=lambda k: k['internal_number'])
        sorted_ids = [line['id'] for line in sorted_invoices]

        # Initiate a dict for vendor and total
        po_total = {}

        # generate lines based on selected sorted invoices
        for invoice in self.browse(cr, uid, sorted_ids, context):
            # Get default value based on vendor
            default_values = filter(lambda ap: ap['vendor_id'][0] == invoice.partner_id.id, invoice_ap)[0]

            # Get correct type of invoice date
            i_date = invoice.date_invoice.split('-')
            invoice_date = i_date[1] + i_date[2] + i_date[0]
            line_total = 0
            line_number = 1
            il_lines = ''

            # for each account line, create a invoice line in this invoice header
            for account_line in invoice.account_line:
                # Generate dict for invoice line
                account = account_line.account_id.name.split('-')
                project_company = account[0]
                project_number = ''
                if len(account) == 5:
                    project_number = account[4]

                # adjust the line amount if there is rounding issue from %.4f to %.2f
                line_amount = account_line.total
                if line_number == len(invoice.account_line):
                    diff = round(invoice.amount_total, 2) - round(line_total+account_line.total, 2)
                    if diff != 0:
                        line_amount += diff

                il_values = {
                    'paying_entity': default_values['paying_entity'],
                    'control_date': control_date,
                    'control_number': default_values['control_number'],
                    'invoice_sequence_number': '{0:06d}'.format(invoice_sequence_number),
                    'line_number': '{0:06d}'.format(line_number),
                    'record_type': 'IL',
                    'vendor_number': default_values['vendor_number'].rjust(10, ' '),
                    'vendor_group': default_values['vendor_group_number'],
                    'invoice_number': invoice.number.encode('utf-8').rjust(16, ' '),
                    'invoice_date': invoice_date,
                    'project_company': project_company,
                    'project_number': project_number.rjust(12, ' '),
                    'expense_company': account[0],
                    'expense_account': account[1].rjust(18, ' '),
                    'expense_center': (account[2] + account[3]).rjust(12, ' '),
                    'expense_amount': (('%.2f' % line_amount).replace('.', '')).rjust(15, '0'),
                }

                il_lines += self._prepare_ap_line(il_fields, il_values) + '\r\n'
                line_number += 1
                line_total += round(line_amount, 2)

            # Generate invoice header dict based on all il values
            ih_values = {
                'paying_entity': default_values['paying_entity'],
                'control_date': control_date,
                'control_number': default_values['control_number'],
                'invoice_sequence_number': '{0:06d}'.format(invoice_sequence_number),
                'record_type': 'IH',
                'vendor_number': default_values['vendor_number'].rjust(10, ' '),
                'vendor_group': default_values['vendor_group_number'],
                'invoice_number': invoice.internal_number,
                'invoice_date': invoice_date,
                'gross_amount': format(line_total, '.2f').replace('.', '').rjust(15, '0'),
                'cm_dm': 'I',
                'one_invoice': '1',
                # 'payment_due_date': due_date,
                'bank_payment_code': default_values['bank_payment_code'],
                # 'gl_effective_date': gl_effective_date,
            }

            ap_lines += self._prepare_ap_line(ih_fields, ih_values) + '\r\n'
            invoice_sequence_number += 1
            ap_lines += il_lines
            control_amount += round(line_total, 2)
            # If this is a delivery fee invoice. get category name from each line
            if invoice.category_id.code == '07':
                for line in invoice.invoice_line:
                    category_name = line.product_id.name.split('-')[0]
                    if category_name in default_values['po']:
                        # Store vendor info (vendor name and po_number) and invoice total for AP use
                        if (invoice.partner_id.name, default_values['po'][category_name]) in po_total:
                            po_total[
                                (invoice.partner_id.name, default_values['po'][category_name])] += line.price_subtotal
                        else:
                            po_total[
                                (invoice.partner_id.name, default_values['po'][category_name])] = line.price_subtotal
            if invoice.category_id.name in default_values['po']:
                # Store vendor info (vendor name and po_number) and invoice total for AP use
                if (invoice.partner_id.name, default_values['po'][invoice.category_id.name]) in po_total:
                    po_total[(invoice.partner_id.name, default_values['po'][invoice.category_id.name])] += line_total
                else:
                    po_total[(invoice.partner_id.name, default_values['po'][invoice.category_id.name])] = line_total

        # Generate cg dict based on all invoice header
        cg_values = {
            'paying_entity': default_values['paying_entity'],
            'control_date': control_date,
            'control_number': default_values['control_number'],
            'record_type': 'CG',
            'application_area': default_values['application_code'],
            # 'gl_effective_date': gl_effective_date,
            'control_amount': format(control_amount, '.2f').replace('.', '').rjust(15, '0'),
            'operator_id': default_values['operator_id'],
        }
        ap_lines += self._prepare_ap_line(cg_fields, cg_values) + '\r\n'

        # Write data to a txt file
        f.write(ap_lines)
        f.close()

        return po_total

    def _prepare_ap_line(self, position, value):
        """
        positioning the value
        :param position: relevant position info for values
        :param value: line values
        :return: a string line where all value in correct positon
        """
        line = [' '] * 1000
        for key in position:
            # match the key in both positon and value
            if key in value.keys():
                # 1 digit
                if isinstance(position[key], int):
                    pos = position[key]
                    line[pos - 1] = value[key]
                # multiple digits
                elif len(position[key]) == 2:
                    start, end = position[key]
                    line[start - 1:end] = value[key]

                else:
                    raise 'Wrong AP position on %s' % key

        return ''.join(line)

    def invoice_cancel(self, cr, uid, ids, context=None):
        """
        Cancel the invoice
        :param cr: database cursor
        :param uid: user id
        :param ids: invoice id
        :param context:
        :return:
        """
        if context is None:
            context = {}
        account_move_obj = self.pool.get('account.move')
        account_invoice_line_obj = self.pool.get('account.invoice.line')
        stock_move_obj = self.pool.get('stock.move')
        stock_picking_obj = self.pool.get('stock.picking')

        # get invoice
        invoice = self.read(cr, uid, ids, ['move_id', 'payment_ids', 'invoice_line'])
        account_move_ids = []  # ones that we will need to remove
        stock_move_ids = []
        stock_picking_ids = []
        if invoice['move_id']:
            account_move_ids.append(invoice['move_id'][0])
        if invoice['payment_ids']:
            account_move_line_obj = self.pool.get('account.move.line')
            pay_ids = account_move_line_obj.browse(cr, uid, invoice['payment_ids'])
            for move_line in pay_ids:
                if move_line.reconcile_partial_id and move_line.reconcile_partial_id.line_partial_ids:
                    raise osv.except_osv(_('Error!'), _(
                        'You cannot cancel an invoice which is partially paid. You need to unreconcile related payment entries first.'))

        # Get related stock_move's
        lines = account_invoice_line_obj.browse(cr, uid, invoice['invoice_line'])
        for line in lines:
            if line.stock_move_id:
                stock_move_ids.append(line.stock_move_id.id)
                if line.stock_move_id.picking_id.id not in stock_picking_ids:
                    stock_picking_ids.append(line.stock_move_id.picking_id.id)

        # Change the statues in related stock move and stock picking
        stock_move_obj.write(cr, uid, stock_move_ids, {'invoice_status': '2binvoiced'})
        stock_picking_obj.write(cr, uid, stock_picking_ids, {'invoice_state': '2binvoiced'})

        # First, set the invoices as cancelled and detach the move ids
        self.write(cr, uid, ids, {'state': 'cancel', 'move_id': False, 'internal_number': None})
        if account_move_ids:
            # second, invalidate the move(s)
            account_move_obj.button_cancel(cr, uid, account_move_ids, context=context)
            # delete the move this invoice was pointing to
            # Note that the corresponding move_lines and move_reconciles
            # will be automatically deleted too
            account_move_obj.unlink(cr, uid, account_move_ids, context=context)
        self._log_event(cr, uid, ids, -1.0, 'Cancel Invoice')
        return True

    def invoice_undo(self, cr, uid, ids, context=None):
        """
        Undo an invoice based on the invoice status
        :param cr:
        :param uid:
        :param ids:
        :param context:
        :return:
        """
        account_invoice_account_line_obj = self.pool.get('account.invoice.account.line')

        account_line_ids = []
        ids_to_vendor_approved = []
        ids_to_draft = []

        # Get all selected invoices and
        for invoice in self.browse(cr, uid, ids, context):
            state = invoice.state
            # state that will move to vendor approved
            if state in ['ready', 'sent']:
                account_line_id = [line.id for line in invoice.account_line]
                if len(account_line_id) > 0:
                    account_line_ids += account_line_id
                ids_to_vendor_approved.append(invoice.id)
            # state that will move to draft
            elif state in ['manager_approved', 'vendor_approved', 'vendor_denied']:
                ids_to_draft.append(invoice.id)
            # cancel the invoice
            elif state == 'draft':
                self.invoice_cancel(cr, uid, invoice.id, context)
            '''else:
                raise osv.except_osv(_('Error!'), _('You can not cancel a cancelled invoice'))'''

        if len(account_line_ids) > 0:
            # Delete all account line attached to this invoice
            account_invoice_account_line_obj.unlink(cr, uid, account_line_ids, context)

        if len(ids_to_vendor_approved) > 0:
            # Change state to Vendor Approved
            self.write(cr, uid, ids_to_vendor_approved, {'state': 'vendor_approved'}, None)

        if len(ids_to_draft) > 0:
            # delete related moves
            self.action_cancel(cr, uid, ids_to_draft, None)
            # set invoice from canceled to draft
            self.write(cr, uid, ids_to_draft, {'state': 'draft'}, None)
            wf_service = netsvc.LocalService("workflow")
            for inv_id in ids_to_draft:
                wf_service.trg_delete(uid, 'account.invoice', inv_id, cr)
                wf_service.trg_create(uid, 'account.invoice', inv_id, cr)

        return True


vmi_account_invoice()


class vmi_account_invoice_line(osv.osv):
    _name = "account.invoice.line"
    _inherit = "account.invoice.line"
    _description = "Invoice Line"
    _columns = {
        'stock_move_id': fields.many2one('stock.move', 'Reference', select=True, states={'done': [('readonly', True)]}),
        'account_id': fields.many2one('account.account', 'Account',
                                      domain=[('type', '<>', 'view'), ('type', '<>', 'closed')],
                                      help="The income or expense account related to the selected product."),
    }


vmi_account_invoice_line()


class vmi_account_move(osv.osv):
    _name = "account.move"
    _inherit = "account.move"
    _description = "Account Entry"

    def button_cancel(self, cr, uid, ids, context=None):
        if ids:
            cr.execute('UPDATE account_move ' \
                       'SET state=%s ' \
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
            raise osv.except_osv(_('Warning!'), _(
                "Sender email is missing or empty after template rendering. Specify one to deliver your message"))
        # process email_recipients field that is a comma separated list of partner_ids -> recipient_ids
        # NOTE: only usable if force_send is True, because otherwise the value is
        # not stored on the mail_mail, and therefore lost -> fixed in v8

        # Add recipient id from context
        if 'recipient_ids' in context.keys():
            recipient_ids = context['recipient_ids']
        email_recipients = values.pop('email_recipients', '')
        if email_recipients:
            for partner_id in email_recipients.split(','):
                if partner_id:  # placeholders could generate '', 3, 2 due to some empty field values
                    recipient_ids.append(int(partner_id))
        # Overwrite email body
        if 'body_html' in context.keys():
            values['body_html'] = context['body_html']

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
        'notification': fields.boolean('Email Notification for Invoice',
                                       help="Check this box to enable email notifications for invoices"),
        'audit_notification': fields.boolean('Email Notification for Auditing',
                                             help="Check this box to enable email notifications for auditing"),
        'code': fields.char('Partner Code', size=4, help="'code' for creating invoice number")
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
        data_inv = self.pool.get('account.invoice').read(cr, uid, context['active_ids'], ['state'], context=context)

        for record in data_inv:
            if record['state'] != 'vendor_approved':
                raise osv.except_osv(_('Warning!'), _(
                    "Selected invoice(s) cannot be allocated as they are not in 'Vendor Approved' state."))
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
        account_account_rule_line_obj = self.pool.get('account.account.rule.line')
        account_invoice_account_line_obj = self.pool.get('account.invoice.account.line')

        # Get id of category "Delivery Fee"
        category_delivery = product_category_obj.search(cr, uid, [('name', '=', 'Delivery Fee')])
        data_inv = account_invoice_obj.browse(cr, uid, context['active_ids'], context=context)
        invoice_delivery = []
        category_sum = {}
        location_ratio = {}
        invoice_date = None
        # Check if selections are valid, record service fee invoice and calculate sum for each category
        for record in data_inv:
            if record.state not in ['vendor_approved', 'ready', 'sent']:
                raise osv.except_osv(_('Warning!'), _(
                    "Selected invoice(s) cannot be allocated as they are not in 'Vendor Approved', 'Ready for AP' or 'AP File Generated'state."))

            # check if the invoice date match
            if not invoice_date:
                invoice_date = record.date_invoice
            elif record.date_invoice != invoice_date:
                raise osv.except_osv(_('Warning!'), _(
                    "Selected invoice(s) cannot be allocated. Invoice Date doesn't match!"))

            # found invoice for service fee
            if record.category_id.id == category_delivery[0]:
                if record.state != 'vendor_approved':
                    raise osv.except_osv(_('Warning!'), _(
                        "The Delivery Fee invoice is not approved by Vendor, or it has been calculated."))
                invoice_delivery.append(record.id)

            # found normal invoice
            elif record.category_id.id in category_sum.keys():
                category_sum[record.category_id.id] += record.amount_total
            else:
                category_sum[record.category_id.id] = record.amount_total

        if len(invoice_delivery) == 0:
            raise osv.except_osv(_('Warning!'), _('Please make sure to select at least one "Service Fee Invoice"!'))

        # the number of categories does not match
        invoices = account_invoice_obj.browse(cr, uid, invoice_delivery)
        num_category_charged = 0
        for invoice in invoices:
            num_category_charged += len(invoice.invoice_line)
        if len(category_sum) != num_category_charged:
            raise osv.except_osv(_('Warning!'), _('The categories of the selected invoices do not match the items in '
                                                  'delivery fee invoice! Please check the delivery fee invoice.'))

        # Calculate ratio
        for record in data_inv:
            if record.category_id.id in category_sum.keys():
                if (record.category_id.id, record.location_id.location_id.id) not in location_ratio:
                    location_ratio[(record.category_id.id, record.location_id.location_id.id)] = record.amount_total / \
                                                                                                 category_sum[
                                                                                                     record.category_id.id]
                # Normally, the (category, location) key is unique, the 'else' here is for the case the manager generates
                # additional invoices after the first run of the month
                else:
                    location_ratio[(record.category_id.id, record.location_id.location_id.id)] += record.amount_total / \
                                                                                                  category_sum[
                                                                                                      record.category_id.id]

        # Match accounts
        # for each delivery fee invoices (one for each partner)
        for invoice in invoices:
            values = []
            account_amount = {}
            # for different category in one delivery fee invoice
            for line in invoice['invoice_line']:
                line_info = str(line.product_id.name).split('-')
                line_category = product_category_obj.search(cr, uid, [('name', '=', line_info[0])])
                # calculate service based on delivery ratio for each location and category
                for cate_loc in location_ratio:
                    # find account based on location and category
                    account_rule_line_id = account_account_rule_line_obj.search(cr, uid,
                                                                                [('location_id', '=', cate_loc[1]), (
                                                                                    'category_id', '=',
                                                                                    category_delivery[0])])
                    #found account
                    if account_rule_line_id:
                        account_rule_line = account_account_rule_line_obj.browse(cr, uid, account_rule_line_id, None)
                        account = account_rule_line[0].account_id.id
                    if line_category[0] == cate_loc[0]:
                        amount = location_ratio[cate_loc] * line.price_subtotal
                        if account in account_amount.keys():
                            account_amount[account] += amount
                        else:
                            account_amount[account] = amount
            for key in account_amount:
                values.append({'invoice_id': invoice['id'], 'account_id': key, 'total': account_amount[key]})
            if len(values) > 0:
                #Create invoice line for delivery fee invoice
                for value in values:
                    account_line = account_invoice_account_line_obj.create(cr, uid, value, None)
                invoice_date = invoice.date_invoice.split('-')
                internal_number = 'VMI' + \
                                  invoice_date[0][2:] + \
                                  invoice_date[1]
                seq = ''
                old_seq = account_invoice_obj.search(cr, uid, [('internal_number', 'like', internal_number)],
                                                     order='internal_number')
                if old_seq:
                    old_num = account_invoice_obj.read(cr, uid, old_seq[-1], ['internal_number'])
                    seq = str(int(old_num['internal_number'][7:10]) + 1)
                internal_number += seq.rjust(3, '0') + \
                                   invoice.partner_id.code.rjust(2, '0') + \
                                   '00' + \
                                   invoice.category_id.code.rjust(2, '0')

                changed_fields = {
                    'internal_number': internal_number,
                    'number': internal_number,
                    'state': 'ready'
                }
                change_state = account_invoice_obj.write(cr, uid, invoice['id'], changed_fields, None)

        return {'type': 'ir.actions.act_window_close'}


account_invoice_allocate()


class account_invoice_generate(osv.osv_memory):
    """
    This wizard will Generate AP File
    """

    _name = "account.invoice.generate"
    _description = "Generate AP File"
    _columns = {
        'upload': fields.boolean("Upload a copy to FTP server")
    }

    def prepare_to_generate_ap_file(self, cr, uid, ids, context=None):
        if context is None:
            context = {}
        account_invoice_obj = self.pool.get('account.invoice')
        res_partner_obj = self.pool.get('res.partner')
        ap_config = get_config()
        # valid_ids = []
        data_inv = self.pool.get('account.invoice').read(cr, uid, context['active_ids'], ['state'], context=context)
        flag = self.read(cr, uid, ids, ['upload'])
        for record in data_inv:
            if record['state'] != 'ready':
                raise osv.except_osv(_('Warning!'), _(
                    "Selected invoice(s) cannot be allocated as they are not in 'Ready for AP' state."))
        try:
            generated = account_invoice_obj.generate_ap_file(cr, uid, context['active_ids'])
        except Exception, e:
            raise osv.except_osv(_('Error!'), _('Fail to generate AP file:', e))
        # Upload file to FTP server
        if '/' in ap_config['ap_file']:
            file_name = ap_config['ap_file'].split('/')[-1]
        else:
            file_name = ap_config['ap_file'].split('\\')[-1]

        if generated and flag[0]['upload']:
            try:
                ftp = FTP(ap_config['ap_ftp'], ap_config['ap_ftp_username'], ap_config['ap_ftp_password'])
                ftp.cwd(ap_config['ap_ftp_path'])
                ftp.storbinary('STOR %s' % file_name, open(ap_config['ap_file'], 'rb'))
                ftp.quit()
            except Exception, e:
                raise osv.except_osv(_('Error!'), _('Upload to FTP error:', e))

        # Create a attachment in ir.attachment for future use
        today = date.today()
        attachment_name = file_name.split('.')[0] + '-' + str(today) + '.' + file_name.split('.')[1]
        file_obj = open(ap_config['ap_file'], 'rb')
        file_string = file_obj.read()
        file_val = base64.encodestring(file_string)
        attachment_obj = self.pool.get('ir.attachment')
        attach_id = attachment_obj.create(cr, uid,
                                          {'name': attachment_name, 'datas': file_val, 'datas_fname': attachment_name},
                                          None)
        file_obj.close()

        if generated:
            template_obj = self.pool.get('email.template')

            # Generate email_1 to IT_control to run the job
            partner_it_id = res_partner_obj.search(cr, uid, [('name', '=', 'IT Control')])
            partner_it = res_partner_obj.browse(cr, uid, partner_it_id)

            # get email template, render it and send it
            control_template_id = template_obj.search(cr, uid, [('name', '=', 'Email to IT Control')])
            context['recipient_ids'] = [int(child_id.id) for child_id in partner_it[0].child_ids]
            try:
                it_mail = template_obj.send_mail(cr, uid, control_template_id[0], ids[0], True, context=context)
            except:
                raise osv.except_osv(_('Error!'), _(
                    'No Email Template Found, Please configure a email template under Email tab and named "Email to IT Control"'))

            # Generate email_2 to AP about the PO number
            partner_ap_id = res_partner_obj.search(cr, uid, [('name', '=', 'AP')])
            partner_ap = res_partner_obj.browse(cr, uid, partner_ap_id)

            # get email template, render it and send it
            ap_template_id = template_obj.search(cr, uid, [('name', '=', 'Email to AP')])
            ap_template = template_obj.browse(cr, uid, ap_template_id, None)
            template_body = ap_template[0].body_html
            context['recipient_ids'] = [int(child_id.id) for child_id in partner_ap[0].child_ids]

            # Append ap file info to email body
            appended_body = ''
            for vendor in generated:
                appended_body += '<p>Vendor: %s ----- PO Number: %s ----- Gross Amount: %.2f</p>' % (
                    vendor[0], vendor[1], generated[vendor])
            closing_body = """<br/>
                              <p>Thanks</p>
                              <p>SEPTA VMI TEAM</p>"""
            context['body_html'] = ''.join([template_body, '\n', appended_body, closing_body])

            try:
                ap_mail = template_obj.send_mail(cr, uid, ap_template_id[0], ids[0], True, context=context)
            except:
                raise osv.except_osv(_('Error!'), _(
                    'No Email Template Found, Please configure a email template under Email tab and named "Email to AP"'))

        # Change status to 'sent'
        if generated:
            account_invoice_obj.write(cr, uid, context['active_ids'], {'state': 'sent'})

        return {'type': 'ir.actions.act_window_close'}


account_invoice_generate()


class account_invoice_undo(osv.osv_memory):
    """
    This wizard will undo the invoices based on the status
    """

    _name = "account.invoice.undo"
    _description = "Undo the invoices based on status"

    def undo_invoices(self, cr, uid, ids, context=None):
        if context is None:
            context = {}
        account_invoice_obj = self.pool.get('account.invoice')
        try:
            account_invoice_obj.invoice_undo(cr, uid, context['active_ids'], context)
        except Exception, e:
            raise osv.except_osv(_('Error!'), _('Fail to Undo the invoices:', e))
        return {'type': 'ir.actions.act_window_close'}


account_invoice_undo()


class account_invoice_account_line(osv.osv):
    """
    A new class defines the which account is attach to the invoice
    """
    _name = 'account.invoice.account.line'
    _description = 'Account Line'
    _columns = {
        'account_id': fields.many2one('account.account', 'Account', required=True,
                                      help="This account related to the selected invoice"),
        'invoice_id': fields.many2one('account.invoice', 'Invoice Reference', ondelete='cascade', select=True),
        'total': fields.float('Total Amount', digits_compute=dp.get_precision('Account'))
    }


account_invoice_account_line()


class account_invoice_ap_po(osv.osv):
    """
    A new class defines the which po line is attach to the ap default value
    """
    _name = 'account.invoice.ap.po'
    _description = 'PO Numbers'
    _columns = {
        'ap_default_id': fields.many2one('account.invoice.ap', 'AP Default Value', required=True,
                                         help="AP Default Value"),
        'category_id': fields.many2one('product.category', 'Category', help="Categories that match the po number"),
        'po_number': fields.char('PO Number', size=64, help="Purchase Order Number")
    }


account_invoice_ap_po()


class account_invoice_ap(osv.osv):
    """
    A new class store the default value of ap
    """

    _name = "account.invoice.ap"
    _table = 'account_invoice_ap'
    _description = "AP default value"
    _columns = {
        'name': fields.char('Name', size=64),
        'paying_entity': fields.char('Paying Entity', size=64),
        'control_number': fields.char('Control Number', size=64),
        'operator_id': fields.char('Operator ID', size=64),
        'vendor_group_number': fields.char('Vendor Group Number', size=64),
        'application_code': fields.char('Application Code', size=64),
        'bank_payment_code': fields.char('Bank Payment Code', size=64),
        'vendor_id': fields.many2one('res.partner', 'Vendor', required=True, readonly=False),
        'vendor_number': fields.char('Vendor Number', size=64),
        'po_numbers': fields.one2many('account.invoice.ap.po', 'ap_default_id', 'PO Numbers', help="PO Numbers",
                                      domain=[])
    }


account_invoice_ap()


class account_account_rule_line(osv.osv):
    """
    A new class store the account rules
    """
    _name = 'account.account.rule.line'
    _description = 'Rule Line'
    _columns = {
        'name': fields.char('Name', size=64, help="Rule line name"),
        'account_id': fields.many2one('account.account', 'Account', required=True,
                                      help="This account related to the selected invoice"),
        'location_id': fields.many2one('stock.location', 'Location', help="Locations that use this rule"),
        'category_id': fields.many2one('product.category', 'Category', help="Categories that use this rule"),
        'ratio': fields.float('Ratio',
                              help="Attached account only pay this ratio of total amount for relevant location and "
                                   "category. It is defined by AP"),
        'product_id': fields.many2one('product.product', 'Product', help="Products that use this rule"),

    }


account_account_rule_line()


class vmi_account_account(osv.osv):
    """
    Overwrite of account.account and add rule_line field which define the rules for this account
    """
    _name = 'account.account'
    _inherit = 'account.account'
    _columns = {
        'rule_line': fields.one2many('account.account.rule.line', 'account_id', 'Rule Lines', help="Account Rules",
                                     domain=[]),
    }


vmi_account_account()