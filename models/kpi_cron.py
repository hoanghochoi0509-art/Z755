from datetime import timedelta

from odoo import api, fields, models


class KpiAssignmentCron(models.Model):
    _inherit = 'kpi.assignment'

    @api.model
    def _cron_deadline_reminder(self):
        """Nhắc KPI sắp đến hạn/quá hạn cho chủ trì và quản lý (Odoo Activity)."""
        today = fields.Date.context_today(self)
        soon = today + timedelta(days=3)
        lines = self.env['kpi.assignment.line'].search([
            ('assignment_state', 'in', ('assigned', 'in_progress')), ('actual_entered', '=', False),
            ('due_date', '!=', False), ('due_date', '<=', soon)])
        for l in lines:
            users = l.responsible_id.user_id | l.assignment_id._manager_user() | l.assignment_id.department_id.manager_id.user_id
            tag = 'quá hạn' if l.due_date < today else 'sắp đến hạn'
            summary = '[KPI] %s %s: %s' % (tag, l.due_date, l.kpi_id.name)
            for u in users:
                exists = l.assignment_id.sudo().activity_ids.filtered(
                    lambda a: a.user_id == u and a.summary == summary)
                if u and not exists:
                    l.assignment_id.sudo().activity_schedule(
                        'mail.mail_activity_data_todo', user_id=u.id, summary=summary,
                        note=summary, date_deadline=today)
