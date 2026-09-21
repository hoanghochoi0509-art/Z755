from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class KpiPeriod(models.Model):
    _name = 'kpi.period'
    _description = 'Kỳ KPI'
    _inherit = ['mail.thread', 'kpi.audit.mixin']
    _order = 'date_start desc'

    _audit_fields = ('data_cutoff_datetime', 'deadline_assign', 'deadline_self', 'deadline_appraisal',
                     'deadline_approval', 'reviewer_agg_method', 'score_digits', 'regulation_ref')

    name = fields.Char('Tên kỳ', required=True, tracking=True)
    code = fields.Char('Mã kỳ', required=True, copy=False, tracking=True)
    period_type = fields.Selection([('month', 'Tháng'), ('quarter', 'Quý'), ('year', 'Năm')],
                                   'Loại kỳ', default='month', required=True)
    date_start = fields.Date('Bắt đầu', required=True)
    date_end = fields.Date('Kết thúc', required=True)
    state = fields.Selection([('draft', 'Nháp'), ('open', 'Đang mở'), ('closed', 'Đã đóng'),
                              ('locked', 'Đã khóa')], default='draft', tracking=True, required=True, string='Trạng thái')
    company_id = fields.Many2one('res.company', default=lambda s: s.env.company, string='Công ty')

    # Quy chế áp dụng (spec 3.3)
    regulation_ref = fields.Char('Văn bản/quy chế áp dụng', tracking=True,
                                 help='Mã văn bản, ví dụ 02/KH-KPI. Bắt buộc trước khi vận hành chính thức.')
    regulation_effective_date = fields.Date('Ngày hiệu lực')
    config_version = fields.Char('Phiên bản cấu hình', default='pilot-1')
    regulation_is_draft = fields.Boolean('Căn cứ còn ở trạng thái dự thảo', default=True)

    # Cấu hình theo kỳ
    allow_inline_kpi = fields.Boolean('Cho phép tạo KPI mới khi giao', default=True)
    allow_inline_rule = fields.Boolean('Cho phép quy tắc trực tiếp', default=True)
    data_cutoff_datetime = fields.Datetime('Mốc chốt dữ liệu', required=True, tracking=True)
    deadline_assign = fields.Datetime('Hạn giao KPI')
    deadline_self = fields.Datetime('Hạn tự đánh giá', required=True)
    deadline_appraisal = fields.Datetime('Hạn thẩm định', required=True)
    deadline_approval = fields.Datetime('Hạn phê duyệt', required=True)
    reviewer_agg_method = fields.Selection([
        ('average', 'Trung bình các reviewer'), ('primary', 'Reviewer chính'),
        ('team_decides', 'Hội ý Tổ KPI quyết định')], 'Tổng hợp nhiều reviewer',
        default='primary', required=True)
    score_digits = fields.Integer('Số chữ số thập phân', default=2)
    round_at = fields.Selection([('line', 'Làm tròn từng dòng'), ('total', 'Làm tròn ở tổng')],
                                'Thời điểm làm tròn', default='line', required=True)
    total_cap_mode = fields.Selection([('none', 'Không giới hạn tổng'), ('cap100', 'Giới hạn tổng ở 100')],
                                      'Điểm trần > 100 ở cấp tổng', default='none', required=True)
    require_reason_on_diff = fields.Boolean('Bắt buộc lý do khi thẩm định khác tự chấm', default=True)
    diff_threshold = fields.Float('Ngưỡng chênh lệch cần giải trình (điểm)', default=0.0)
    personal_use_kpi_team = fields.Boolean('KPI cá nhân: có bước Tổ KPI', default=False)
    personal_use_approval = fields.Boolean('KPI cá nhân: có bước phê duyệt', default=True)

    assignment_ids = fields.One2many('kpi.assignment', 'period_id', 'Bảng giao')
    assignment_count = fields.Integer(compute='_compute_counts', string='Số bảng giao')
    progress = fields.Float('Tiến độ (%)', compute='_compute_counts')
    cutoff_warning = fields.Char(compute='_compute_cutoff_warning', string='Cảnh báo mốc chốt')

    _sql_constraints = [('code_uniq', 'unique(code)', 'Mã kỳ phải duy nhất.')]

    @api.depends('assignment_ids.state')
    def _compute_counts(self):
        for p in self:
            n = len(p.assignment_ids)
            done = len(p.assignment_ids.filtered(lambda a: a.state in ('approved', 'locked')))
            p.assignment_count = n
            p.progress = (done * 100.0 / n) if n else 0.0

    @api.depends('data_cutoff_datetime', 'deadline_self', 'deadline_appraisal', 'deadline_approval')
    def _compute_cutoff_warning(self):
        for p in self:
            p.cutoff_warning = p._cutoff_problem() or False

    def _cutoff_problem(self):
        self.ensure_one()
        c, s, a, ap = (self.data_cutoff_datetime, self.deadline_self,
                       self.deadline_appraisal, self.deadline_approval)
        if not (c and s and a and ap):
            return False
        if c > s:
            return 'Mốc chốt dữ liệu phải trước hoặc bằng hạn tự đánh giá.'
        if not (s <= a <= ap):
            return 'Hạn phải theo thứ tự: tự đánh giá ≤ thẩm định ≤ phê duyệt.'
        if self.deadline_assign and self.deadline_assign > c:
            return 'Hạn giao KPI phải trước mốc chốt dữ liệu.'
        return False

    @api.constrains('data_cutoff_datetime', 'deadline_self', 'deadline_appraisal',
                    'deadline_approval', 'deadline_assign', 'date_start', 'date_end')
    def _check_dates(self):
        for p in self:
            if p.date_start > p.date_end:
                raise ValidationError('Ngày bắt đầu phải trước ngày kết thúc.')
            msg = p._cutoff_problem()
            if msg:
                raise ValidationError(msg)

    def action_open(self):
        self.write({'state': 'open'})

    def action_close(self):
        self.write({'state': 'closed'})

    def action_draft(self):
        self.write({'state': 'draft'})

    def action_lock(self):
        for p in self:
            pending = p.assignment_ids.filtered(lambda a: a.state not in ('approved', 'locked'))
            if pending:
                raise UserError('Còn %d bảng KPI chưa phê duyệt: %s' % (
                    len(pending), ', '.join(pending.mapped('name'))))
            p.assignment_ids.filtered(lambda a: a.state == 'approved').action_lock()
            p.state = 'locked'

    def action_copy_period(self):
        """Sao chép cấu hình kỳ và các bảng giao sang kỳ kế tiếp (nháp)."""
        self.ensure_one()
        delta = {'month': relativedelta(months=1), 'quarter': relativedelta(months=3),
                 'year': relativedelta(years=1)}[self.period_type]
        new_start = self.date_start + delta
        new = self.copy({
            'name': '%s (sao chép)' % self.name,
            'code': '%s-COPY-%s' % (self.code, fields.Datetime.now().strftime('%H%M%S')),
            'date_start': new_start,
            'date_end': self.date_end + delta,
            'state': 'draft',
            'data_cutoff_datetime': self.data_cutoff_datetime + delta,
            'deadline_assign': self.deadline_assign and self.deadline_assign + delta,
            'deadline_self': self.deadline_self + delta,
            'deadline_appraisal': self.deadline_appraisal + delta,
            'deadline_approval': self.deadline_approval + delta,
        })
        for a in self.assignment_ids:
            a.copy_to_period(new)
        return {'type': 'ir.actions.act_window', 'res_model': 'kpi.period',
                'res_id': new.id, 'view_mode': 'form', 'target': 'current'}

    def action_view_assignments(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'name': 'Bảng giao KPI', 'res_model': 'kpi.assignment',
                'view_mode': 'list,form', 'domain': [('period_id', '=', self.id)],
                'context': {'default_period_id': self.id}}

    def unlink(self):
        for p in self:
            if p.assignment_ids:
                raise UserError('Không xóa kỳ đã có bảng giao KPI; hãy đóng kỳ.')
        return super().unlink()
