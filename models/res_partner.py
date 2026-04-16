from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # --- Rental fields ---
    is_rental_customer = fields.Boolean(
        string='Cliente de Alquiler',
        default=False,
        help='Indica si el cliente tiene equipos en alquiler',
    )
    rental_monthly_amount = fields.Monetary(
        string='Importe Mensual de Alquiler',
        currency_field='currency_id',
        help='Importe fijo mensual a facturar por alquiler de equipos',
    )
    rental_concept = fields.Char(
        string='Concepto de Factura',
        help='Descripción que aparecerá en la línea de factura recurrente',
        default='Alquiler mensual de equipos',
    )
    rental_day_of_month = fields.Integer(
        string='Día de Cargo',
        default=1,
        help='Día del mes en que se genera la factura (1-28)',
    )
    rental_collection_day = fields.Integer(
        string='Día de Cobro SEPA',
        default=5,
        help='Día del mes en que el banco debe ejecutar el cobro para este cliente',
    )
    rental_start_date = fields.Date(
        string='Fecha Inicio Alquiler',
    )
    rental_end_date = fields.Date(
        string='Fecha Fin Alquiler',
        help='Dejar vacío si el alquiler es indefinido',
    )
    rental_active = fields.Boolean(
        string='Alquiler Activo',
        default=True,
    )

    # --- SEPA ---
    sepa_mandate_ids = fields.One2many(
        'sepa.mandate',
        'partner_id',
        string='Mandatos SEPA',
    )
    sepa_mandate_count = fields.Integer(
        string='Nº Mandatos',
        compute='_compute_sepa_mandate_count',
    )
    active_mandate_id = fields.Many2one(
        'sepa.mandate',
        string='Mandato SEPA Activo',
        compute='_compute_active_mandate',
        store=True,
        help='Mandato SEPA activo actual para adeudos directos',
    )

    recurring_invoice_ids = fields.One2many(
        'recurring.invoice',
        'partner_id',
        string='Suscripciones',
    )
    recurring_invoice_count = fields.Integer(
        compute='_compute_recurring_invoice_count',
    )
    rental_invoice_count = fields.Integer(
        string='Nº Facturas',
        compute='_compute_rental_invoice_count',
    )
    rental_pending_amount = fields.Monetary(
        string='Pendiente de Cobro',
        compute='_compute_rental_pending_amount',
        currency_field='currency_id',
    )

    @api.depends('sepa_mandate_ids')
    def _compute_sepa_mandate_count(self):
        for partner in self:
            partner.sepa_mandate_count = len(partner.sepa_mandate_ids)

    @api.depends('sepa_mandate_ids', 'sepa_mandate_ids.state')
    def _compute_active_mandate(self):
        for partner in self:
            active = partner.sepa_mandate_ids.filtered(
                lambda m: m.state == 'active'
            )
            partner.active_mandate_id = active[0] if active else False

    @api.depends('recurring_invoice_ids')
    def _compute_recurring_invoice_count(self):
        for partner in self:
            partner.recurring_invoice_count = len(partner.recurring_invoice_ids)

    def _compute_rental_invoice_count(self):
        Move = self.env['account.move']
        for partner in self:
            partner.rental_invoice_count = Move.search_count([
                ('partner_id', '=', partner.id),
                ('move_type', '=', 'out_invoice'),
                ('recurring_invoice_id', '!=', False),
            ])

    def _compute_rental_pending_amount(self):
        Move = self.env['account.move']
        for partner in self:
            invoices = Move.search([
                ('partner_id', '=', partner.id),
                ('move_type', '=', 'out_invoice'),
                ('recurring_invoice_id', '!=', False),
                ('payment_state', 'in', ('not_paid', 'partial')),
                ('state', '=', 'posted'),
            ])
            partner.rental_pending_amount = sum(i.amount_residual for i in invoices)

    def action_view_mandates(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Mandatos SEPA',
            'res_model': 'sepa.mandate',
            'view_mode': 'list,form',
            'domain': [('partner_id', '=', self.id)],
            'context': {'default_partner_id': self.id},
        }

    def action_view_recurring_invoices(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Suscripciones',
            'res_model': 'recurring.invoice',
            'view_mode': 'list,form',
            'domain': [('partner_id', '=', self.id)],
            'context': {'default_partner_id': self.id},
        }

    def action_view_rental_invoices(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Facturas de Alquiler',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [
                ('partner_id', '=', self.id),
                ('move_type', '=', 'out_invoice'),
                ('recurring_invoice_id', '!=', False),
            ],
        }
