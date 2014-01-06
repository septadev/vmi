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

class vmi_product(osv.osv):
	"""Override of product.product"""
	_name = 'product.product'
	_inherit = 'product.product'
	_columns = {
		'vendor_part_number': fields.char('Vendor P/N', size=128,  translate=False,  required=False, readonly=False, select=True),
		'default_code': fields.char('SEPTA P/N', size=64,  translate=False,  required=False, readonly=False, select=True),
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
					'scrapped' : False,
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
	
	def _flag_next_audit(self, cr, uid, ids, last_audited, partner, location, context):
		if context is None:
			context = {}
		res = []
		i = 1
		new_id = ids
		sql_req = """
			select 
			m.id
			,m.date 
			from 
			stock_move m
			where 
			(m.location_dest_id = %d)
			and 
			(m.partner_id = %d)
			order by date DESC ;
			""" % (location, partner) # offset %d last_audited['id']
		cr.execute(sql_req)
		sql_res = cr.dictfetchall()
		while i < len(sql_res):
			if sql_res[i]['id'] == last_audited:
				i += 1
				continue # Skip the offending last audited move.
				
			if i % 10 == 0:
				res.append(sql_res[i]['id'])
			i += 1
		
		vals = ', '.join(str(x) for x in res)
		_logger.debug('<_flag_next_audit> vals: %s', str(sql_res))	
		update_sql = """
		 update 
		   stock_move
		 set
		   audit = True 
		 where
		   id in (%s)
		""" % vals
		cr.execute(update_sql)
		return res		
			 
	""" Retrieve the most recently audited moves for this location and vendor """
	def _get_last_audited(self, cr, uid, ids, partner, location, context):
		if context is None:
			context = {}
		res = []
		last_audited = None
		if partner and location:
			sql_req = """
			select 
			m.id
			,m.date 
			from 
			stock_move m
			where 
			m.audit = True 
			and 
			(m.location_dest_id = %d)
			and 
			(m.partner_id = %d)
			order by date DESC limit 1;
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
			(m.location_dest_id = %d)
			and 
			(m.partner_id = %d)
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

	def create(self, cr, user, vals, context=None):
		if ('name' not in vals) or (vals.get('name')=='/'):
			seq_obj_name =  self._name
			vals['name'] = self.pool.get('ir.sequence').get(cr, user, seq_obj_name)
		new_id = super(vmi_stock_picking_in, self).create(cr, user, vals, context)
		last_audited = self._get_last_audited(cr, user, new_id, vals['move_lines'][0][2]['partner_id'], vals['move_lines'][0][2]['location_dest_id'], context)
		_logger.debug('<CREATE> last_audited: %s', str(last_audited))
		if last_audited is not None:
			next_audit = self._flag_next_audit(cr, user, new_id, last_audited, vals['move_lines'][0][2]['partner_id'], vals['move_lines'][0][2]['location_dest_id'], context)
			_logger.debug('<CREATE> next_audit: %s', str(next_audit))
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
		scrpaed_location_ids = location_obj.search(cr, uid, [('scrap_location','=',True)])

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
