from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class KpiEvaluation(models.Model):
    _name = 'kpi.evaluation'
    _description = 'Đánh giá KPI theo bước'
    _inherit = ['kpi.audit.mixin']
    _order = 'line_id, stage, id'

    _audit_fields = ('score_pct', 'evaluation_comment', 'adjustment_reason', 'submitted')

    line_id = fields.Many2one('kpi.assignment.line', required=True, ondelete='cascade', index=True, string='Dòng KPI')
    assignment_id = fields.Many2one(related='line_id.assignment_id', store=True, index=True, string='Bảng giao')
    kpi_name = fields.Char(related='line_id.kpi_name')
    stage = fields.Selection([('self', 'Tự chấm'), ('reviewer', 'Thẩm định'), ('kpi_team', 'Tổ KPI đề xuất'),
                              ('final', 'Kết luận')], 'Bước đánh giá', required=True, index=True)
    user_id = fields.Many2one('res.users', 'Người đánh giá')
    is_primary = fields.Boolean('Reviewer chính', default=False)
    actual_value = fields.Float('Kết quả thực tế', digits=(16, 2))
    system_score = fields.Float('Điểm hệ thống', digits=(16, 2))
    score_pct = fields.Float('Điểm (trước trọng số)', digits=(16, 2))
    weight_pct = fields.Float(related='line_id.weight_pct')
    weighted_score = fields.Float('Điểm quy đổi', compute='_compute_weighted', store=True, digits=(16, 2))
    evaluation_comment = fields.Text('Nhận xét')
    adjustment_reason = fields.Text('Lý do điều chỉnh')
    submitted = fields.Boolean('Đã gửi/xác nhận', default=False)
    prev_stage_score = fields.Float('Điểm bước trước', compute='_compute_prev')
    diff = fields.Float('Chênh lệch', compute='_compute_prev')

    def _audit_assignment(self):
        return self.assignment_id

    @api.depends('score_pct', 'weight_pct')
    def _compute_weighted(self):
        for e in self:
            e.weighted_score = e.score_pct * e.weight_pct / 100.0

    @api.depends('score_pct', 'stage', 'line_id.self_score', 'line_id.reviewer_score', 'line_id.team_score',
                 'line_id.system_score')
    def _compute_prev(self):
        for e in self:
            prev = {'self': e.line_id.system_score, 'reviewer': e.line_id.self_score,
                    'kpi_team': e.line_id.reviewer_score, 'final': e.line_id.team_score}.get(e.stage, 0.0)
            e.prev_stage_score = prev
            e.diff = e.score_pct - prev

    def _stage_state(self):
        return {'self': 'self_review', 'reviewer': 'appraisal', 'kpi_team': 'kpi_team', 'final': 'pending_approval'}

    def _check_permission(self):
        u = self.env.user
        for e in self:
            if self.env.context.get('kpi_internal'):
                continue
            st = e.assignment_id.state
            if st != e._stage_state()[e.stage]:
                raise UserError('Bước "%s" không mở để nhập ở trạng thái hiện tại của hồ sơ.' % dict(
                    self._fields['stage'].selection)[e.stage])
            if e.stage == 'self':
                a = e.assignment_id
                if not (u == a.employee_id.user_id or u in a._unit_users() or
                        u.has_group('z755_kpi.group_kpi_unit_editor') or u.has_group('z755_kpi.group_kpi_unit_manager')):
                    raise UserError('Bạn không thuộc đối tượng tự đánh giá của hồ sơ này.')
            elif e.stage == 'reviewer':
                if e.user_id and e.user_id != u and not u.has_group('z755_kpi.group_kpi_leader'):
                    raise UserError('Phiếu thẩm định này thuộc người thẩm định khác.')
            elif e.stage == 'kpi_team':
                if not (u.has_group('z755_kpi.group_kpi_member') or u.has_group('z755_kpi.group_kpi_leader')):
                    raise UserError('Chỉ Tổ KPI được nhập đề xuất.')
            elif e.stage == 'final':
                if not (u.has_group('z755_kpi.group_kpi_approver') or u.has_group('z755_kpi.group_kpi_leader')):
                    raise UserError('Chỉ cấp phê duyệt được nhập kết luận.')

    def write(self, vals):
        if {'score_pct', 'evaluation_comment', 'adjustment_reason', 'actual_value'} & set(vals):
            self._check_permission()
            if self.filtered('submitted') and 'submitted' not in vals:
                raise UserError('Phiếu đã gửi/xác nhận; chỉ được sửa khi hồ sơ bị trả lại.')
        return super().write(vals)

    def _requires_reason(self):
        self.ensure_one()
        period = self.line_id.period_id
        if not period.require_reason_on_diff or self.stage == 'self':
            return False
        prev = self.prev_stage_score
        return abs(self.score_pct - prev) > (period.diff_threshold or 0.0)

    @api.constrains('submitted', 'score_pct', 'adjustment_reason')
    def _check_reason(self):
        for e in self:
            if e.submitted and e._requires_reason() and not (e.adjustment_reason or '').strip():
                raise ValidationError(
                    'KPI "%s": điểm khác bước trước (%.2f → %.2f), bắt buộc nhập lý do điều chỉnh.' % (
                        e.line_id.kpi_name, e.prev_stage_score, e.score_pct))

    @api.constrains('score_pct')
    def _check_cap(self):
        for e in self:
            if e.score_pct < 0 or e.score_pct > e.line_id.score_cap:
                raise ValidationError('Điểm phải trong khoảng 0 - %s (điểm trần của dòng KPI).' % e.line_id.score_cap)

    def unlink(self):
        if not self.env.context.get('kpi_internal'):
            raise UserError('Không xóa phiếu đánh giá.')
        return super().unlink()

    def action_submit(self):
        self._check_permission()
        self.write({'submitted': True})
