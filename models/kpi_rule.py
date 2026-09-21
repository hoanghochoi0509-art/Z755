from odoo import api, fields, models
from odoo.exceptions import UserError

METHODS = [
    ('RATE', 'RATE - Thực hiện/Kế hoạch'),
    ('REVERSE_RATE', 'REVERSE_RATE - Càng thấp càng tốt'),
    ('THRESHOLD', 'THRESHOLD - Theo ngưỡng'),
    ('DATE_DELAY', 'DATE_DELAY - Trừ theo ngày chậm'),
    ('INCIDENT_COUNT', 'INCIDENT_COUNT - Trừ theo số lỗi/sự cố'),
    ('LEVEL', 'LEVEL - Theo mức độ lỗi'),
    ('BINARY', 'BINARY - Đạt/Không đạt'),
    ('MANUAL', 'MANUAL - Nhập điểm có thẩm định'),
]


class KpiScoringRule(models.Model):
    _name = 'kpi.scoring.rule'
    _description = 'Quy tắc chấm điểm KPI'
    _inherit = ['mail.thread', 'kpi.audit.mixin']
    _order = 'code, version desc'

    _audit_fields = ('method', 'score_cap', 'score_floor', 'combine_mode', 'exception_deduct_pct', 'state')

    code = fields.Char('Mã quy tắc', copy=False, readonly=True, default='Mới')
    name = fields.Char('Tên quy tắc', required=True, tracking=True)
    version = fields.Integer('Phiên bản', default=1, copy=False, readonly=True)
    method = fields.Selection(METHODS, 'Phương pháp', required=True, default='RATE', tracking=True)
    scope = fields.Selection([('company', 'Toàn công ty'), ('group', 'Nhóm KPI'),
                              ('kpi', 'KPI cụ thể'), ('object_type', 'Loại đối tượng')],
                             'Phạm vi', default='company')
    state = fields.Selection([('proposed', 'Đề xuất'), ('confirmed', 'Đã xác nhận'),
                              ('retired', 'Ngừng dùng')], default='proposed', tracking=True, string='Trạng thái')
    score_cap = fields.Integer('Điểm trần mặc định', default=100,
                               help='Tham số cấu hình (100/110/120/khác); dòng KPI có thể ghi đè.')
    score_floor = fields.Float('Điểm sàn', default=0.0)
    combine_mode = fields.Selection([('sum', 'Cộng dồn các mức trừ'), ('max', 'Lấy mức trừ lớn nhất'),
                                     ('multiply', 'Nhân hệ số')], 'Kết hợp nhiều điều kiện/sự việc',
                                    default='sum', required=True)
    exception_deduct_pct = fields.Float('Trừ khi có ngoại lệ khách quan (%)', default=0.0,
                                        help='Chỉ áp dụng khi dòng KPI có ngoại lệ được người có thẩm quyền xác nhận.')
    priority_note = fields.Char('Nguyên tắc ưu tiên', default='Điều kiện đầu tiên theo thứ tự (Sequence) thỏa mãn được áp dụng.')
    valid_from = fields.Date('Hiệu lực từ')
    valid_to = fields.Date('Hiệu lực đến')
    description = fields.Text('Mô tả')
    is_inline = fields.Boolean('Quy tắc trực tiếp tại dòng KPI', default=False, copy=False,
                               help='Chỉ dùng trong hồ sơ; chưa là quy tắc thư viện dùng chung.')
    line_ids = fields.One2many('kpi.scoring.rule.line', 'rule_id', 'Điều kiện/hành động', copy=True)
    previous_rule_id = fields.Many2one('kpi.scoring.rule', 'Phiên bản trước', copy=False, readonly=True)
    kpi_line_ids = fields.One2many('kpi.assignment.line', 'scoring_rule_id', 'Dòng KPI dùng quy tắc')
    usage_count = fields.Integer('Số dòng KPI dùng', compute='_compute_usage')

    _sql_constraints = [('code_version_uniq', 'unique(code, version)', 'Mã + phiên bản quy tắc phải duy nhất.')]

    @api.depends('kpi_line_ids')
    def _compute_usage(self):
        for r in self:
            r.usage_count = len(r.kpi_line_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for v in vals_list:
            if not v.get('code') or v.get('code') == 'Mới':
                seq = 'kpi.scoring.rule.inline' if v.get('is_inline') else 'kpi.scoring.rule'
                v['code'] = self.env['ir.sequence'].next_by_code(seq) or 'Mới'
        return super().create(vals_list)

    def get_config(self):
        """Cấu hình dạng dict, dùng cho engine và ảnh chụp."""
        self.ensure_one()
        return {
            'rule_id': self.id, 'code': self.code, 'name': self.name, 'version': self.version,
            'method': self.method, 'score_cap': self.score_cap, 'score_floor': self.score_floor,
            'combine_mode': self.combine_mode, 'exception_deduct_pct': self.exception_deduct_pct,
            'lines': [{
                'sequence': l.sequence, 'label': l.label, 'op': l.condition_op, 'threshold': l.threshold,
                'level': l.level, 'action': l.action, 'value': l.value, 'step': l.step,
            } for l in self.line_ids.sorted('sequence')],
        }

    def action_confirm(self):
        self.write({'state': 'confirmed'})

    def action_retire(self):
        self.write({'state': 'retired'})

    def action_save_to_library(self):
        """Lưu quy tắc trực tiếp thành quy tắc thư viện: sinh mã/phiên bản mới, không đổi kỳ đã ảnh chụp."""
        for r in self:
            if not r.is_inline:
                continue
            r.write({
                'is_inline': False,
                'code': self.env['ir.sequence'].next_by_code('kpi.scoring.rule') or r.code,
                'version': 1, 'state': 'proposed',
            })

    def action_new_version(self):
        self.ensure_one()
        if self.is_inline:
            raise UserError('Hãy lưu quy tắc vào thư viện trước khi tạo phiên bản mới.')
        last = self.search([('code', '=', self.code)], order='version desc', limit=1)
        new = self.copy({'code': self.code, 'version': last.version + 1, 'previous_rule_id': self.id,
                         'state': 'proposed'})
        return {'type': 'ir.actions.act_window', 'res_model': 'kpi.scoring.rule',
                'res_id': new.id, 'view_mode': 'form', 'target': 'current'}

    def write(self, vals):
        cfg_fields = {'method', 'score_cap', 'score_floor', 'combine_mode', 'exception_deduct_pct'}
        if cfg_fields & set(vals):
            for r in self:
                if r.kpi_line_ids.filtered('is_locked') and not self.env.context.get('kpi_allow_rule_edit'):
                    raise UserError('Quy tắc "%s" đang được ảnh chụp vào kỳ đã giao; hãy tạo phiên bản mới.' % r.display_name)
        return super().write(vals)

    def unlink(self):
        for r in self:
            if r.kpi_line_ids:
                raise UserError('Quy tắc "%s" đang/đã được dùng trong bảng giao, không được xóa.' % r.display_name)
        return super().unlink()

    @api.depends('code', 'name', 'version')
    def _compute_display_name(self):
        for r in self:
            r.display_name = '[%s v%s] %s' % (r.code, r.version, r.name) if r.code else r.name


class KpiScoringRuleLine(models.Model):
    _name = 'kpi.scoring.rule.line'
    _description = 'Chi tiết quy tắc chấm'
    _order = 'sequence, id'

    rule_id = fields.Many2one('kpi.scoring.rule', required=True, ondelete='cascade', string='Quy tắc chấm')
    sequence = fields.Integer('Ưu tiên', default=10)
    label = fields.Char('Diễn giải')
    condition_op = fields.Selection([('>=', '>='), ('<=', '<='), ('=', '='), ('>', '>'), ('<', '<')],
                                    'Toán tử', default='>=')
    threshold = fields.Float('Ngưỡng')
    level = fields.Selection([('light', 'Nhẹ'), ('medium', 'Vừa'), ('heavy', 'Nặng'),
                              ('critical', 'Nghiêm trọng')], 'Mức độ')
    action = fields.Selection([
        ('set_score', 'Gán điểm'), ('deduct_pct', 'Trừ %'), ('factor', 'Nhân hệ số'),
        ('zero', 'Đặt 0 điểm')], 'Hành động', default='deduct_pct', required=True)
    value = fields.Float('Giá trị (điểm / % trừ / hệ số)')
    step = fields.Float('Bước (ngày chậm N)', default=1.0,
                        help='DATE_DELAY: mỗi N ngày chậm trừ X%.')
