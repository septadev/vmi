import logging
from openerp.osv import osv
from openerp.osv import fields
from openerp import SUPERUSER_ID
from openerp import pooler, tools
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
        'mode': fields.selection([('N', 'Normal'), ('D', 'Debug'), ('T', 'Test')], 'Mode', help="Select the mode for this controller."),
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
    'audit': fields.boolean('Audit'),
    'audit_fail': fields.boolean('Failed Audit'),
    }
    _defaults = {
    'audit': False,
    'audit_fail': False,
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
        #audit quantity should be less than or equal to shipped quant.
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


class vmi_stock_picking_in(osv.osv):
    """Override of stock.picking.in"""
    _name = 'stock.picking.in'
    _inherit = 'stock.picking.in'
    _table = "stock_picking"
    _order = 'date desc'

    def _flag_next_audit(self, cr, uid, ids, last_audited, partner, location, context):
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
        sql_req = """
			select 
			m.id
			,m.date 
			from 
			stock_move m
			where 
			(m.location_dest_id = %s)
			and 
			(m.partner_id = %s)
			and
			 (m.date between '%s' and '%s')
			order by date DESC ;
			""" % (location, partner, last_audited['date'], now.strftime(date_format))
        cr.execute(sql_req)
        sql_res = cr.dictfetchall()
        _logger.debug('<_flag_next_audit> sql_res: %s', str(sql_res))
        if len(sql_res) > 0:
            while i < len(sql_res):
                if sql_res[i]['id'] == last_audited['id']:
                    i += 1
                    continue # Skip the offending last audited move.

                if i % 10 == 0:
                    res.append(sql_res[i]['id'])
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

        return res



    def _get_last_audited(self, cr, uid, ids, partner, location, context):
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
        #import pdb; pdb.set_trace()
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
                (m.partner_id = %s)
                ORDER BY date DESC LIMIT 1;
                """ % (location, partner)

            cr.execute(sql_req)
            sql_res = cr.dictfetchone()
            if sql_res:
                res.append({'id': sql_res['id'], 'date': sql_res['date']})

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
                (m.partner_id = %s)
                order by date DESC limit 1;
                """ % (location, partner)

            cr.execute(sql_req)
            sql_res = cr.dictfetchone()
            if sql_res:
                res.append({'id': sql_res['id'], 'date': sql_res['date']})

            if len(res) > 0:
                if len(res) > 1:
                    if res[0]['date'].date() < res[1]['date'].date():
                        last_audited = res.pop(1)
                    else:
                        last_audited = res.pop(0)
                else:
                    last_audited = res.pop(0)

        _logger.debug('<_get_last_audited> %s : %s : %s', str(sql_res), str(location), str(partner))
        return last_audited

    def _flag_first_audit(self, cr, user, partner, location, context):
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
                (m.partner_id = %s)
                AND
                (m.state != 'done')
                ORDER BY date ASC LIMIT 1;
                """ % (location, partner)
            cr.execute(sql_req)
            sql_res = cr.dictfetchone()
            if sql_res: # Set the audit flag for move record obtained.
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
            _logger.debug('<_flag_first_audit> No move records matching criteria exist: %s, %s', str(partner), str(location))

        return result


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
        result = []
        if 'pid' in vals:
            pid = vals.get('pid')
            if 'parse_result' in vals:
                p = vals.get('parse_result')
                for location in p['move_lines']['locations']:
                    last_audited = self._get_last_audited(cr, user, None, pid, location, context)
                    if last_audited:
                        result = self._flag_next_audit(cr, user, None, last_audited, pid, location, context)
                        #flagged.update({'location': location})
                        #result.append(flagged.copy())
                    else: # If no previously flagged move record exists then begin audit process by flagging a record.
                        result = self._flag_first_audit(cr, user, pid, location, context)


        _logger.debug('<action_flag_audit> next_audit: %s', str(result))
        return result

    def create(self, cr, user, vals, context=None):
        if ('name' not in vals) or (vals.get('name') == '/'):
            seq_obj_name = self._name
            vals['name'] = self.pool.get('ir.sequence').get(cr, user, seq_obj_name)
        new_id = super(vmi_stock_picking_in, self).create(cr, user, vals, context)

        return new_id


    _defaults = {
    'invoice_state': 'none',
    }

vmi_stock_picking_in()


class vmi_move_consume(osv.osv_memory):
    _name = "vmi.move.consume"
    _description = "Consume Products"

    _columns = {
    'product_id': fields.many2one('product.product', 'Product', required=True, select=True),
    'product_qty': fields.float('Quantity', digits_compute=dp.get_precision('Product Unit of Measure'), required=True),
    'product_uom': fields.many2one('product.uom', 'Product Unit of Measure', required=True),
    'location_id': fields.many2one('stock.location', 'Location', required=True)
    }

    #TOFIX: product_uom should not have differemt category of default UOM of product. Qty should be convert into UOM of original move line before going in consume and scrap
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
        if context is None:
            context = {}
        res = super(vmi_move_consume, self).default_get(cr, uid, fields, context=context)
        move = self.pool.get('stock.move').browse(cr, uid, context['active_id'], context=context)
        location_obj = self.pool.get('stock.location')
        scrpaed_location_ids = location_obj.search(cr, uid, [('scrap_location', '=', True)])

        if 'product_id' in fields:
            res.update({'product_id': move.product_id.id})
        if 'product_uom' in fields:
            res.update({'product_uom': move.product_uom.id})
        if 'product_qty' in fields:
            res.update({'product_qty': move.product_qty})
        if 'location_id' in fields:
            res.update({'location_id': move.location_dest_id.id})
            if scrpaed_location_ids:
                res.update({'location_id': scrpaed_location_ids[0]})
            else:
                res.update({'location_id': False})

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
