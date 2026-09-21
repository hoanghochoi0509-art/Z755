from odoo import api, fields, models


class KpiAuditLog(models.Model):
    _name = 'kpi.audit.log'
    _description = 'Nhật ký thay đổi KPI (kiểm toán)'
    _order = 'id desc'

    res_model = fields.Char('Mô hình', required=True, index=True)
    res_id = fields.Integer('ID bản ghi', required=True, index=True)
    record_name = fields.Char('Bản ghi')
    field_name = fields.Char('Trường', required=True)
    old_value = fields.Char('Giá trị trước')
    new_value = fields.Char('Giá trị sau')
    user_id = fields.Many2one('res.users', 'Người thay đổi', default=lambda s: s.env.user, readonly=True)
    change_date = fields.Datetime('Thời gian', default=fields.Datetime.now, readonly=True)
    reason = fields.Text('Lý do')
    assignment_id = fields.Many2one('kpi.assignment', 'Bảng giao', ondelete='set null', index=True)

    def unlink(self):
        from odoo.exceptions import UserError
        raise UserError('Không được xóa nhật ký kiểm toán KPI.')

    def write(self, vals):
        from odoo.exceptions import UserError
        raise UserError('Không được sửa nhật ký kiểm toán KPI.')


class KpiAuditMixin(models.AbstractModel):
    """Ghi giá trị trước/sau của các trường ảnh hưởng kết quả."""
    _name = 'kpi.audit.mixin'
    _description = 'Mixin nhật ký thay đổi KPI'

    _audit_fields = ()

    def _audit_display(self, field, value):
        if isinstance(value, models.BaseModel):
            return ', '.join(value.mapped('display_name'))
        if value is False or value is None:
            return ''
        return str(value)

    def _audit_assignment(self):
        return self.env['kpi.assignment']

    def write(self, vals):
        watched = [f for f in self._audit_fields if f in vals]
        before = {}
        if watched:
            for rec in self:
                before[rec.id] = {f: rec._audit_display(f, rec[f]) for f in watched}
        res = super().write(vals)
        if watched:
            reason = self.env.context.get('kpi_change_reason')
            logs = []
            for rec in self:
                for f in watched:
                    new = rec._audit_display(f, rec[f])
                    if new != before[rec.id][f]:
                        logs.append({
                            'res_model': rec._name, 'res_id': rec.id,
                            'record_name': rec.display_name, 'field_name': rec._fields[f].string or f,
                            'old_value': before[rec.id][f], 'new_value': new,
                            'reason': reason, 'assignment_id': rec._audit_assignment().id or False,
                        })
            if logs:
                self.env['kpi.audit.log'].sudo().create(logs)
        return res
