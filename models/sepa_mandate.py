import logging
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

from .sepa_validation import is_valid_bic, is_valid_creditor_identifier, is_valid_iban

_logger = logging.getLogger(__name__)


class SepaMandate(models.Model):
    _name = 'sepa.mandate'
    _description = 'Mandato SEPA de Adeudo Directo'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'unique_mandate_reference'

    unique_mandate_reference = fields.Char(
        string='Referencia Única de Mandato (UMR)',
        required=True,
        copy=False,
        tracking=True,
        help='Identificador único del mandato SEPA asignado por el acreedor',
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Cliente',
        required=True,
        tracking=True,
        domain=[('customer_rank', '>', 0)],
    )
    partner_bank_id = fields.Many2one(
        'res.partner.bank',
        string='Cuenta Bancaria (IBAN)',
        required=True,
        tracking=True,
        domain="[('partner_id', '=', partner_id)]",
        help='Cuenta bancaria del deudor para el adeudo directo',
    )
    iban = fields.Char(
        related='partner_bank_id.acc_number',
        string='IBAN',
        readonly=True,
    )
    bic = fields.Char(
        string='BIC/SWIFT',
        help='Código BIC de la entidad bancaria del deudor',
    )
    signature_date = fields.Date(
        string='Fecha de Firma',
        required=True,
        default=fields.Date.today,
        tracking=True,
    )
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('active', 'Activo'),
        ('closed', 'Cerrado'),
        ('revoked', 'Revocado'),
    ], string='Estado', default='draft', required=True, tracking=True)

    scheme = fields.Selection([
        ('CORE', 'CORE (Particulares)'),
        ('B2B', 'B2B (Empresas)'),
    ], string='Esquema', default='CORE', required=True, tracking=True)

    sequence_type = fields.Selection([
        ('FRST', 'Primer Adeudo'),
        ('RCUR', 'Recurrente'),
        ('FNAL', 'Último Adeudo'),
        ('OOFF', 'Adeudo Único'),
    ], string='Tipo de Secuencia', default='FRST', required=True, tracking=True,
        help='FRST para el primer cobro, luego cambia automáticamente a RCUR',
    )

    creditor_identifier = fields.Char(
        string='Identificador del Acreedor',
        help='Número de identificación del acreedor SEPA (CIF + sufijo)',
    )
    company_id = fields.Many2one(
        'res.company',
        string='Empresa',
        default=lambda self: self.env.company,
        required=True,
    )
    notes = fields.Text(string='Notas')

    _sql_constraints = [
        ('unique_mandate_ref_unique',
         'UNIQUE(unique_mandate_reference, company_id)',
         'La referencia de mandato debe ser única por empresa.'),
    ]

    @api.constrains('partner_bank_id', 'bic', 'creditor_identifier')
    def _check_sepa_identifiers(self):
        for mandate in self:
            if not is_valid_iban(mandate.partner_bank_id.acc_number):
                raise ValidationError(_(
                    'La cuenta %(account)s del mandato %(mandate)s no es un IBAN válido. '
                    'Los adeudos SEPA necesitan el IBAN del deudor.',
                    account=mandate.partner_bank_id.acc_number,
                    mandate=mandate.unique_mandate_reference,
                ))
            if mandate.bic and not is_valid_bic(mandate.bic):
                raise ValidationError(_(
                    'El BIC %s no es válido. Debe tener 8 u 11 caracteres en mayúsculas, '
                    'por ejemplo CAIXESBBXXX.',
                    mandate.bic,
                ))
            identifier = mandate.creditor_identifier
            if identifier and not is_valid_creditor_identifier(identifier):
                raise ValidationError(_(
                    'El identificador de acreedor SEPA %s no es válido.', identifier,
                ))

    def action_activate(self):
        for mandate in self:
            if mandate.state != 'draft':
                raise ValidationError(
                    _('Solo se pueden activar mandatos en estado borrador.')
                )
            mandate.state = 'active'

    def action_close(self):
        for mandate in self:
            mandate.state = 'closed'

    def action_revoke(self):
        for mandate in self:
            mandate.state = 'revoked'

    def action_reset_to_draft(self):
        for mandate in self:
            mandate.state = 'draft'

    def mark_as_recurring(self):
        """After first successful direct debit, change FRST to RCUR."""
        for mandate in self:
            if mandate.sequence_type == 'FRST':
                mandate.sequence_type = 'RCUR'
