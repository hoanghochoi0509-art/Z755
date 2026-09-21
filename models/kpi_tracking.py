from odoo import api, fields, models
from odoo.exceptions import UserError


class KpiEvidence(models.Model):
    _name = 'kpi.evidence'
    _description = 'Minh chứng KPI'
    _order = 'id desc'

    line_id = fields.Many2one('kpi.assignment.line', 'Dòng KPI', required=True, ondelete='cascade', index=True)
    assignment_id = fields.Many2one(related='line_id.assignment_id', store=True, string='Bảng giao')
    name = fields.Char('Tên/Số chứng từ', required=True)
    evidence_type = fields.Selection([('file', 'File đính kèm'), ('doc_no', 'Số chứng từ'),
                                      ('minutes', 'Biên bản'), ('report', 'Báo cáo'),
                                      ('link', 'Liên kết record/hệ thống khác')], 'Loại', default='file', required=True)
    attachment_ids = fields.Many2many('ir.attachment', string='Tệp')
    link_url = fields.Char('Liên kết')
    ref_model = fields.Char('Mô hình nguồn')
    ref_res_id = fields.Integer('ID bản ghi nguồn')
    snapshot_value = fields.Char('Ảnh chụp số liệu tại thời điểm chốt')
    note = fields.Text('Ghi chú')
    uploaded_by = fields.Many2one('res.users', 'Người tải lên', default=lambda s: s.env.user, readonly=True)
    uploaded_at = fields.Datetime('Thời gian', default=fields.Datetime.now, readonly=True)

    def _check_open(self):
        for e in self:
            if e.line_id.assignment_state in ('locked', 'approved'):
                raise UserError('Hồ sơ đã phê duyệt/khóa, không sửa minh chứng.')

    def write(self, vals):
        self._check_open()
        return super().write(vals)

    def unlink(self):
        self._check_open()
        return super().unlink()


class KpiEventLog(models.Model):
    _name = 'kpi.event.log'
    _description = 'Nhật ký sự việc KPI'
    _inherit = ['mail.thread']
    _order = 'event_datetime desc'

    name = fields.Char('Nội dung', required=True)
    event_datetime = fields.Datetime('Thời điểm sự việc', required=True, default=fields.Datetime.now)
    recorded_at = fields.Datetime('Thời điểm ghi nhận', default=fields.Datetime.now, readonly=True)
    period_id = fields.Many2one('kpi.period', 'Kỳ', compute='_compute_period', store=True, readonly=False)
    assignment_id = fields.Many2one('kpi.assignment', 'Bảng giao', index=True)
    line_id = fields.Many2one('kpi.assignment.line', 'KPI liên quan', domain="[('assignment_id','=',assignment_id)]")
    department_id = fields.Many2one('hr.department', 'Đơn vị liên quan')
    employee_id = fields.Many2one('hr.employee', 'Cá nhân liên quan')
    severity = fields.Selection([('info', 'Thông tin'), ('light', 'Nhẹ'), ('medium', 'Vừa'),
                                 ('heavy', 'Nặng'), ('critical', 'Nghiêm trọng')], 'Mức độ', default='light')
    affects_score = fields.Boolean('Ảnh hưởng điểm', default=False)
    rule_id = fields.Many2one('kpi.scoring.rule', 'Quy tắc áp dụng')
    evidence_ids = fields.Many2many('ir.attachment', string='Minh chứng')
    evidence_note = fields.Char('Link minh chứng')
    confirmed_by = fields.Many2one('res.users', 'Người xác nhận', readonly=True, copy=False)
    confirmed_at = fields.Datetime('Xác nhận lúc', readonly=True, copy=False)
    state = fields.Selection([('new', 'Mới'), ('confirmed', 'Đã xác nhận'), ('cancelled', 'Đã hủy')],
                             'Trạng thái', default='new', tracking=True)
    cancel_reason = fields.Text('Lý do hủy', copy=False)
    user_id = fields.Many2one('res.users', 'Người ghi', default=lambda s: s.env.user, readonly=True)

    @api.depends('assignment_id')
    def _compute_period(self):
        for r in self:
            if r.assignment_id:
                r.period_id = r.assignment_id.period_id

    @api.onchange('line_id')
    def _onchange_line(self):
        if self.line_id:
            self.assignment_id = self.line_id.assignment_id

    @api.onchange('affects_score', 'line_id')
    def _onchange_rule(self):
        if self.affects_score and self.line_id and not self.rule_id:
            self.rule_id = self.line_id.effective_rule_id

    def action_confirm(self):
        u = self.env.user
        if not (u.has_group('z755_kpi.group_kpi_unit_manager') or u.has_group('z755_kpi.group_kpi_member')
                or u.has_group('z755_kpi.group_kpi_leader') or u.has_group('z755_kpi.group_kpi_assigner')):
            raise UserError('Bạn không có thẩm quyền xác nhận sự việc.')
        self.write({'state': 'confirmed', 'confirmed_by': u.id, 'confirmed_at': fields.Datetime.now()})

    def action_cancel(self):
        for r in self:
            if not r.cancel_reason:
                raise UserError('Nhập lý do hủy trước khi hủy sự việc.')
        self.write({'state': 'cancelled'})

    def unlink(self):
        raise UserError('Không xóa sự việc KPI; hãy hủy có lý do.')


