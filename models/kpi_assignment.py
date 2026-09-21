from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare

STATES = [
    ('draft', 'Dự thảo'), ('negotiating', 'Thảo luận/thống nhất'), ('submit_assign', 'Trình giao'),
    ('assigned', 'Đã giao'), ('in_progress', 'Đang thực hiện'), ('self_review', 'Tự đánh giá'),
    ('appraisal', 'Thẩm định'), ('kpi_team', 'Tổ KPI đề xuất'), ('pending_approval', 'Chờ phê duyệt'),
    ('approved', 'Đã phê duyệt'), ('locked', 'Khóa kỳ'),
]
# Nhánh trả lại: Thẩm định → Tự đánh giá; Tổ KPI → Thẩm định; Phê duyệt → Tổ KPI
RETURN_MAP = {
    'negotiating': 'draft', 'submit_assign': 'draft', 'self_review': 'in_progress',
    'appraisal': 'self_review', 'kpi_team': 'appraisal', 'pending_approval': 'kpi_team',
}
EVAL_STAGE_OF_STATE = {'self_review': 'self', 'appraisal': 'reviewer',
                       'kpi_team': 'kpi_team', 'pending_approval': 'final'}


class KpiAssignment(models.Model):
    _name = 'kpi.assignment'
    _description = 'Bảng giao KPI'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'kpi.audit.mixin']
    _order = 'period_id desc, id desc'

    _audit_fields = ('period_id', 'department_id', 'employee_id', 'assignment_version')

    name = fields.Char('Số bảng giao', readonly=True, copy=False, default='Mới')
    period_id = fields.Many2one('kpi.period', 'Kỳ KPI', required=True, tracking=True, index=True)
    object_type = fields.Selection([('company', 'Công ty'), ('department', 'Đơn vị'),
                                    ('employee', 'Cá nhân')], 'Loại đối tượng', required=True,
                                   default='department', tracking=True)
    department_id = fields.Many2one('hr.department', 'Đơn vị', tracking=True, index=True)
    employee_id = fields.Many2one('hr.employee', 'Cá nhân', tracking=True, index=True)
    target_name = fields.Char('Đối tượng', compute='_compute_target_name', store=True)
    assigner_id = fields.Many2one('res.users', 'Người giao KPI', default=lambda s: s.env.user,
                                  readonly=True, copy=False)
    parent_assignment_id = fields.Many2one('kpi.assignment', 'Bảng giao cấp trên', copy=False)
    state = fields.Selection(STATES, 'Trạng thái', default='draft', tracking=True, required=True,
                             copy=False, index=True)
    assignment_version = fields.Integer('Phiên bản bảng giao', default=1, copy=False)
    adjusting = fields.Boolean('Đang điều chỉnh', copy=False)
    company_id = fields.Many2one('res.company', default=lambda s: s.env.company, string='Công ty')

    line_ids = fields.One2many('kpi.assignment.line', 'assignment_id', 'Dòng KPI', copy=False)
    evaluation_ids = fields.One2many('kpi.evaluation', 'assignment_id', 'Đánh giá')
    history_ids = fields.One2many('kpi.approval.history', 'assignment_id', 'Lịch sử phê duyệt')
    event_log_ids = fields.One2many('kpi.event.log', 'assignment_id', 'Nhật ký sự việc')
    weekly_review_ids = fields.One2many('kpi.weekly.review', 'assignment_id', 'Nhận xét tuần')
    audit_log_ids = fields.One2many('kpi.audit.log', 'assignment_id', 'Nhật ký thay đổi')

    total_weight = fields.Float('Tổng trọng số (%)', compute='_compute_totals', store=True)
    weight_ok = fields.Boolean('Đủ 100%', compute='_compute_totals', store=True)
    line_count = fields.Integer(compute='_compute_totals', store=True, string='Số dòng KPI')
    total_system = fields.Float('Tổng điểm hệ thống', compute='_compute_totals', store=True, digits=(16, 2))
    total_self = fields.Float('Tổng điểm tự chấm', compute='_compute_totals', store=True, digits=(16, 2))
    total_reviewer = fields.Float('Tổng điểm thẩm định', compute='_compute_totals', store=True, digits=(16, 2))
    total_team = fields.Float('Tổng điểm Tổ KPI', compute='_compute_totals', store=True, digits=(16, 2))
    total_final = fields.Float('Tổng điểm kết luận', compute='_compute_totals', store=True, digits=(16, 2))

    submitted_at = fields.Datetime('Thời điểm trình giao', readonly=True, copy=False)
    assigned_at = fields.Datetime('Ngày giao', readonly=True, copy=False)
    approved_at = fields.Datetime('Ngày phê duyệt', readonly=True, copy=False)
    locked_at = fields.Datetime('Ngày khóa', readonly=True, copy=False)
    employee_confirmed_at = fields.Datetime('Cá nhân xác nhận lúc', readonly=True, copy=False)
    employee_confirmed_by = fields.Many2one('res.users', 'Cá nhân xác nhận', readonly=True, copy=False)
    manager_confirmed_at = fields.Datetime('Quản lý xác nhận lúc', readonly=True, copy=False)
    manager_confirmed_by = fields.Many2one('res.users', 'Quản lý xác nhận', readonly=True, copy=False)
    change_reason = fields.Text('Lý do điều chỉnh', copy=False)
    conclusion = fields.Text('Ý kiến kết luận', copy=False)
    is_editable = fields.Boolean(compute='_compute_is_editable', string='Được phép chỉnh sửa')

    @api.depends('object_type', 'department_id', 'employee_id')
    def _compute_target_name(self):
        for a in self:
            if a.object_type == 'employee':
                a.target_name = a.employee_id.name or ''
            elif a.object_type == 'department':
                a.target_name = a.department_id.name or ''
            else:
                a.target_name = a.company_id.name or 'Công ty'

    @api.depends('line_ids.weight_pct', 'line_ids.system_weighted', 'line_ids.self_weighted',
                 'line_ids.reviewer_weighted', 'line_ids.team_weighted', 'line_ids.final_weighted',
                 'period_id.total_cap_mode', 'period_id.score_digits', 'period_id.round_at')
    def _compute_totals(self):
        for a in self:
            total = sum(a.line_ids.mapped('weight_pct'))
            a.total_weight = total
            a.weight_ok = float_compare(total, 100.0, precision_digits=4) == 0
            a.line_count = len(a.line_ids)
            digits = a.period_id.score_digits if a.period_id else 2
            cap100 = a.period_id.total_cap_mode == 'cap100'

            def tot(field):
                v = sum(a.line_ids.mapped(field))
                if cap100:
                    v = min(v, 100.0)
                return round(v, digits)
            a.total_system = tot('system_weighted')
            a.total_self = tot('self_weighted')
            a.total_reviewer = tot('reviewer_weighted')
            a.total_team = tot('team_weighted')
            a.total_final = tot('final_weighted')

    @api.depends('state', 'adjusting')
    def _compute_is_editable(self):
        for a in self:
            a.is_editable = a.state in ('draft', 'negotiating')

    def _audit_assignment(self):
        return self

    @api.constrains('object_type', 'department_id', 'employee_id')
    def _check_target(self):
        for a in self:
            if a.object_type == 'department' and not a.department_id:
                raise ValidationError('Chọn đơn vị được giao KPI.')
            if a.object_type == 'employee' and not a.employee_id:
                raise ValidationError('Chọn cá nhân được giao KPI.')

    @api.onchange('employee_id')
    def _onchange_employee(self):
        if self.employee_id and self.object_type == 'employee':
            self.department_id = self.employee_id.department_id

    @api.model_create_multi
    def create(self, vals_list):
        for v in vals_list:
            if not v.get('name') or v.get('name') == 'Mới':
                v['name'] = self.env['ir.sequence'].next_by_code('kpi.assignment') or 'Mới'
        return super().create(vals_list)

    def unlink(self):
        for a in self:
            if a.state != 'draft' or a.assignment_version > 1 or a.history_ids.filtered(
                    lambda h: h.to_state in ('assigned', 'approved')):
                raise UserError('Không xóa bảng giao đã trình/giao/phê duyệt.')
        return super().unlink()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _is_personal(self):
        return self.object_type == 'employee'

    def _unit_users(self):
        self.ensure_one()
        users = self.env['res.users']
        if self.employee_id.user_id:
            users |= self.employee_id.user_id
        if self.department_id.manager_id.user_id:
            users |= self.department_id.manager_id.user_id
        users |= self.line_ids.mapped('responsible_id.user_id')
        return users

    def _manager_user(self):
        self.ensure_one()
        emp = self.employee_id
        return emp.parent_id.user_id or emp.department_id.manager_id.user_id

    def _users_of_group(self, xmlid):
        return self.env.ref(xmlid).users

    def _notify(self, users, summary, note=''):
        self.ensure_one()
        todo = self.env.ref('mail.mail_activity_data_todo')
        for u in users.filtered(lambda u: u.active):
            self.sudo().activity_schedule(
                act_type_xmlid='mail.mail_activity_data_todo', user_id=u.id,
                summary='[KPI] ' + summary, note=note or summary,
                date_deadline=fields.Date.context_today(self))
        if users:
            self.message_subscribe(partner_ids=users.partner_id.ids)

    def _clear_activities(self):
        acts = self.sudo().activity_ids.filtered(lambda a: (a.summary or '').startswith('[KPI]'))
        acts.unlink()

    def _transition(self, new_state, reason=False, action=None):
        for a in self:
            old = a.state
            a.with_context(kpi_internal=True).write({'state': new_state})
            self.env['kpi.approval.history'].create({
                'assignment_id': a.id, 'action': action or 'transition',
                'from_state': old, 'to_state': new_state, 'reason': reason,
            })
            a._clear_activities()
            a.message_post(body='Trạng thái: %s → %s%s' % (
                dict(STATES)[old], dict(STATES)[new_state], ('<br/>Lý do: %s' % reason) if reason else ''))

    def _check_ready(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError('Bảng giao chưa có dòng KPI.')
        if not self.weight_ok:
            raise UserError('Tổng trọng số hiện là %.2f%%, phải bằng 100%% mới được trình giao.' % self.total_weight)
        problems = []
        for l in self.line_ids:
            problems += l._readiness_problems()
        if problems:
            raise UserError('Chưa đủ điều kiện trình giao:\n- ' + '\n- '.join(problems))
        if self.period_id.state not in ('open', 'draft'):
            raise UserError('Kỳ KPI đã đóng/khóa.')

    # ------------------------------------------------------------------
    # Giao KPI
    # ------------------------------------------------------------------
    def action_submit_assign(self):
        for a in self:
            if a._is_personal():
                raise UserError('KPI cá nhân đi qua bước Thảo luận/thống nhất.')
            a._check_ready()
            a.submitted_at = fields.Datetime.now()
            a._transition('submit_assign', action='submit')
            leaders = a._users_of_group('z755_kpi.group_kpi_assigner') | a._users_of_group('z755_kpi.group_kpi_leader')
            a._notify(leaders, 'Kiểm tra/phê duyệt giao KPI %s' % a.name)

    def action_approve_assign(self):
        for a in self:
            if a.state != 'submit_assign':
                raise UserError('Bảng giao chưa ở trạng thái Trình giao.')
            a._check_ready()
            a._do_assign()

    def action_start_negotiation(self):
        for a in self:
            if not a._is_personal():
                raise UserError('Chỉ dùng cho KPI cá nhân.')
            if not a.line_ids:
                raise UserError('Quản lý cần phân bổ ít nhất một KPI trước khi chuyển cá nhân.')
            a.submitted_at = fields.Datetime.now()
            a._transition('negotiating', action='submit')
            a._notify(a.employee_id.user_id, 'Bổ sung/đề xuất KPI cá nhân kỳ %s' % a.period_id.name)

    def action_employee_confirm(self):
        for a in self:
            if a.state != 'negotiating':
                raise UserError('Chỉ xác nhận trong giai đoạn thảo luận.')
            u = self.env.user
            if u != a.employee_id.user_id and not u.has_group('z755_kpi.group_kpi_leader'):
                raise UserError('Chỉ cá nhân được giao mới xác nhận phần của mình.')
            a.write({'employee_confirmed_at': fields.Datetime.now(), 'employee_confirmed_by': u.id})
            a.message_post(body='Cá nhân xác nhận bản KPI.')
            a._try_finish_negotiation()

    def action_manager_confirm(self):
        for a in self:
            if a.state != 'negotiating':
                raise UserError('Chỉ xác nhận trong giai đoạn thảo luận.')
            u = self.env.user
            if not (u == a._manager_user() or u.has_group('z755_kpi.group_kpi_unit_manager')
                    or u.has_group('z755_kpi.group_kpi_leader')):
                raise UserError('Chỉ quản lý trực tiếp/chỉ huy đơn vị mới xác nhận.')
            a.write({'manager_confirmed_at': fields.Datetime.now(), 'manager_confirmed_by': u.id})
            a.message_post(body='Quản lý xác nhận bản KPI.')
            a._try_finish_negotiation()

    def _try_finish_negotiation(self):
        self.ensure_one()
        if self.employee_confirmed_at and self.manager_confirmed_at:
            self._check_ready()
            self._do_assign()

    def action_reset_confirmation(self):
        """Hai bên chưa thống nhất: xóa xác nhận để tiếp tục thảo luận."""
        self.write({'employee_confirmed_at': False, 'employee_confirmed_by': False,
                    'manager_confirmed_at': False, 'manager_confirmed_by': False})

    def _do_assign(self):
        self.ensure_one()
        self.line_ids._take_snapshot()
        self.line_ids.write({'is_locked': True})
        self.write({'assigned_at': fields.Datetime.now(), 'adjusting': False})
        self._transition('assigned', action='assign')
        self._notify(self._unit_users(), 'KPI đã được giao: %s' % self.name)

    def action_start(self):
        for a in self:
            if a.state != 'assigned':
                raise UserError('Bảng giao chưa được giao.')
            a._transition('in_progress', action='start')

    # ------------------------------------------------------------------
    # Đánh giá
    # ------------------------------------------------------------------
    def _generate_evaluations(self, stage):
        Eval = self.env['kpi.evaluation'].with_context(kpi_internal=True)
        for a in self:
            for line in a.line_ids:
                if stage == 'self':
                    users = [self.env.user.id]
                    prefill = line.system_score
                elif stage == 'reviewer':
                    users = line.reviewer_ids.ids
                    if a._is_personal() and a._manager_user():
                        users = [a._manager_user().id]
                    users = users or [False]
                    prefill = line.self_score
                elif stage == 'kpi_team':
                    users = [False]
                    prefill = line.reviewer_score if line.reviewer_score is not False else line.self_score
                else:
                    users = [False]
                    prefill = line.team_score if line.team_score is not False else line.reviewer_score
                for uid in users:
                    exists = line.evaluation_ids.filtered(lambda e: e.stage == stage and (e.user_id.id or False) == uid)
                    if not exists:
                        Eval.create({
                            'line_id': line.id, 'stage': stage, 'user_id': uid,
                            'score_pct': prefill or 0.0, 'system_score': line.system_score,
                            'actual_value': line.actual_value,
                        })

    def action_open_self_review(self):
        for a in self:
            if a.state != 'in_progress':
                raise UserError('Bảng KPI chưa ở trạng thái Đang thực hiện.')
            a._transition('self_review', action='open_self')
            a._generate_evaluations('self')
            a._notify(a._unit_users(), 'Nhập tự đánh giá KPI %s' % a.name)

    def _require_stage_done(self, stage):
        self.ensure_one()
        evs = self.evaluation_ids.filtered(lambda e: e.stage == stage)
        missing = self.line_ids.filtered(lambda l: not evs.filtered(lambda e: e.line_id == l and e.submitted))
        if missing:
            raise UserError('Còn dòng chưa được chấm/xác nhận ở bước này:\n- ' +
                            '\n- '.join(missing.mapped('kpi_name')))

    def action_submit_self(self):
        for a in self:
            if a.state != 'self_review':
                raise UserError('Chưa ở bước Tự đánh giá.')
            a.evaluation_ids.filtered(lambda e: e.stage == 'self' and not e.submitted).write({'submitted': True})
            a._require_stage_done('self')
            a._transition('appraisal', action='submit_self')
            a._generate_evaluations('reviewer')
            reviewers = a.line_ids.mapped('reviewer_ids')
            if a._is_personal() and a._manager_user():
                reviewers = a._manager_user()
            a._notify(reviewers, 'Thẩm định KPI %s' % a.name)

    def action_complete_appraisal(self):
        for a in self:
            if a.state != 'appraisal':
                raise UserError('Chưa ở bước Thẩm định.')
            mine = a.evaluation_ids.filtered(lambda e: e.stage == 'reviewer' and e.user_id == self.env.user)
            mine.write({'submitted': True})
            evs = a.evaluation_ids.filtered(lambda e: e.stage == 'reviewer')
            pending = evs.filtered(lambda e: not e.submitted)
            if pending:
                raise UserError('Còn %d phiếu thẩm định chưa hoàn tất (người thẩm định: %s).' % (
                    len(pending), ', '.join(pending.mapped('user_id.name') or ['chưa phân công'])))
            a._require_stage_done('reviewer')
            personal = a._is_personal()
            if personal and not a.period_id.personal_use_kpi_team:
                if a.period_id.personal_use_approval:
                    a._go_pending_approval()
                else:
                    a._approve_now()
                continue
            a._transition('kpi_team', action='complete_appraisal')
            a._generate_evaluations('kpi_team')
            a._notify(a._users_of_group('z755_kpi.group_kpi_member') | a._users_of_group('z755_kpi.group_kpi_leader'),
                      'Rà soát/đề xuất KPI %s' % a.name)

    def _go_pending_approval(self):
        self._transition('pending_approval', action='submit_approval')
        self._generate_evaluations('final')
        approvers = self.line_ids.mapped('approver_ids') or self._users_of_group('z755_kpi.group_kpi_approver')
        self._notify(approvers, 'Phê duyệt KPI %s' % self.name)

    def action_submit_approval(self):
        for a in self:
            if a.state != 'kpi_team':
                raise UserError('Chưa ở bước Tổ KPI đề xuất.')
            a.evaluation_ids.filtered(lambda e: e.stage == 'kpi_team' and not e.submitted).write({'submitted': True})
            a._require_stage_done('kpi_team')
            a._go_pending_approval()

    def _approve_now(self):
        self.ensure_one()
        self.write({'approved_at': fields.Datetime.now()})
        self._transition('approved', action='approve')
        self._notify(self._unit_users(), 'KPI %s đã được phê duyệt' % self.name)

    def action_approve(self):
        for a in self:
            if a.state != 'pending_approval':
                raise UserError('Chưa ở bước Chờ phê duyệt.')
            if not (self.env.user.has_group('z755_kpi.group_kpi_approver') or
                    self.env.user.has_group('z755_kpi.group_kpi_leader')):
                raise UserError('Bạn không có thẩm quyền phê duyệt.')
            a.evaluation_ids.filtered(lambda e: e.stage == 'final' and not e.submitted).write({'submitted': True})
            a._require_stage_done('final')
            a._approve_now()

    def action_lock(self):
        for a in self:
            if a.state != 'approved':
                raise UserError('Chỉ khóa bảng KPI đã phê duyệt.')
            a.locked_at = fields.Datetime.now()
            a._transition('locked', action='lock')
            a._notify(a._unit_users(), 'Kỳ %s đã khóa - hồ sơ chỉ đọc' % a.period_id.name)

    # ------------------------------------------------------------------
    # Trả lại / điều chỉnh / mở lại (có lý do)
    # ------------------------------------------------------------------
    def _return_target(self):
        self.ensure_one()
        target = RETURN_MAP.get(self.state)
        if self.state == 'pending_approval' and self._is_personal() and not self.period_id.personal_use_kpi_team:
            target = 'appraisal'
        return target

    def _do_return(self, reason):
        for a in self:
            target = a._return_target()
            if not target:
                raise UserError('Không thể trả lại từ trạng thái "%s".' % dict(STATES)[a.state])
            frm = a.state
            a.evaluation_ids.filtered(lambda e: e.stage == EVAL_STAGE_OF_STATE.get(frm) or (
                target != 'draft' and e.stage == EVAL_STAGE_OF_STATE.get(target))).write({'submitted': False})
            a._transition(target, reason=reason, action='return')
            if target == 'draft':
                a.write({'employee_confirmed_at': False, 'manager_confirmed_at': False})
            users = {
                'draft': a._unit_users(), 'in_progress': a._unit_users(), 'self_review': a._unit_users(),
                'appraisal': a.line_ids.mapped('reviewer_ids') | (a._manager_user() or self.env['res.users']),
                'kpi_team': a._users_of_group('z755_kpi.group_kpi_member') | a._users_of_group('z755_kpi.group_kpi_leader'),
            }.get(target, self.env['res.users'])
            a._notify(users, 'Hồ sơ %s bị trả lại: %s' % (a.name, reason))

    def _do_adjust(self, reason):
        """Điều chỉnh bảng giao: phiên bản +1, mở khóa dòng, phải trình/phê duyệt lại."""
        for a in self:
            if a.state not in ('assigned', 'in_progress'):
                raise UserError('Chỉ điều chỉnh khi bảng đã giao/đang thực hiện (trước khi tự đánh giá).')
            a.line_ids.write({'is_locked': False})
            a.with_context(kpi_internal=True).write({
                'assignment_version': a.assignment_version + 1, 'adjusting': True, 'change_reason': reason})
            a._transition('draft', reason=reason, action='adjust')

    def _do_reopen(self, reason):
        """Mở lại hồ sơ đã khóa/phê duyệt qua quy trình có lý do."""
        for a in self:
            if a.state not in ('approved', 'locked'):
                raise UserError('Chỉ mở lại hồ sơ đã phê duyệt/khóa.')
            a.with_context(kpi_internal=True).write({
                'assignment_version': a.assignment_version + 1, 'change_reason': reason})
            a.evaluation_ids.filtered(lambda e: e.stage == 'final').write({'submitted': False})
            a._transition('pending_approval', reason=reason, action='reopen')

    def _open_reason_wizard(self, kind):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': 'Nhập lý do', 'res_model': 'kpi.reason.wizard',
            'view_mode': 'form', 'target': 'new',
            'context': {'default_assignment_id': self.id, 'default_kind': kind},
        }

    def action_return(self):
        return self._open_reason_wizard('return')

    def action_adjust(self):
        return self._open_reason_wizard('adjust')

    def action_reopen(self):
        return self._open_reason_wizard('reopen')

    # ------------------------------------------------------------------
    # Sao chép, xem
    # ------------------------------------------------------------------
    def copy_to_period(self, period):
        self.ensure_one()
        new = self.copy({'period_id': period.id, 'state': 'draft', 'assignment_version': 1})
        for l in self.line_ids:
            vals = {'assignment_id': new.id}
            if l.inline_rule_id:
                vals['inline_rule_id'] = l.inline_rule_id.copy({'is_inline': True, 'code': 'Mới'}).id
            l.copy(vals)
        return new

    def action_copy_previous(self):
        """Sao chép dòng từ bảng giao gần nhất cùng đối tượng ở kỳ trước."""
        self.ensure_one()
        domain = [('id', '!=', self.id), ('object_type', '=', self.object_type),
                  ('department_id', '=', self.department_id.id), ('employee_id', '=', self.employee_id.id)]
        prev = self.search(domain, order='period_id desc, id desc', limit=1)
        if not prev:
            raise UserError('Không có bảng giao kỳ trước cùng đối tượng.')
        for l in prev.line_ids:
            vals = {'assignment_id': self.id}
            if l.inline_rule_id:
                vals['inline_rule_id'] = l.inline_rule_id.copy({'is_inline': True, 'code': 'Mới'}).id
            l.copy(vals)

    def action_check_data(self):
        self.ensure_one()
        problems = []
        if not self.weight_ok:
            problems.append('Tổng trọng số %.2f%% (phải = 100%%).' % self.total_weight)
        for l in self.line_ids:
            problems += l._readiness_problems()
        if problems:
            raise UserError('Cần bổ sung:\n- ' + '\n- '.join(problems))
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'title': 'Kiểm tra dữ liệu', 'message': 'Đủ điều kiện trình giao.',
                           'type': 'success', 'sticky': False}}

    def action_print_assign(self):
        return self.env.ref('z755_kpi.action_report_assignment').report_action(self)

    def action_print_evaluation(self):
        return self.env.ref('z755_kpi.action_report_evaluation').report_action(self)


