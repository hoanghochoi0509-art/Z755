/** @odoo-module **/
import { Component, useState, onMounted, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { router } from "@web/core/browser/router";
import { user } from "@web/core/user";

const ROOT_XMLID = "z755_kpi.menu_kpi_root";

export class KpiSidebar extends Component {
    static template = "z755_kpi.Sidebar";
    static props = {};

    setup() {
        this.menus = useService("menu");
        this.state = useState({ visible: false, tick: 0 });
        this.user = user;
        const update = () => {
            const app = this.menus.getCurrentApp();
            this.state.visible = !!app && app.xmlid === ROOT_XMLID;
            document.body.classList.toggle("z755_kpi", this.state.visible);
            this.state.tick++;
        };
        this.update = update;
        onMounted(() => {
            update();
            this.env.bus.addEventListener("MENUS:APP-CHANGED", update);
            this.env.bus.addEventListener("ROUTE_CHANGE", update);
            this.env.bus.addEventListener("ACTION_MANAGER:UI-UPDATED", update);
        });
        onWillUnmount(() => {
            this.env.bus.removeEventListener("MENUS:APP-CHANGED", update);
            this.env.bus.removeEventListener("ROUTE_CHANGE", update);
            this.env.bus.removeEventListener("ACTION_MANAGER:UI-UPDATED", update);
            document.body.classList.remove("z755_kpi");
        });
    }

    get items() {
        void this.state.tick; // đọc tick để render lại khi đổi route/menu
        const app = this.menus.getCurrentApp();
        if (!app) {
            return [];
        }
        const tree = this.menus.getMenuAsTree(app.id);
        const current = router.current.action;
        return (tree.childrenTree || []).map((m) => {
            const kids = (m.childrenTree || []).map((c) => ({
                id: c.id, name: c.name, active: this._isActive(c, current), menu: c,
            }));
            const active = this._isActive(m, current) || kids.some((k) => k.active);
            return { id: m.id, name: m.name, active, kids, menu: m };
        });
    }

    _isActive(menu, current) {
        if (!current || !menu.actionID) {
            return false;
        }
        return String(menu.actionID) === String(current);
    }

    onClick(item) {
        const target = item.kids && item.kids.length ? item.kids[0].menu : item.menu;
        this.menus.selectMenu(target);
    }

    get initials() {
        const n = (this.user.name || "QT").split(" ");
        return (n[n.length - 1][0] + (n[0][0] || "")).toUpperCase().slice(0, 2);
    }
}

registry.category("main_components").add("z755_kpi_sidebar", { Component: KpiSidebar });
