from datetime import timedelta

from odoo import api, fields, models


class KpiAssignmentDashboard(models.Model):
    _inherit = 'kpi.assignment'

    @api.model
    def _dash_period(self):
        Period = self.env['kpi.period']
        return Period.search([('state', '=', 'open')], order='date_start desc', limit=1) or \
            Period.search([], order='date_start desc', limit=1)

    @api.model
    def get_dashboard_data(self):
        period = self._dash_period()
        res = {'period': period.name or '', 'period_state': dict(
            period._fields['state'].selection).get(period.state, '') if period else '',
            'tiles': [], 'units': [], 'todo': [], 'user': self.env.user.name}
        if not period:
            return res
        As = self.search([('period_id', '=', period.id)])
        total = len(As)
        done_assign = As.filtered(lambda a: a.state not in ('draft', 'negotiating', 'submit_assign'))
        self_done = As.filtered(lambda a: a.state in ('appraisal', 'kpi_team', 'pending_approval', 'approved', 'locked'))
        appraisal = As.filtered(lambda a: a.state == 'appraisal')
        approved = As.filtered(lambda a: a.state in ('approved', 'locked'))
        now = fields.Datetime.now()
        late = appraisal if (period.deadline_appraisal and period.deadline_appraisal < now) else As.browse()
        pct = lambda n: int(round(n * 100.0 / total)) if total else 0
        res['tiles'] = [
            {'label': 'Bảng KPI đã giao', 'value': '%d/%d' % (len(done_assign), total),
             'sub': '%d%% đơn vị' % pct(len(done_assign)), 'color': 'plum'},
            {'label': 'Đã tự đánh giá', 'value': str(len(self_done)),
             'sub': '%d%% hồ sơ' % pct(len(self_done)), 'color': 'blue'},
            {'label': 'Đang thẩm định', 'value': str(len(appraisal)),
             'sub': '%d hồ sơ quá hạn' % len(late), 'color': 'orange'},
            {'label': 'Đã phê duyệt', 'value': str(len(approved)),
             'sub': '%d%% hồ sơ' % pct(len(approved)), 'color': 'green'},
        ]
        for a in As.sorted('total_system', reverse=True):
            v = min(a.total_system, 100.0)
            res['units'].append({
                'id': a.id, 'name': a.target_name, 'value': int(round(v)),
                'color': 'green' if v >= 85 else 'blue' if v >= 80 else 'orange' if v >= 60 else 'red'})
        diff = self.env['kpi.assignment.line'].search_count([
            ('period_id', '=', period.id), ('self_score', '!=', 0), ('reviewer_score', '!=', 0),
            ('diff_flag', '=', True)])
        week_ago = fields.Date.today() - timedelta(days=7)
        running = As.filtered(lambda a: a.state in ('in_progress', 'self_review'))
        recent = self.env['kpi.weekly.review'].search([('period_id', '=', period.id), ('date_to', '>=', week_ago)])
        no_weekly = running.filtered(lambda a: a not in recent.mapped('assignment_id'))
        res['todo'] = [
            {'n': len(late), 'label': 'Hồ sơ chậm thẩm định', 'color': 'orange', 'action': 'appraisal'},
            {'n': diff, 'label': 'KPI có chênh lệch >10 điểm', 'color': 'red', 'action': 'diff'},
            {'n': len(no_weekly), 'label': 'Đơn vị chưa cập nhật tuần', 'color': 'blue', 'action': 'weekly'},
        ]
        return res

    @api.model
    def get_my_kpi_data(self):
        period = self._dash_period()
        me = self.env.user
        a = self.search([('period_id', '=', period.id), ('employee_id.user_id', '=', me.id)], limit=1) if period else self
        if not a:
            a = self.search([('period_id', '=', period.id), ('object_type', '=', 'department'),
                             ('department_id.member_ids.user_id', '=', me.id)], limit=1) if period else self
        res = {'period': period.name or '', 'assignment_id': a.id if a else False,
               'subtitle': a.target_name if a else '', 'state': dict(self._fields['state'].selection).get(a.state, '') if a else '',
               'tiles': [], 'lines': []}
        if not a:
            return res
        lines = a.line_ids
        ontrack = lines.filtered(lambda l: not l.overdue and (l.progress_pct >= 80 or l.actual_entered))
        attention = lines - ontrack
        n = len(lines)
        res['tiles'] = [
            {'label': 'Tổng KPI', 'value': str(n), 'sub': 'Trọng số %d%%' % round(a.total_weight), 'color': 'plum'},
            {'label': 'Đúng tiến độ', 'value': str(len(ontrack)),
             'sub': '%d%% KPI' % (round(len(ontrack) * 100.0 / n) if n else 0), 'color': 'green'},
            {'label': 'Cần chú ý', 'value': str(len(attention)),
             'sub': (attention[:1].kpi_name or '')[:28], 'color': 'orange'},
            {'label': 'Minh chứng', 'value': str(sum(lines.mapped('evidence_count'))), 'sub': 'Đã tải lên', 'color': 'blue'},
        ]
        for l in lines:
            p = l.progress_pct or (min(l.achievement_rate, 100) if l.actual_entered else 0)
            res['lines'].append({
                'id': l.id, 'name': l.kpi_name, 'progress': int(round(p)),
                'target': '%s %s%s' % (l.target_operator or '', ('%g' % l.target_value), (' ' + l.uom_id.name) if l.uom_id else ''),
                'weight': '%g%%' % l.weight_pct, 'due': l.due_date.strftime('%d/%m') if l.due_date else '-',
                'color': 'green' if p >= 90 else 'blue' if p >= 75 else 'orange'})
        return res
