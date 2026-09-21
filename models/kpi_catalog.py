from odoo import api, fields, models
from odoo.exceptions import UserError

KPI_STATES = [('proposed', 'Đề xuất'), ('confirmed', 'Đã xác nhận'), ('retired', 'Ngừng dùng')]


class KpiCatalog(models.Model):
    _name = 'kpi.catalog'
    _description = 'Danh mục KPI động'
    _inherit = ['mail.thread', 'kpi.audit.mixin']
    _order = 'code'

    _audit_fields = ('name', 'kpi_type', 'value_type', 'uom_id', 'state')

    code = fields.Char('Mã KPI', copy=False, readonly=True, default='Mới', tracking=True)
    name = fields.Char('Tên KPI', required=True, tracking=True)
    group_id = fields.Many2one('kpi.group', 'Nhóm/BSC')
    field_id = fields.Many2one('kpi.field', 'Lĩnh vực')
    kpi_type = fields.Selection([('quantitative', 'Định lượng'), ('qualitative', 'Định tính'),
                                 ('compliance', 'Tuân thủ')], 'Loại KPI', required=True,
                                default='quantitative')
    uom_id = fields.Many2one('kpi.uom', 'Đơn vị tính mặc định')
    value_type = fields.Selection([
        ('percentage', 'Phần trăm'), ('count', 'Số lượng'), ('currency', 'Tiền tệ'), ('date', 'Ngày'),
        ('duration', 'Thời lượng'), ('boolean', 'Có/Không'), ('milestone', 'Mốc'), ('text', 'Văn bản/Thủ công'),
    ], 'Kiểu giá trị mục tiêu', required=True, default='percentage')
    description = fields.Text('Mô tả/cách hiểu')
    state = fields.Selection(KPI_STATES, 'Trạng thái', default='proposed', required=True, tracking=True)
    line_ids = fields.One2many('kpi.assignment.line', 'kpi_id', 'Dòng KPI')
    usage_count = fields.Integer('Số lần sử dụng', compute='_compute_usage')
    similar_hint = fields.Char(compute='_compute_similar_hint', string='Gợi ý KPI tương tự')

    _sql_constraints = [('code_uniq', 'unique(code)', 'Mã KPI phải duy nhất.')]

    @api.depends('line_ids')
    def _compute_usage(self):
        data = self.env['kpi.assignment.line']._read_group(
            [('kpi_id', 'in', self.ids)], ['kpi_id'], ['__count'])
        counts = {k.id: c for k, c in data}
        for r in self:
            r.usage_count = counts.get(r.id, 0)

    @api.depends('name', 'field_id')
    def _compute_similar_hint(self):
        for r in self:
            hint = False
            if r.name and isinstance(r.id, int):
                dup = self.search([('id', '!=', r.id), ('name', 'ilike', r.name)], limit=3)
                if dup:
                    hint = 'KPI gần giống: ' + '; '.join('[%s] %s' % (d.code, d.name) for d in dup)
            r.similar_hint = hint

    @api.model_create_multi
    def create(self, vals_list):
        for v in vals_list:
            if not v.get('code') or v.get('code') == 'Mới':
                v['code'] = self.env['ir.sequence'].next_by_code('kpi.catalog') or 'Mới'
        return super().create(vals_list)

    @api.onchange('name', 'field_id')
    def _onchange_similar(self):
        if self.name and len(self.name) > 3:
            dup = self.search([('name', 'ilike', self.name)], limit=3)
            if dup:
                return {'warning': {'title': 'Có thể trùng KPI đã có',
                                    'message': '\n'.join('[%s] %s (%s)' % (
                                        d.code, d.name, dict(KPI_STATES)[d.state]) for d in dup)}}

    def action_confirm(self):
        self.write({'state': 'confirmed'})

    def action_retire(self):
        self.write({'state': 'retired'})

    def action_propose(self):
        self.write({'state': 'proposed'})

    def unlink(self):
        for r in self:
            if r.line_ids:
                raise UserError('KPI "%s" đã xuất hiện trong bảng giao, không được xóa; hãy chuyển sang Ngừng dùng.' % r.name)
        return super().unlink()
