from odoo import fields, models


class KpiReasonWizard(models.TransientModel):
    _name = 'kpi.reason.wizard'
    _description = 'Nhập lý do trả lại/điều chỉnh/mở lại'

    assignment_id = fields.Many2one('kpi.assignment', required=True, string='Bảng giao')
    kind = fields.Selection([('return', 'Trả lại'), ('adjust', 'Điều chỉnh bảng giao'),
                             ('reopen', 'Mở lại hồ sơ')], required=True, string='Loại thao tác')
    reason = fields.Text('Lý do', required=True)

    def action_confirm(self):
        self.ensure_one()
        a = self.assignment_id
        if self.kind == 'return':
            a._do_return(self.reason)
        elif self.kind == 'adjust':
            a._do_adjust(self.reason)
        else:
            a._do_reopen(self.reason)
        return {'type': 'ir.actions.act_window_close'}
