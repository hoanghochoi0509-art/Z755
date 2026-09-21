from odoo import api, SUPERUSER_ID


def post_init_hook(env):
    """Gắn admin vào nhóm quản trị KPI để kiểm thử UAT (chỉ khi cài mới)."""
    admin = env.ref('base.user_admin', raise_if_not_found=False)
    grp = env.ref('z755_kpi.group_kpi_leader', raise_if_not_found=False)
    if admin and grp:
        admin.write({'groups_id': [(4, grp.id)]})
    # Giao diện toàn tiếng Việt: kích hoạt vi_VN và đặt cho người dùng nội bộ
    lang = env['res.lang'].with_context(active_test=False).search([('code', '=', 'vi_VN')], limit=1)
    if lang:
        if not lang.active:
            lang.active = True
        env['res.users'].search([('share', '=', False)]).write({'lang': 'vi_VN'})
