from datetime import date, timedelta
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models


class AlquilerDashboard(models.Model):
    _name = 'alquiler.dashboard'
    _description = 'Dashboard de Alquiler de Equipos'

    name = fields.Char(default='Dashboard')

    total_customers = fields.Integer(compute='_compute_kpis')
    active_customers = fields.Integer(compute='_compute_kpis')
    total_monthly_revenue = fields.Monetary(compute='_compute_kpis',
                                            currency_field='currency_id')
    total_active_mandates = fields.Integer(compute='_compute_kpis')
    invoices_this_month = fields.Integer(compute='_compute_kpis')
    invoices_this_month_amount = fields.Monetary(compute='_compute_kpis',
                                                 currency_field='currency_id')
    pending_invoices = fields.Integer(compute='_compute_kpis')
    pending_invoices_amount = fields.Monetary(compute='_compute_kpis',
                                              currency_field='currency_id')
    remesas_this_month = fields.Integer(compute='_compute_kpis')
    returned_invoices = fields.Integer(compute='_compute_kpis')
    returned_invoices_amount = fields.Monetary(compute='_compute_kpis',
                                               currency_field='currency_id')
    morosidad_rate = fields.Float(compute='_compute_kpis',
                                  string='Tasa de Morosidad (%)')

    currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.company.currency_id,
    )

    def _compute_kpis(self):
        Partner = self.env['res.partner']
        Mandate = self.env['sepa.mandate']
        Move = self.env['account.move']
        Line = self.env['sepa.remittance.line']
        Rem = self.env['sepa.remittance']

        today = fields.Date.today()
        month_start = today.replace(day=1)
        next_month_start = month_start + relativedelta(months=1)

        for rec in self:
            rec.total_customers = Partner.search_count(
                [('is_rental_customer', '=', True)])
            rec.active_customers = Partner.search_count([
                ('is_rental_customer', '=', True),
                ('rental_active', '=', True),
            ])

            active_partners = Partner.search([
                ('is_rental_customer', '=', True),
                ('rental_active', '=', True),
            ])
            rec.total_monthly_revenue = sum(
                p.rental_monthly_amount for p in active_partners)

            rec.total_active_mandates = Mandate.search_count(
                [('state', '=', 'active')])

            month_invoices = Move.search([
                ('move_type', '=', 'out_invoice'),
                ('recurring_invoice_id', '!=', False),
                ('invoice_date', '>=', month_start),
                ('invoice_date', '<', next_month_start),
            ])
            rec.invoices_this_month = len(month_invoices)
            rec.invoices_this_month_amount = sum(
                m.amount_total for m in month_invoices)

            pending = Move.search([
                ('move_type', '=', 'out_invoice'),
                ('recurring_invoice_id', '!=', False),
                ('payment_state', 'in', ('not_paid', 'partial')),
                ('state', '=', 'posted'),
            ])
            rec.pending_invoices = len(pending)
            rec.pending_invoices_amount = sum(
                m.amount_residual for m in pending)

            rec.remesas_this_month = Rem.search_count([
                ('date', '>=', month_start),
                ('date', '<', next_month_start),
            ])

            returned = Line.search([('state', '=', 'returned')])
            rec.returned_invoices = len(returned)
            rec.returned_invoices_amount = sum(l.amount for l in returned)

            total_lines = Line.search_count([])
            if total_lines > 0:
                rec.morosidad_rate = (len(returned) / total_lines) * 100.0
            else:
                rec.morosidad_rate = 0.0

    @api.model
    def action_open_dashboard(self):
        dashboard = self.search([], limit=1)
        if not dashboard:
            dashboard = self.create({'name': 'Dashboard'})
        return {
            'type': 'ir.actions.act_window',
            'name': 'Panel de Control',
            'res_model': 'alquiler.dashboard',
            'res_id': dashboard.id,
            'view_mode': 'form',
            'target': 'current',
            'context': {'form_view_initial_mode': 'readonly'},
        }

    def action_view_customers(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Clientes de Alquiler',
            'res_model': 'res.partner',
            'view_mode': 'kanban,list,form',
            'domain': [('is_rental_customer', '=', True)],
        }

    def action_view_active_mandates(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Mandatos Activos',
            'res_model': 'sepa.mandate',
            'view_mode': 'kanban,list,form',
            'domain': [('state', '=', 'active')],
        }

    def action_view_invoices_this_month(self):
        today = fields.Date.today()
        month_start = today.replace(day=1)
        next_month_start = month_start + relativedelta(months=1)
        return {
            'type': 'ir.actions.act_window',
            'name': 'Facturas del Mes',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [
                ('move_type', '=', 'out_invoice'),
                ('recurring_invoice_id', '!=', False),
                ('invoice_date', '>=', month_start),
                ('invoice_date', '<', next_month_start),
            ],
        }

    def action_view_pending_invoices(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Facturas Pendientes',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [
                ('move_type', '=', 'out_invoice'),
                ('recurring_invoice_id', '!=', False),
                ('payment_state', 'in', ('not_paid', 'partial')),
                ('state', '=', 'posted'),
            ],
        }

    def action_view_remesas(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Remesas SEPA',
            'res_model': 'sepa.remittance',
            'view_mode': 'kanban,list,form',
        }

    def action_view_returns(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Devoluciones',
            'res_model': 'sepa.remittance.line',
            'view_mode': 'list,form',
            'domain': [('state', '=', 'returned')],
        }
