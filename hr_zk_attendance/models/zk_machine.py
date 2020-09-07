import pytz
import sys
from datetime import datetime
import dateutil
import logging
import binascii
import os
import platform
import subprocess
import time

from odoo import models, fields, api, exceptions, _
from odoo import _
from odoo.exceptions import UserError, ValidationError
_logger = logging.getLogger(__name__)
try:
    from zk import ZK, const
except ImportError:
    _logger.error("Unable to import pyzk library. Try 'pip3 install pyzk'.")

class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    device_id = fields.Char(string='Biometric Device ID')
    check_in_date = fields.Date(string="Attendance date" ,default=datetime.today())

    @api.depends('check_in', 'check_out')
    def _compute_worked_hours(self):
        for attendance in self:
            if attendance.check_in and attendance.check_out:
                delta = attendance.check_out - attendance.check_in
                attendance.worked_hours = delta.total_seconds() / 3600.0
            else:
                attendance.worked_hours = False

    @api.constrains('check_in', 'check_out', 'employee_id')
    def _check_validity(self):
        for attendance in self:
            # we take the latest attendance before our check_in time and check it doesn't overlap with ours
            last_attendance_before_check_in = self.env['hr.attendance'].search([
                ('employee_id', '=', attendance.employee_id.id),
                ('check_in', '<=', attendance.check_in),
                ('id', '!=', attendance.id),
            ], order='check_in desc', limit=1)
            if last_attendance_before_check_in and last_attendance_before_check_in.check_out and last_attendance_before_check_in.check_out > attendance.check_in:
                _logger.info('====== Warning ======')
                _logger.info(_("Cannot create new attendance record for %(empl_name)s, the employee was already checked in on %(datetime)s") % {
                    'empl_name': attendance.employee_id.name,
                    'datetime': fields.Datetime.to_string(fields.Datetime.context_timestamp(self, fields.Datetime.from_string(attendance.check_in))),
                })

            if not attendance.check_out:
                # if our attendance is "open" (no check_out), we verify there is no other "open" attendance
                no_check_out_attendances = self.env['hr.attendance'].search([
                    ('employee_id', '=', attendance.employee_id.id),
                    ('check_out', '=', False),
                    ('id', '!=', attendance.id), 
                ], order='check_in desc', limit=1)
                if no_check_out_attendances:
                    _logger.info('====== Warning ======')
                    _logger.info(_("Cannot create new attendance record for %(empl_name)s, the employee hasn't checked out since %(datetime)s") % {
                        'empl_name': attendance.employee_id.name,
                        'datetime': fields.Datetime.to_string(fields.Datetime.context_timestamp(self, fields.Datetime.from_string(no_check_out_attendances.check_in))),
                    })
            else:
                # we verify that the latest attendance with check_in time before our check_out time
                # is the same as the one before our check_in time computed before, otherwise it overlaps
                last_attendance_before_check_out = self.env['hr.attendance'].search([
                    ('employee_id', '=', attendance.employee_id.id),
                    ('check_in', '<', attendance.check_out),
                    ('id', '!=', attendance.id),
                ], order='check_in desc', limit=1)
                if last_attendance_before_check_out and last_attendance_before_check_in != last_attendance_before_check_out:
                    _logger.info('====== Warning ======')
                    _logger.info(_("Cannot create new attendance record for %(empl_name)s, the employee was already checked in on %(datetime)s") % {
                        'empl_name': attendance.employee_id.name,
                        'datetime': fields.Datetime.to_string(fields.Datetime.context_timestamp(self, fields.Datetime.from_string(attendance.check_in))),
                    })


