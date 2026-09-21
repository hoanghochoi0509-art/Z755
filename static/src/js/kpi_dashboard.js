/** @odoo-module **/
import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class KpiDashboard extends Component {
    static template = "z755_kpi.Dashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ data: { tiles: [], units: [], todo: [] } });
        onWillStart(async () => {
            this.state.data = await this.orm.call("kpi.assignment", "get_dashboard_data", []);
        });
    }

    open(xmlid) {
        this.action.doAction(xmlid);
    }

    todoClick(t) {
        const map = {
            appraisal: "z755_kpi.action_kpi_appraisal",
            diff: "z755_kpi.action_kpi_report_diff",
            weekly: "z755_kpi.action_kpi_weekly",
        };
        this.open(map[t.action]);
    }
}
registry.category("actions").add("z755_kpi.dashboard", KpiDashboard);

export class KpiMy extends Component {
    static template = "z755_kpi.My";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ data: { tiles: [], lines: [] } });
        onWillStart(async () => {
            this.state.data = await this.orm.call("kpi.assignment", "get_my_kpi_data", []);
        });
    }

    updateLine(line) {
        this.action.doAction({
            type: "ir.actions.act_window", res_model: "kpi.assignment.line", res_id: line.id,
            views: [[false, "form"]], target: "current",
        });
    }

    openAssignment() {
        if (this.state.data.assignment_id) {
            this.action.doAction({
                type: "ir.actions.act_window", res_model: "kpi.assignment",
                res_id: this.state.data.assignment_id, views: [[false, "form"]], target: "current",
            });
        }
    }
}
registry.category("actions").add("z755_kpi.my_kpi", KpiMy);
