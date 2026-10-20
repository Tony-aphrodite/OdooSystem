from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .sepa_validation import is_valid_creditor_identifier


class ResCompany(models.Model):
    _inherit = 'res.company'

    sepa_creditor_identifier = fields.Char(
        string='Identificador de Acreedor SEPA',
        help='Identificador SEPA del acreedor (AT-02). '
             'Normalmente ES + dígitos de control + sufijo + CIF. '
             'Se usa por defecto en las remesas SEPA.',
    )

    @api.constrains('sepa_creditor_identifier')
    def _check_sepa_creditor_identifier(self):
        for company in self:
            identifier = company.sepa_creditor_identifier
            if identifier and not is_valid_creditor_identifier(identifier):
                raise ValidationError(_(
                    'El identificador de acreedor SEPA %s no es válido. Debe tener el '
                    'código de país, dos dígitos de control, un sufijo de tres caracteres '
                    'y el NIF, sin espacios (por ejemplo ES97000B12345678).',
                    identifier,
                ))

    def _get_sepa_creditor_bank(self):
        """Bank account used by default as the creditor account in remittances."""
        self.ensure_one()
        return self.partner_id.bank_ids[:1]
