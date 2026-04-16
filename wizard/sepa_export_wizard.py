from odoo import api, fields, models, _
from odoo.exceptions import UserError


class SepaExportWizard(models.TransientModel):
    _name = 'sepa.export.wizard'
    _description = 'Asistente para Generar Remesa SEPA'

    date_from = fields.Date(
        string='Facturas Desde',
        default=fields.Date.today,
    )
    date_to = fields.Date(
        string='Facturas Hasta',
        default=fields.Date.today,
    )
    requested_collection_date = fields.Date(
        string='Fecha de Cobro por Defecto',
        required=True,
        help='Fecha de cobro por defecto. Cada recibo usará la fecha '
             'según la ficha del cliente si está configurada.',
    )
    bank_name = fields.Selection([
        ('cajamar', 'Cajamar'),
        ('sabadell', 'Sabadell'),
    ], string='Banco', required=True, default='sabadell')
    creditor_identifier = fields.Char(
        string='Identificador del Acreedor',
        required=True,
        default='ES91000B16612525',
    )
    creditor_iban = fields.Char(
        string='IBAN del Acreedor',
        required=True,
        default='ES9800810652210002257827',
    )
    creditor_bic = fields.Char(
        string='BIC del Acreedor',
        default='BSABESBB',
    )

    def action_create_remittance(self):
        """Create a new SEPA remittance and add pending invoices."""
        self.ensure_one()

        remittance = self.env['sepa.remittance'].create({
            'requested_collection_date': self.requested_collection_date,
            'bank_name': self.bank_name,
            'creditor_identifier': self.creditor_identifier,
            'creditor_iban': self.creditor_iban,
            'creditor_bic': self.creditor_bic,
        })

        remittance.action_add_pending_invoices()

        return {
            'type': 'ir.actions.act_window',
            'name': 'Remesa SEPA',
            'res_model': 'sepa.remittance',
            'res_id': remittance.id,
            'view_mode': 'form',
            'target': 'current',
        }
