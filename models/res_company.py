from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    sepa_creditor_identifier = fields.Char(
        string='Identificador de Acreedor SEPA',
        help='Identificador SEPA del acreedor (AT-02). '
             'Normalmente ES + dígitos de control + sufijo + CIF. '
             'Se usa por defecto en las remesas SEPA.',
    )

    def _get_sepa_creditor_bank(self):
        """Bank account used by default as the creditor account in remittances."""
        self.ensure_one()
        return self.partner_id.bank_ids[:1]
