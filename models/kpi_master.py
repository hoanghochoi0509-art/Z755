from odoo import fields, models


class KpiUom(models.Model):
    _name = 'kpi.uom'
    _description = 'Đơn vị tính KPI'
    _order = 'name'

    name = fields.Char('Đơn vị tính', required=True, translate=True)
    active = fields.Boolean(default=True, string='Đang sử dụng')
    _sql_constraints = [('name_uniq', 'unique(name)', 'Đơn vị tính đã tồn tại.')]


class KpiGroup(models.Model):
    _name = 'kpi.group'
    _description = 'Nhóm KPI / BSC'
    _order = 'name'

    name = fields.Char('Nhóm/BSC', required=True)
    code = fields.Char('Mã')
    active = fields.Boolean(default=True, string='Đang sử dụng')


class KpiField(models.Model):
    _name = 'kpi.field'
    _description = 'Lĩnh vực nghiệp vụ KPI'
    _order = 'name'

    name = fields.Char('Lĩnh vực', required=True)
    code = fields.Char('Mã')
    active = fields.Boolean(default=True, string='Đang sử dụng')


class KpiDataSource(models.Model):
    _name = 'kpi.data.source'
    _description = 'Nguồn dữ liệu KPI'
    _order = 'name'

    name = fields.Char('Nguồn dữ liệu', required=True)
    source_type = fields.Selection([
        ('system', 'Hệ thống'), ('odoo', 'Odoo/Hỗ trợ'),
        ('document', 'Văn bản'), ('other', 'Khác')], 'Loại nguồn', default='other', required=True)
    owner_department_id = fields.Many2one('hr.department', 'Đơn vị sở hữu')
    collection_method = fields.Selection([
        ('auto', 'Tự động/API'), ('link', 'Liên kết record'),
        ('upload', 'Tải lên/liên kết'), ('manual', 'Nhập thủ công')], 'Phương thức thu thập', default='manual')
    cutoff_note = fields.Char('Thời điểm chốt', help='Ví dụ: Theo cấu hình kỳ, cuối kỳ, theo mốc.')
    required_evidence = fields.Char('Minh chứng bắt buộc')
    active = fields.Boolean(default=True, string='Đang sử dụng')