class KpiWeeklyReview(models.Model):
    _name = 'kpi.weekly.review'
    _description = 'Nhận xét KPI tuần'
    _inherit = ['mail.thread']
    _order = 'date_from desc, id desc'

    name = fields.Char(compute='_compute_name', store=True, string='Tên nhận xét')
    period_id = fields.Many2one('kpi.period', 'Kỳ KPI', required=True)
    week_no = fields.Integer('Tuần số')
    date_from = fields.Date('Từ ngày', required=True)
    date_to = fields.Date('Đến ngày', required=True)
    assignment_id = fields.Many2one('kpi.assignment', 'Đối tượng (bảng giao)', required=True, index=True)
    department_id = fields.Many2one(related='assignment_id.department_id', store=True)
    employee_id = fields.Many2one(related='assignment_id.employee_id', store=True)
    line_ids = fields.Many2many('kpi.assignment.line', 'kpi_weekly_line_rel', 'review_id', 'line_id',
                                'KPI liên quan', domain="[('assignment_id','=',assignment_id)]")
    good_work = fields.Text('Việc làm tốt')
    delayed_work = fields.Text('Việc chậm/vướng mắc')
    cause = fields.Text('Nguyên nhân')
    remedy_request = fields.Text('Yêu cầu khắc phục')
    remedy_owner_id = fields.Many2one('res.users', 'Người phụ trách khắc phục')
    remedy_deadline = fields.Date('Hạn khắc phục')
    reviewer_id = fields.Many2one('res.users', 'Người nhận xét', default=lambda s: s.env.user, readonly=True)
    reviewed_at = fields.Datetime('Thời điểm', default=fields.Datetime.now, readonly=True)
    state = fields.Selection([('draft', 'Nháp'), ('confirmed', 'Đã xác nhận')], default='draft', tracking=True, string='Trạng thái')

    @api.depends('week_no', 'assignment_id.target_name')
    def _compute_name(self):
        for r in self:
            r.name = 'Tuần %s - %s' % (r.week_no or '', r.assignment_id.target_name or '')

    @api.onchange('assignment_id')
    def _onchange_assignment(self):
        if self.assignment_id:
            self.period_id = self.assignment_id.period_id

    @api.onchange('date_from')
    def _onchange_date(self):
        if self.date_from:
            self.week_no = self.date_from.isocalendar()[1]
            if not self.date_to:
                self.date_to = fields.Date.add(self.date_from, days=6)

    def action_confirm(self):
        for r in self:
            if r.remedy_request and r.remedy_owner_id:
                r.assignment_id.sudo().activity_schedule(
                    'mail.mail_activity_data_todo', user_id=r.remedy_owner_id.id,
                    date_deadline=r.remedy_deadline or fields.Date.today(),
                    summary='[KPI] Khắc phục: %s' % (r.remedy_request or '')[:80], note=r.remedy_request)
        self.write({'state': 'confirmed'})

    def unlink(self):
        if self.filtered(lambda r: r.state == 'confirmed'):
            raise UserError('Nhận xét đã xác nhận không được xóa.')
        return super().unlink()
