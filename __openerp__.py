# -*- coding: utf-8 -*-
##############################################################################
#
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################


{
    'name': 'SEPTA VMI',
    'version': '0.1',
    'category': 'VMI',
    'description': """
This module modifies the OpenERP Warehouse modules 
for use with VMI requirments.
     """,
    'author': 'M. A. Ruberto',
    'website': 'http://septa.org',
    'depends': ['stock', 'product', 'base'],
    'data': [
        'vmi_view.xml',
    ],
    'demo': [],
    'test':[],
    'installable': True,
    'images': [],
}
