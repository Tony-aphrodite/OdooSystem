import logging
from datetime import date
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class RecurringInvoice(models.Model):
    _name = 'recurring.invoice'
    _description = 'Facturación Recurrente de Alquiler'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Referencia',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('Nuevo'),
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Cliente',
        required=True,
        domain=[('is_rental_customer', '=', True)],
        tracking=True,
    )
    product_description = fields.Char(
        string='Concepto',
        required=True,
        default='Alquiler mensual de equipos',
    )
    amount = fields.Monetary(
        string='Importe',
        currency_field='currency_id',
        required=True,
        tracking=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        default=lambda self: self.env.company.currency_id,
    )
    interval = fields.Selection([
        ('monthly', 'Mensual'),
        ('quarterly', 'Trimestral'),
        ('yearly', 'Anual'),
    ], string='Periodicidad', default='monthly', required=True)

    day_of_month = fields.Integer(
        string='Día del Mes',
        default=1,
        help='Día del mes para generar la factura (1-28)',
    )
    next_invoice_date = fields.Date(
        string='Próxima Factura',
        required=True,
        default=fields.Date.today,
        tracking=True,
    )
    start_date = fields.Date(
        string='Fecha de Inicio',
        default=fields.Date.today,
    )
    end_date = fields.Date(
        string='Fecha de Fin',
        help='Dejar vacío para facturación indefinida',
    )
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('active', 'Activo'),
        ('paused', 'Pausado'),
        ('closed', 'Cerrado'),
    ], string='Estado', default='draft', required=True, tracking=True)

    invoice_count = fields.Integer(
        string='Facturas Generadas',
        compute='_compute_invoice_count',
    )
    invoice_ids = fields.One2many(
        'account.move',
        'recurring_invoice_id',
        string='Facturas',
    )
    company_id = fields.Many2one(
        'res.company',
        string='Empresa',
        default=lambda self: self.env.company,
        required=True,
    )
    mandate_id = fields.Many2one(
        'sepa.mandate',
        string='Mandato SEPA',
        domain="[('partner_id', '=', partner_id), ('state', '=', 'active')]",
        help='Mandato SEPA para el adeudo directo de esta suscripción',
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('Nuevo')) == _('Nuevo'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'recurring.invoice'
                ) or _('Nuevo')
        return super().create(vals_list)

    @api.depends('invoice_ids')
    def _compute_invoice_count(self):
        for rec in self:
            rec.invoice_count = len(rec.invoice_ids)

    def action_activate(self):
        for rec in self:
            if not rec.partner_id or not rec.amount:
                raise UserError(
                    _('Debe indicar cliente e importe antes de activar.')
                )
            rec.state = 'active'

    def action_pause(self):
        for rec in self:
            rec.state = 'paused'

    def action_close(self):
        for rec in self:
            rec.state = 'closed'

    def action_reset_to_draft(self):
        for rec in self:
            rec.state = 'draft'

    def action_view_invoices(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Facturas',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('recurring_invoice_id', '=', self.id)],
        }

    def _get_interval_delta(self):
        if self.interval == 'monthly':
            return relativedelta(months=1)
        elif self.interval == 'quarterly':
            return relativedelta(months=3)
        elif self.interval == 'yearly':
            return relativedelta(years=1)

    def _create_invoice(self):
        """Create a single invoice for this recurring subscription."""
        self.ensure_one()
        invoice_vals = {
            'move_type': 'out_invoice',
            'partner_id': self.partner_id.id,
            'invoice_date': fields.Date.today(),
            'recurring_invoice_id': self.id,
            'company_id': self.company_id.id,
            'invoice_line_ids': [(0, 0, {
                'name': self.product_description,
                'quantity': 1,
                'price_unit': self.amount,
            })],
        }
        invoice = self.env['account.move'].create(invoice_vals)
        _logger.info(
            'Factura recurrente %s creada para cliente %s - Importe: %s',
            invoice.name, self.partner_id.name, self.amount,
        )
        return invoice

    @api.model
    def _cron_generate_recurring_invoices(self):
        """Cron job: generate invoices for all active recurring subscriptions
        whose next_invoice_date is today or in the past."""
        today = fields.Date.today()
        subscriptions = self.search([
            ('state', '=', 'active'),
            ('next_invoice_date', '<=', today),
            '|',
            ('end_date', '=', False),
            ('end_date', '>=', today),
        ])

        _logger.info(
            'Generación de facturas recurrentes: %d suscripciones encontradas',
            len(subscriptions),
        )

        for sub in subscriptions:
            try:
                sub._create_invoice()
                sub.next_invoice_date = sub.next_invoice_date + sub._get_interval_delta()
            except Exception as e:
                _logger.error(
                    'Error generando factura para suscripción %s: %s',
                    sub.name, str(e),
                )
        return True


class AccountMove(models.Model):
    _inherit = 'account.move'

    recurring_invoice_id = fields.Many2one(
        'recurring.invoice',
        string='Suscripción Recurrente',
        readonly=True,
    )