class ZkMachine(models.Model):
    _name = 'zk.machine'
    
    name = fields.Char(string='Machine IP', required=True)
    port_no = fields.Integer(string='Port No', required=True, default="4370")
    address_id = fields.Many2one('res.partner', string='Working Address')
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.user.company_id.id)
    zk_timeout = fields.Integer(string='ZK Timeout', required=True, default="120")
    zk_after_date =  fields.Datetime(string='Attend Start Date', help='If provided, Attendance module will ignore records before this date.')

    def device_connect(self, zkobj):
        try:
            conn =  zkobj.connect()
            return conn
        except:
            _logger.info("zk.exception.ZKNetworkError: can't reach device.")
            raise UserError("Connection To Device cannot be established.")
            return False

    
    # def device_connect(self, zkobj):
    #     for i in range(10):
    #         try:
    #             conn =  zkobj.connect()
    #             return conn
    #         except:
    #             _logger.info("zk.exception.ZKNetworkError: can't reach device.")
    #             conn = False
    #     return False


    def try_connection(self):
        for r in self:
            machine_ip = r.name
            if platform.system() == 'Linux':
                response = os.system("ping -c 1 " + machine_ip)
                print(response)
                if response == 0:
                    raise UserError("Biometric Device is Up/Reachable.")
                else:
                    raise UserError("Biometric Device is Down/Unreachable.") 
            else:
                prog = subprocess.run(["ping", machine_ip], stdout=subprocess.PIPE)
                if 'unreachable' in str(prog):
                    raise UserError("Biometric Device is Down/Unreachable.")
                else:
                    raise UserError("Biometric Device is Up/Reachable.")  
    
    def clear_attendance(self):
        for info in self:
            try:
                machine_ip = info.name
                zk_port = info.port_no
                timeout = info.zk_timeout
                try:
                    zk = ZK(machine_ip, port = zk_port , timeout=timeout, password=0, force_udp=False, ommit_ping=False)
                except NameError:
                    raise UserError(_("Pyzk module not Found. Please install it with 'pip3 install pyzk'."))                
                conn = self.device_connect(zk)
                if conn:
                    conn.enable_device()
                    clear_data = zk.get_attendance()
                    if clear_data:
                        #conn.clear_attendance()
                        self._cr.execute("""delete from zk_machine_attendance""")
                        conn.disconnect()
                        raise UserError(_('Attendance Records Deleted.'))
                    else:
                        raise UserError(_('Unable to clear Attendance log. Are you sure attendance log is not empty.'))
                else:
                    raise UserError(_('Unable to connect to Attendance Device. Please use Test Connection button to verify.'))
            except:
                raise ValidationError('Unable to clear Attendance log. Are you sure attendance device is connected & record is not empty.')

    def zkgetuser(self, zk):
        try:
            users = zk.get_users()
            print(users)
            return users
        except:
            raise UserError(_('Unable to get Users.'))

    @api.model
    def cron_download(self):
        machines = self.env['zk.machine'].search([])
        for machine in machines :
            machine.download_attendance()

    def download_user(self):
        _logger.info("==========download_user==========")
        zk_user = self.env['zk.machine.user']
        for info in self:
            machine_ip = info.name
            zk_port = info.port_no
            timeout = info.zk_timeout
            try:
                zk = ZK(machine_ip, port = zk_port , timeout=timeout, password=0, force_udp=False, ommit_ping=False)
            except NameError:
                raise UserError(_("Pyzk module not Found. Please install it with 'pip3 install pyzk'."))
            conn = self.device_connect(zk)
            if conn:
                try:
                    user = conn.get_users()
                    conn.disconnect
                except:
                    user = False
                if user:
                    for each in user:
                        attendance_user = zk_user.search([('device_id','=',each.uid),('user_id','=',each.user_id)])
                        if not attendance_user:
                            zk_user.create({'device_id': each.uid,
                                            'name':each.name,
                                            'privilege': each.privilege,
                                            'user_id': each.user_id,
                                            'group_id': each.group_id})
                    return True
                else:
                    raise UserError(_('No User found in Attendance Device to Download.'))
            else:
                raise UserError(_('Unable to connect to Attendance Device. Please use Test Connection button to verify.'))
        
    def download_attendance(self):
        _logger.info("++++++++++++Cron Executed++++++++++++++++++++++")
        zk_attendance = self.env['zk.machine.attendance']
        att_obj = self.env['hr.attendance']
        for info in self:
            machine_ip = info.name
            zk_port = info.port_no
            timeout = info.zk_timeout
            try:
                zk = ZK(machine_ip, port = zk_port , timeout=timeout, password=0, force_udp=False, ommit_ping=False)
            except NameError:
                raise UserError(_("Pyzk module not Found. Please install it with 'pip3 install pyzk'."))
            conn = self.device_connect(zk)
            if conn:
                # conn.disable_device() #Device Cannot be used during this time.
                try:
                    attendance = conn.get_attendance()
                except:
                    attendance = False
                if attendance:
                    for each in attendance:
                        atten_time = each.timestamp
                        atten_time = datetime.strptime(atten_time.strftime('%Y-%m-%d %H:%M:%S'), '%Y-%m-%d %H:%M:%S')
                        atten_date = dateutil.parser.parse(str(atten_time)).date()
                        if info.zk_after_date == False:
                            tmp_zk_after_date = datetime.strptime('2000-01-01',"%Y-%m-%d")
                        else:
                            tmp_zk_after_date = datetime.strptime(str(info.zk_after_date),'%Y-%m-%d %H:%M:%S')
                        if atten_time != False and atten_time > tmp_zk_after_date:
                            local_tz = pytz.timezone(
                                self.env.user.partner_id.tz or 'GMT')
                            local_dt = local_tz.localize(atten_time, is_dst=None)
                            utc_dt = local_dt.astimezone(pytz.utc)
                            utc_dt = utc_dt.strftime("%Y-%m-%d %H:%M:%S")
                            atten_time = datetime.strptime(
                                utc_dt, "%Y-%m-%d %H:%M:%S")
                            tmp_utc = local_dt.astimezone(pytz.utc)
                            tmp_attend = tmp_utc.strftime("%m-%d-%Y %H:%M:%S")
                            attendance_time = atten_time
                            atten_time = fields.Datetime.to_string(atten_time)
                            get_user_id = self.env['hr.employee'].search(
                                [('device_id.user_id', '=', each.user_id)])
                            if get_user_id:
                                duplicate_atten_ids = zk_attendance.search(
                                    [('device_id', '=', each.user_id), ('punching_time', '=', atten_time)])
                                if duplicate_atten_ids:
                                    continue
                                else:
                                    attendance_log = zk_attendance.search([('device_id','=',each.user_id),('employee_id','=',get_user_id.id),('punching_time','=',atten_time)])
                                    if not attendance_log:
                                        zk_attendance.create({'employee_id': get_user_id.id,
                                                            'device_id': each.user_id,
                                                            'attendance_type': str(each.status),
                                                            'punch_type': str(each.punch),
                                                            'punching_time': atten_time,
                                                            'address_id': info.address_id.id,
                                                            'check_in_date': atten_date})
                                        print(atten_date)
                                        att_var = att_obj.search([('employee_id', '=', get_user_id.id),('check_in_date','=',atten_date),
                                                                ('check_out', '=', False)])

                                        if each.punch == 0: #check-in
                                            if not att_var:
                                                attend_rec_tmp = att_obj.search([('employee_id', '=', get_user_id.id),('check_out', '>', tmp_attend)])
                                                if not attend_rec_tmp:
                                                    att_obj.create({'employee_id': get_user_id.id,
                                                                    'check_in': atten_time,
                                                                    'check_in_date': atten_date})

                                        if each.punch == 1: #check-out
                                            if len(att_var) == 1:
                                                att_var.write({'check_out': atten_time})
                                            else:
                                                att_var1 = att_obj.search([('employee_id', '=', get_user_id.id),('check_in_date','=',atten_date)])
                                                if att_var1:
                                                    att_var1[-1].write({'check_out': atten_time})
                                    else:
                                        pass
                            else:
                                pass
                    # conn.enable_device() #Enable Device Once Done.
                    conn.disconnect
                    return True
                else:
                    raise UserError(_('No attendances found in Attendance Device to Download.'))
                    # conn.enable_device() #Enable Device Once Done.
                    conn.disconnect
            else:
                raise UserError(_('Unable to connect to Attendance Device. Please use Test Connection button to verify.'))