class KpiApprovalHistory(models.Model):
    _name = 'kpi.approval.history'
    _description = 'Lịch sử phê duyệt KPI'
    _order = 'id desc'

    assignment_id = fields.Many2one('kpi.assignment', required=True, ondelete='restrict', index=True, string='Bảng giao')
    action = fields.Selection([
        ('transition', 'Chuyển bước'), ('submit', 'Trình'), ('assign', 'Giao'), ('start', 'Bắt đầu'),
        ('open_self', 'Mở tự đánh giá'), ('submit_self', 'Gửi thẩm định'),
        ('complete_appraisal', 'Hoàn tất thẩm định'), ('submit_approval', 'Trình phê duyệt'),
        ('approve', 'Phê duyệt'), ('lock', 'Khóa'), ('return', 'Trả lại'),
        ('adjust', 'Điều chỉnh'), ('reopen', 'Mở lại')], 'Hành động')
    from_state = fields.Selection(STATES, 'Từ trạng thái')
    to_state = fields.Selection(STATES, 'Sang trạng thái')
    user_id = fields.Many2one('res.users', 'Người thực hiện', default=lambda s: s.env.user, readonly=True)
    date = fields.Datetime('Thời gian', default=fields.Datetime.now, readonly=True)
    reason = fields.Text('Lý do')

    def write(self, vals):
        raise UserError('Không được sửa lịch sử phê duyệt.')

    def unlink(self):
        raise UserError('Không được xóa lịch sử phê duyệt.')
