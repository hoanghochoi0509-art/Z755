import json

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

from . import kpi_engine


class KpiAssignmentLine(models.Model):
    _name = 'kpi.assignment.line'
    _description = 'Dòng KPI theo kỳ'
    _inherit = ['kpi.audit.mixin']
    _order = 'assignment_id, sequence, id'

    _audit_fields = ('kpi_id', 'target_value', 'target_operator', 'weight_pct', 'score_cap',
                     'scoring_rule_id', 'inline_rule_id', 'due_date', 'responsible_id', 'actual_value')

    sequence = fields.Integer(default=10, string='Thứ tự')
    assignment_id = fields.Many2one('kpi.assignment', required=True, ondelete='cascade', index=True, string='Bảng giao')
    period_id = fields.Many2one(related='assignment_id.period_id', store=True, index=True)
    assignment_state = fields.Selection(related='assignment_id.state', store=True)
    object_type = fields.Selection(related='assignment_id.object_type', store=True)
    department_id = fields.Many2one(related='assignment_id.department_id', store=True)
    employee_id = fields.Many2one(related='assignment_id.employee_id', store=True)
    is_locked = fields.Boolean('Đã khóa (ảnh chụp)', default=False, copy=False)

    kpi_id = fields.Many2one('kpi.catalog', 'KPI', required=True, ondelete='restrict',
                             domain="[('state', '!=', 'retired')]")
    kpi_code = fields.Char(related='kpi_id.code', string='Mã KPI')
    kpi_name = fields.Char(compute='_compute_kpi_name', string='Nội dung KPI')
    kpi_type = fields.Selection(related='kpi_id.kpi_type', store=True)
    value_type = fields.Selection(related='kpi_id.value_type', store=True)
    uom_id = fields.Many2one('kpi.uom', 'ĐVT')
    target_operator = fields.Selection([('>=', '>='), ('<=', '<='), ('=', '='), ('>', '>'), ('<', '<')],
                                       'Toán tử', default='>=')
    target_value = fields.Float('Chỉ tiêu kỳ', digits=(16, 2))
    target_date = fields.Date('Ngày mục tiêu')
    target_text = fields.Text('Chỉ tiêu mô tả')
    weight_pct = fields.Float('Trọng số (%)', required=True, digits=(16, 2))
    score_cap = fields.Integer('Điểm trần', default=100, required=True)
    due_date = fields.Date('Hạn hoàn thành')
    output_product = fields.Text('Sản phẩm đầu ra')
    responsible_id = fields.Many2one('hr.employee', 'Chủ trì')
    collaborator_ids = fields.Many2many('hr.employee', 'kpi_line_collab_rel', 'line_id', 'employee_id', 'Phối hợp')
    data_source_id = fields.Many2one('kpi.data.source', 'Nguồn dữ liệu')
    review_department_ids = fields.Many2many('hr.department', 'kpi_line_revdept_rel', 'line_id', 'dept_id',
                                             'Cơ quan thẩm định')
    reviewer_ids = fields.Many2many('res.users', 'kpi_line_reviewer_rel', 'line_id', 'user_id',
                                    'Người thẩm định')
    approver_ids = fields.Many2many('res.users', 'kpi_line_approver_rel', 'line_id', 'user_id',
                                    'Người phê duyệt')
    approval_role = fields.Selection([('unit_manager', 'Chỉ huy đơn vị'), ('kpi_leader', 'Tổ trưởng KPI'),
                                      ('approver', 'Cấp phê duyệt')], 'Vai trò/cấp phê duyệt',
                                     default='approver')
    enhanced_control = fields.Boolean('Kiểm soát tăng cường',
                                      help='Bắt buộc thêm minh chứng/thẩm định.')

    # Quan hệ mục tiêu nhiều cấp
    parent_line_id = fields.Many2one('kpi.assignment.line', 'KPI/mục tiêu cấp trên', ondelete='restrict')
    child_line_ids = fields.One2many('kpi.assignment.line', 'parent_line_id', 'KPI cấp dưới')
    source_level = fields.Selection([('company', 'Công ty'), ('department', 'Đơn vị'),
                                     ('employee', 'Cá nhân')], 'Cấp nguồn')
    cascade_type = fields.Selection([('full', 'Giao nguyên chỉ tiêu'), ('allocation', 'Phân bổ chỉ tiêu'),
                                     ('reference', 'Tham chiếu mục tiêu'), ('independent', 'KPI độc lập')],
                                    'Kiểu phân rã/kế thừa', default='independent')
    allocated_target = fields.Float('Chỉ tiêu phân bổ')
    proposed_by_employee = fields.Boolean('Cá nhân đề xuất', copy=False)

    # Rule
    rule_mode = fields.Selection([('library', 'Thư viện'), ('inline', 'Cấu hình trực tiếp')],
                                 'Nguồn quy tắc chấm', default='library', required=True)
    scoring_rule_id = fields.Many2one('kpi.scoring.rule', 'Quy tắc (thư viện)',
                                      domain="[('is_inline', '=', False), ('state', '!=', 'retired')]")
    inline_rule_id = fields.Many2one('kpi.scoring.rule', 'Quy tắc trực tiếp', copy=False, ondelete='restrict')
    rule_method = fields.Selection(related='effective_rule_id.method', string='Phương pháp')
    effective_rule_id = fields.Many2one('kpi.scoring.rule', compute='_compute_effective_rule', store=True, string='Quy tắc đang áp dụng')
    save_rule_to_library = fields.Boolean('Lưu vào thư viện quy tắc', copy=False)

    # Snapshot (spec 14.1)
    snapshot_json = fields.Text('Ảnh chụp khi giao', readonly=True, copy=False)
    kpi_code_snapshot = fields.Char('Mã KPI lúc giao', readonly=True, copy=False)
    kpi_name_snapshot = fields.Text('Tên KPI lúc giao', readonly=True, copy=False)
    rule_version_snapshot = fields.Text('Phiên bản quy tắc lúc giao', readonly=True, copy=False)

    # Thực hiện
    actual_value = fields.Float('Kết quả thực tế', digits=(16, 2), copy=False)
    actual_entered = fields.Boolean('Đã nhập kết quả', copy=False)
    actual_date = fields.Date('Ngày hoàn thành thực tế', copy=False)
    actual_text = fields.Text('Diễn giải kết quả', copy=False)
    progress_pct = fields.Float('Tiến độ (%)', copy=False)
    objective_exception = fields.Boolean('Ngoại lệ khách quan', copy=False)
    exception_confirmed_by = fields.Many2one('res.users', 'Người xác nhận ngoại lệ', copy=False)
    exception_note = fields.Text('Nguyên nhân ngoại lệ', copy=False)
    evidence_ids = fields.One2many('kpi.evidence', 'line_id', 'Minh chứng')
    evidence_count = fields.Integer(compute='_compute_evidence_count', string='Số minh chứng')
    event_log_ids = fields.One2many('kpi.event.log', 'line_id', 'Nhật ký')
    weekly_review_ids = fields.Many2many('kpi.weekly.review', 'kpi_weekly_line_rel', 'line_id', 'review_id', string='Nhận xét tuần')
    evaluation_ids = fields.One2many('kpi.evaluation', 'line_id', 'Đánh giá')

    # Điểm (bốn khái niệm tách bạch + lưu từng bước)
    achievement_rate = fields.Float('Mức hoàn thành (%)', compute='_compute_system_score', store=True, digits=(16, 2))
    system_score = fields.Float('Điểm hệ thống', compute='_compute_system_score', store=True, digits=(16, 2))
    system_note = fields.Char('Ghi chú engine', compute='_compute_system_score', store=True)
    has_system_score = fields.Boolean(compute='_compute_system_score', store=True, string='Có điểm hệ thống')
    self_score = fields.Float('Điểm tự chấm', compute='_compute_stage_scores', store=True, digits=(16, 2))
    reviewer_score = fields.Float('Điểm thẩm định', compute='_compute_stage_scores', store=True, digits=(16, 2))
    team_score = fields.Float('Điểm Tổ KPI', compute='_compute_stage_scores', store=True, digits=(16, 2))
    final_score = fields.Float('Điểm kết luận', compute='_compute_stage_scores', store=True, digits=(16, 2))
    system_weighted = fields.Float('Điểm QĐ hệ thống', compute='_compute_weighted', store=True, digits=(16, 2))
    self_weighted = fields.Float('Điểm QĐ tự chấm', compute='_compute_weighted', store=True, digits=(16, 2))
    reviewer_weighted = fields.Float('Điểm QĐ thẩm định', compute='_compute_weighted', store=True, digits=(16, 2))
    team_weighted = fields.Float('Điểm QĐ Tổ KPI', compute='_compute_weighted', store=True, digits=(16, 2))
    final_weighted = fields.Float('Điểm QĐ kết luận', compute='_compute_weighted', store=True, digits=(16, 2))
    diff_flag = fields.Boolean('Có chênh lệch', compute='_compute_weighted', store=True)
    overdue = fields.Boolean('Quá hạn', compute='_compute_overdue', search='_search_overdue')

    def _audit_assignment(self):
        return self.assignment_id

    @api.depends('kpi_id.name', 'kpi_name_snapshot', 'is_locked')
    def _compute_kpi_name(self):
        for l in self:
            l.kpi_name = l.kpi_name_snapshot if (l.is_locked and l.kpi_name_snapshot) else l.kpi_id.name

    def _compute_evidence_count(self):
        for l in self:
            l.evidence_count = len(l.evidence_ids)

    @api.depends('rule_mode', 'scoring_rule_id', 'inline_rule_id')
    def _compute_effective_rule(self):
        for l in self:
            l.effective_rule_id = l.inline_rule_id if l.rule_mode == 'inline' else l.scoring_rule_id

    def _compute_overdue(self):
        today = fields.Date.context_today(self)
        for l in self:
            l.overdue = bool(l.due_date and l.due_date < today and
                             l.assignment_state in ('assigned', 'in_progress') and not l.actual_entered)

    def _search_overdue(self, operator, value):
        today = fields.Date.context_today(self)
        dom = [('due_date', '<', today), ('assignment_state', 'in', ('assigned', 'in_progress')),
               ('actual_entered', '=', False)]
        return dom if (operator == '=' and value) or (operator == '!=' and not value) else ['!'] + dom

    # ------------------------------------------------------------------
    def _rule_cfg(self):
        self.ensure_one()
        if self.is_locked and self.rule_version_snapshot:
            return json.loads(self.rule_version_snapshot)
        rule = self.effective_rule_id
        return rule.get_config() if rule else {}

    @api.depends('actual_value', 'actual_entered', 'target_value', 'target_operator', 'score_cap',
                 'effective_rule_id', 'effective_rule_id.method', 'effective_rule_id.line_ids',
                 'actual_date', 'due_date', 'objective_exception', 'is_locked', 'rule_version_snapshot',
                 'event_log_ids.state', 'event_log_ids.severity', 'event_log_ids.affects_score')
    def _compute_system_score(self):
        for l in self:
            cfg = l._rule_cfg()
            if not cfg:
                l.system_score, l.achievement_rate, l.system_note, l.has_system_score = 0.0, 0.0, 'Chưa có quy tắc', False
                continue
            events = l.event_log_ids.filtered(
                lambda e: e.state == 'confirmed' and e.affects_score).mapped('severity')
            delay = None
            if l.due_date and l.actual_date:
                delay = (l.actual_date - l.due_date).days
            res = kpi_engine.compute_score(
                cfg, l.target_operator, l.target_value, l.actual_value, l.actual_entered, delay, events,
                objective_exception=l.objective_exception and bool(l.exception_confirmed_by),
                score_cap=l.score_cap)
            digits = l.period_id.score_digits if l.period_id else 2
            l.has_system_score = res['score'] is not None
            l.system_score = round(res['score'], digits) if res['score'] is not None else 0.0
            l.achievement_rate = round(res['rate'], digits) if res['rate'] is not None else 0.0
            l.system_note = res['note']

    @api.depends('evaluation_ids.score_pct', 'evaluation_ids.stage', 'evaluation_ids.submitted',
                 'system_score', 'period_id.reviewer_agg_method')
    def _compute_stage_scores(self):
        for l in self:
            def stage_scores(stage):
                return l.evaluation_ids.filtered(lambda e: e.stage == stage)
            selfs = stage_scores('self')
            l.self_score = selfs[:1].score_pct if selfs else 0.0
            revs = stage_scores('reviewer')
            method = l.period_id.reviewer_agg_method or 'primary'
            if revs:
                vals = revs.mapped('score_pct')
                if method == 'average':
                    l.reviewer_score = sum(vals) / len(vals)
                elif method == 'primary':
                    prim = revs.filtered('is_primary')[:1] or revs[:1]
                    l.reviewer_score = prim.score_pct
                else:  # team_decides: giữ trung bình để tham khảo, Tổ KPI chốt ở bước sau
                    l.reviewer_score = sum(vals) / len(vals)
            else:
                l.reviewer_score = 0.0
            team = stage_scores('kpi_team')
            l.team_score = team[:1].score_pct if team else 0.0
            fin = stage_scores('final')
            l.final_score = fin[:1].score_pct if fin else 0.0

    @api.depends('weight_pct', 'system_score', 'self_score', 'reviewer_score', 'team_score', 'final_score',
                 'period_id.round_at', 'period_id.score_digits', 'period_id.diff_threshold')
    def _compute_weighted(self):
        for l in self:
            w = l.weight_pct / 100.0
            digits = l.period_id.score_digits if l.period_id and l.period_id.round_at == 'line' else 6
            l.system_weighted = round(l.system_score * w, digits)
            l.self_weighted = round(l.self_score * w, digits)
            l.reviewer_weighted = round(l.reviewer_score * w, digits)
            l.team_weighted = round(l.team_score * w, digits)
            l.final_weighted = round(l.final_score * w, digits)
            thr = l.period_id.diff_threshold or 0.0
            l.diff_flag = bool(l.self_score and l.reviewer_score and abs(l.self_score - l.reviewer_score) > thr)

    # ------------------------------------------------------------------
    @api.constrains('weight_pct', 'score_cap')
    def _check_values(self):
        for l in self:
            if l.weight_pct < 0 or l.weight_pct > 100:
                raise ValidationError('Trọng số phải trong khoảng 0-100%.')
            if l.score_cap <= 0:
                raise ValidationError('Điểm trần phải > 0.')

    @api.constrains('kpi_id', 'assignment_id')
    def _check_dup(self):
        for l in self:
            dup = self.search_count([('assignment_id', '=', l.assignment_id.id), ('kpi_id', '=', l.kpi_id.id),
                                     ('id', '!=', l.id)])
            if dup:
                raise ValidationError('KPI "%s" đã có trong bảng giao này.' % l.kpi_id.name)

    @api.onchange('kpi_id')
    def _onchange_kpi(self):
        if self.kpi_id:
            self.uom_id = self.kpi_id.uom_id
            if not self.responsible_id and self.assignment_id.department_id.manager_id:
                self.responsible_id = self.assignment_id.department_id.manager_id

    @api.onchange('parent_line_id')
    def _onchange_parent(self):
        if self.parent_line_id:
            self.source_level = self.parent_line_id.object_type
            if self.cascade_type == 'independent':
                self.cascade_type = 'reference'
            if self.cascade_type == 'full':
                self.target_value = self.parent_line_id.target_value

    @api.onchange('rule_mode')
    def _onchange_rule_mode(self):
        if self.rule_mode == 'inline' and not self.inline_rule_id and not self.effective_rule_id:
            pass

    @api.onchange('scoring_rule_id')
    def _onchange_rule(self):
        if self.scoring_rule_id and self.rule_mode == 'library':
            self.score_cap = self.scoring_rule_id.score_cap

    def _readiness_problems(self):
        problems = []
        for l in self:
            n = l.kpi_id.name or '?'
            if not l.effective_rule_id:
                problems.append('%s: thiếu quy tắc chấm.' % n)
            if not l.data_source_id:
                problems.append('%s: thiếu nguồn dữ liệu.' % n)
            if not l.responsible_id:
                problems.append('%s: thiếu chủ trì.' % n)
            if not (l.reviewer_ids or l.review_department_ids) and not l.assignment_id._is_personal():
                problems.append('%s: thiếu cơ quan/người thẩm định.' % n)
            if not l.approval_role and not l.approver_ids:
                problems.append('%s: thiếu vai trò/người phê duyệt.' % n)
            if l.value_type in ('percentage', 'count', 'currency', 'duration') and not l.target_value \
                    and l.effective_rule_id.method not in ('INCIDENT_COUNT', 'LEVEL', 'BINARY', 'MANUAL', 'DATE_DELAY'):
                problems.append('%s: chỉ tiêu bằng 0, cần dùng quy tắc sự kiện.' % n)
            if l.enhanced_control and not l.evidence_ids and l.assignment_id.state in ('self_review',):
                problems.append('%s: kiểm soát tăng cường yêu cầu minh chứng.' % n)
            if l.kpi_id.state == 'retired':
                problems.append('%s: KPI đã ngừng dùng.' % n)
        return problems

    def _take_snapshot(self):
        """Chụp toàn bộ cấu hình khi phê duyệt giao (spec 14.1)."""
        for l in self:
            # lưu rule inline vào thư viện nếu được chọn
            if l.save_rule_to_library and l.inline_rule_id and l.inline_rule_id.is_inline:
                l.inline_rule_id.action_save_to_library()
            cfg = l.effective_rule_id.get_config() if l.effective_rule_id else {}
            a = l.assignment_id
            snap = {
                'kpi_code': l.kpi_id.code, 'kpi_name': l.kpi_id.name, 'target_operator': l.target_operator,
                'target_value': l.target_value, 'target_date': str(l.target_date or ''),
                'target_text': l.target_text or '', 'weight_pct': l.weight_pct,
                'uom': l.uom_id.name or '', 'due_date': str(l.due_date or ''),
                'score_cap': l.score_cap, 'output_product': l.output_product or '',
                'data_source': l.data_source_id.name or '',
                'responsible': l.responsible_id.name or '', 'responsible_job': l.responsible_id.job_id.name or '',
                'collaborators': l.collaborator_ids.mapped('name'),
                'review_departments': l.review_department_ids.mapped('name'),
                'reviewers': l.reviewer_ids.mapped('name'), 'approvers': l.approver_ids.mapped('name'),
                'approval_role': l.approval_role or '',
                'department': a.department_id.name or '', 'employee': a.employee_id.name or '',
                'job': a.employee_id.job_id.name or '',
                'regulation': a.period_id.regulation_ref or '', 'config_version': a.period_id.config_version or '',
                'assignment_version': a.assignment_version,
                'parent_line': l.parent_line_id.kpi_id.name or '', 'parent_line_id': l.parent_line_id.id,
                'source_level': l.source_level or '', 'cascade_type': l.cascade_type or '',
                'allocated_target': l.allocated_target, 'rule_mode': l.rule_mode, 'rule': cfg,
            }
            l.with_context(kpi_internal=True).write({
                'snapshot_json': json.dumps(snap, ensure_ascii=False),
                'kpi_code_snapshot': l.kpi_id.code, 'kpi_name_snapshot': l.kpi_id.name,
                'rule_version_snapshot': json.dumps(cfg, ensure_ascii=False),
            })

    # ------------------------------------------------------------------
    # Khóa chỉnh sửa sau giao
    # ------------------------------------------------------------------
    _locked_fields = {'kpi_id', 'target_operator', 'target_value', 'target_date', 'target_text', 'weight_pct',
                      'score_cap', 'due_date', 'output_product', 'responsible_id', 'data_source_id',
                      'scoring_rule_id', 'inline_rule_id', 'rule_mode', 'parent_line_id', 'cascade_type',
                      'allocated_target', 'reviewer_ids', 'approver_ids', 'review_department_ids', 'approval_role'}

    def write(self, vals):
        if not self.env.context.get('kpi_internal') and self._locked_fields & set(vals):
            if self.filtered('is_locked'):
                raise UserError('Dòng KPI đã giao bị khóa. Hãy dùng "Điều chỉnh bảng giao" (có lý do & phiên bản).')
        if self.filtered(lambda l: l.assignment_state == 'locked') and not self.env.context.get('kpi_internal'):
            raise UserError('Kỳ đã khóa - hồ sơ chỉ đọc.')
        if {'actual_value', 'actual_date'} & set(vals):
            vals.setdefault('actual_entered', True)
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        for v in vals_list:
            a = self.env['kpi.assignment'].browse(v.get('assignment_id'))
            if a and a.state not in ('draft', 'negotiating') and not self.env.context.get('kpi_internal'):
                raise UserError('Bảng giao đã trình/giao: không thêm dòng. Dùng "Điều chỉnh bảng giao".')
        return super().create(vals_list)

    def unlink(self):
        for l in self:
            if l.is_locked or l.assignment_id.state not in ('draft', 'negotiating'):
                raise UserError('Không xóa dòng KPI đã giao/tham gia kỳ phê duyệt.')
        return super().unlink()

    # ------------------------------------------------------------------
    # Tạo inline
    # ------------------------------------------------------------------
    def action_create_inline_rule(self):
        self.ensure_one()
        if not self.period_id.allow_inline_rule:
            raise UserError('Kỳ không cho phép quy tắc trực tiếp.')
        if self.is_locked:
            raise UserError('Dòng đã khóa.')
        rule = self.env['kpi.scoring.rule'].create({
            'name': 'Quy tắc dòng %s' % (self.kpi_id.name or ''), 'is_inline': True,
            'method': 'RATE', 'score_cap': self.score_cap})
        self.write({'rule_mode': 'inline', 'inline_rule_id': rule.id})
        return {'type': 'ir.actions.act_window', 'res_model': 'kpi.scoring.rule', 'res_id': rule.id,
                'view_mode': 'form', 'target': 'new'}

    def action_edit_inline_rule(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'kpi.scoring.rule',
                'res_id': self.inline_rule_id.id, 'view_mode': 'form', 'target': 'new'}

    def action_add_evidence(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'kpi.evidence', 'view_mode': 'form',
                'target': 'new', 'context': {'default_line_id': self.id}}

    def action_open_form(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'kpi.assignment.line', 'res_id': self.id,
                'view_mode': 'form', 'target': 'current'}
