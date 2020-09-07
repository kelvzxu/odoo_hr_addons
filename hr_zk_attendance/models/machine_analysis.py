# -*- coding: utf-8 -*-
###################################################################################
#
#    This program is free software: you can modify
#    it under the terms of the GNU Affero General Public License (AGPL) as
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
###################################################################################
from odoo import tools
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class HrEmployee(models.Model):
    _inherit = 'hr.employee'
    device_id = fields.Many2one('zk.machine.user',string='Biometric Device ID')  

    @api.constrains('device_id')
    def check_unique_deviceid(self):
        records = self.env['hr.employee'].search([('device_id', '=', self.device_id.id),('device_id', '!=', False ),('id', '!=', self.id)])
        if records:
            raise UserError(_('Another User with same Biometric Device ID already exists.'))


class ZkMachine(models.Model):
    _name = 'zk.machine.attendance'
    _inherit = 'hr.attendance'

    @api.constrains('check_in', 'check_out', 'employee_id')
    def _check_validity(self):
        """overriding the __check_validity function for employee attendance."""
        pass

    device_id = fields.Char(string='Biometric Device ID')
    punch_type = fields.Selection([('0', 'Check In'),
                                   ('1', 'Check Out'),
                                   ('2', 'Break Out'),
                                   ('3', 'Break In'),
                                   ('4', 'Overtime In'),
                                   ('5', 'Overtime Out')],
                                  string='Punching Type')

    attendance_type = fields.Selection([('0', 'Finger'),
                                        ('1', 'Finger'),
                                        ('15', 'Face'),
                                        ('2','Type_2'),
                                        ('3','Password'),
                                        ('4','Card')], string='Category')
    punching_time = fields.Datetime(string='Attendance Time')
    address_id = fields.Many2one('res.partner', string='Working Address')

class ZkMachine(models.Model):
    _name = 'zk.machine.user'

    device_id = fields.Char(string='Biometric Device ID')
    name = fields.Char(string='Biometric Device Name')
    privilege = fields.Char(string='Biometric Device Privilege')
    user_id=fields.Char(string='Biometric User Id')
    group_id = fields.Char(string='Biometric Device Group ID')

    

