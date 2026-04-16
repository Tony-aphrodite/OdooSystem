import base64
import logging
from datetime import datetime, date
from collections import defaultdict
from lxml import etree

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class SepaRemittance(models.Model):
    _name = 'sepa.remittance'
    _description = 'Remesa SEPA de Adeudo Directo'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    name = fields.Char(
        string='Referencia',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('Nuevo'),
    )
    date = fields.Date(
        string='Fecha de Remesa',
        default=fields.Date.today,
        required=True,
        tracking=True,
    )
    requested_collection_date = fields.Date(
        string='Fecha de Cobro Solicitada',
        required=True,
        tracking=True,
        help='Fecha en la que se solicita al banco que ejecute los adeudos',
    )
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('confirmed', 'Confirmada'),
        ('exported', 'Exportada (XML)'),
        ('sent', 'Presentada al Banco'),
        ('reconciled', 'Conciliada'),
        ('closed', 'Cerrada'),
    ], string='Estado', default='draft', required=True, tracking=True)

    line_ids = fields.One2many(
        'sepa.remittance.line',
        'remittance_id',
        string='Líneas de Remesa',
    )
    line_count = fields.Integer(
        string='Nº de Recibos',
        compute='_compute_totals',
    )
    total_amount = fields.Monetary(
        string='Importe Total',
        currency_field='currency_id',
        compute='_compute_totals',
        store=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        default=lambda self: self.env.company.currency_id,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Empresa',
        default=lambda self: self.env.company,
        required=True,
    )

    # Creditor info
    creditor_name = fields.Char(
        string='Nombre del Acreedor',
        default=lambda self: self.env.company.name,
    )
    creditor_identifier = fields.Char(
        string='Identificador del Acreedor (CIF)',
        default='ES91000B16612525',
        help='Identificador SEPA del acreedor (AT-02). '
             'Normalmente ES + sufijo + CIF.',
    )
    creditor_iban = fields.Char(
        string='IBAN del Acreedor',
        default='ES9800810652210002257827',
        help='Cuenta bancaria del acreedor donde se recibirán los fondos',
    )
    creditor_bic = fields.Char(
        string='BIC del Acreedor',
        default='BSABESBB',
    )
    bank_name = fields.Selection([
        ('cajamar', 'Cajamar'),
        ('sabadell', 'Sabadell'),
    ], string='Banco de Presentación', default='sabadell')

    # XML file
    xml_file = fields.Binary(
        string='Fichero SEPA XML',
        readonly=True,
    )
    xml_filename = fields.Char(
        string='Nombre del Fichero',
        readonly=True,
    )

    notes = fields.Text(string='Notas')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('Nuevo')) == _('Nuevo'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'sepa.remittance'
                ) or _('Nuevo')
        return super().create(vals_list)

    @api.depends('line_ids', 'line_ids.amount')
    def _compute_totals(self):
        for rem in self:
            rem.line_count = len(rem.line_ids)
            rem.total_amount = sum(rem.line_ids.mapped('amount'))

    def action_add_pending_invoices(self):
        """Add all open (posted, unpaid) invoices with active SEPA mandates."""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('Solo se pueden añadir facturas en estado borrador.'))

        existing_invoice_ids = self.line_ids.mapped('invoice_id').ids

        invoices = self.env['account.move'].search([
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('payment_state', 'in', ['not_paid', 'partial']),
            ('partner_id.active_mandate_id', '!=', False),
            ('id', 'not in', existing_invoice_ids),
        ])

        lines_vals = []
        today = fields.Date.today()
        for inv in invoices:
            mandate = inv.partner_id.active_mandate_id
            # Calculate collection date from partner's collection day
            collection_day = inv.partner_id.rental_collection_day or 5
            try:
                coll_date = today.replace(day=collection_day)
                if coll_date < today:
                    # If the day has passed this month, set to next month
                    if today.month == 12:
                        coll_date = date(today.year + 1, 1, collection_day)
                    else:
                        coll_date = date(today.year, today.month + 1, collection_day)
            except ValueError:
                coll_date = today.replace(day=28)

            lines_vals.append((0, 0, {
                'remittance_id': self.id,
                'partner_id': inv.partner_id.id,
                'invoice_id': inv.id,
                'mandate_id': mandate.id,
                'amount': inv.amount_residual,
                'communication': inv.name or '',
                'collection_date': coll_date,
                'iban': mandate.partner_bank_id.acc_number,
                'bic': mandate.bic or '',
            }))

        if not lines_vals:
            raise UserError(
                _('No se encontraron facturas pendientes con mandato SEPA activo.')
            )

        self.write({'line_ids': lines_vals})
        return True

    def action_confirm(self):
        for rem in self:
            if not rem.line_ids:
                raise UserError(_('No hay líneas en la remesa.'))
            if not rem.requested_collection_date:
                raise UserError(_('Debe indicar la fecha de cobro solicitada.'))
            if not rem.creditor_identifier:
                raise UserError(_('Debe indicar el identificador del acreedor.'))
            if not rem.creditor_iban:
                raise UserError(_('Debe indicar el IBAN del acreedor.'))
            rem.state = 'confirmed'

    def action_generate_xml(self):
        """Generate SEPA Direct Debit XML (pain.008.001.02)."""
        self.ensure_one()
        if self.state not in ('confirmed', 'exported'):
            raise UserError(
                _('La remesa debe estar confirmada antes de generar el XML.')
            )

        xml_content = self._generate_pain_008_xml()
        filename = 'SEPA_DD_%s_%s.xml' % (
            self.name.replace('/', '-'),
            fields.Date.today().strftime('%Y%m%d'),
        )

        self.write({
            'xml_file': base64.b64encode(xml_content),
            'xml_filename': filename,
            'state': 'exported',
        })

        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s/%s/xml_file/%s?download=true' % (
                self._name.replace('.', '_'),
                self.id,
                filename,
            ),
            'target': 'new',
        }

    def _generate_pain_008_xml(self):
        """Generate ISO 20022 pain.008.001.02 XML for SEPA Direct Debit.

        Lines are grouped by collection_date, creating one PmtInf block
        per unique collection date (as required by SEPA when dates differ).
        """
        nsmap = {
            None: 'urn:iso:std:iso:20022:tech:xsd:pain.008.001.02',
            'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
        }

        root = etree.Element('Document', nsmap=nsmap)
        cstmr_drct_dbt_initn = etree.SubElement(root, 'CstmrDrctDbtInitn')

        # --- Group Header ---
        grp_hdr = etree.SubElement(cstmr_drct_dbt_initn, 'GrpHdr')
        msg_id = 'SEPA-DD-%s-%s' % (
            self.name.replace('/', '-'),
            datetime.now().strftime('%Y%m%d%H%M%S'),
        )
        etree.SubElement(grp_hdr, 'MsgId').text = msg_id
        etree.SubElement(grp_hdr, 'CreDtTm').text = datetime.now().strftime(
            '%Y-%m-%dT%H:%M:%S'
        )
        etree.SubElement(grp_hdr, 'NbOfTxs').text = str(len(self.line_ids))
        etree.SubElement(grp_hdr, 'CtrlSum').text = '%.2f' % self.total_amount
        initg_pty = etree.SubElement(grp_hdr, 'InitgPty')
        etree.SubElement(initg_pty, 'Nm').text = self.creditor_name or self.company_id.name

        # Group lines by collection date
        lines_by_date = defaultdict(list)
        for line in self.line_ids:
            coll_date = line.collection_date or self.requested_collection_date
            lines_by_date[coll_date].append(line)

        # --- One PmtInf block per collection date ---
        for pmt_idx, (coll_date, lines) in enumerate(
            sorted(lines_by_date.items()), start=1
        ):
            pmt_inf = etree.SubElement(cstmr_drct_dbt_initn, 'PmtInf')
            etree.SubElement(pmt_inf, 'PmtInfId').text = (
                '%s-%d' % (msg_id, pmt_idx)
            )
            etree.SubElement(pmt_inf, 'PmtMtd').text = 'DD'

            group_amount = sum(l.amount for l in lines)
            etree.SubElement(pmt_inf, 'BtchBookg').text = 'true'
            etree.SubElement(pmt_inf, 'NbOfTxs').text = str(len(lines))
            etree.SubElement(pmt_inf, 'CtrlSum').text = '%.2f' % group_amount

            # Payment Type Information
            pmt_tp_inf = etree.SubElement(pmt_inf, 'PmtTpInf')
            svc_lvl = etree.SubElement(pmt_tp_inf, 'SvcLvl')
            etree.SubElement(svc_lvl, 'Cd').text = 'SEPA'
            lcl_instrm = etree.SubElement(pmt_tp_inf, 'LclInstrm')
            etree.SubElement(lcl_instrm, 'Cd').text = 'CORE'
            etree.SubElement(pmt_tp_inf, 'SeqTp').text = 'RCUR'

            # Requested Collection Date (per group)
            etree.SubElement(pmt_inf, 'ReqdColltnDt').text = (
                coll_date.strftime('%Y-%m-%d')
            )

            # Creditor
            cdtr = etree.SubElement(pmt_inf, 'Cdtr')
            etree.SubElement(cdtr, 'Nm').text = (
                self.creditor_name or self.company_id.name
            )

            # Creditor Account
            cdtr_acct = etree.SubElement(pmt_inf, 'CdtrAcct')
            cdtr_acct_id = etree.SubElement(cdtr_acct, 'Id')
            etree.SubElement(cdtr_acct_id, 'IBAN').text = (
                self.creditor_iban.replace(' ', '')
            )

            # Creditor Agent (BIC)
            cdtr_agt = etree.SubElement(pmt_inf, 'CdtrAgt')
            fin_instn_id = etree.SubElement(cdtr_agt, 'FinInstnId')
            if self.creditor_bic:
                etree.SubElement(fin_instn_id, 'BIC').text = self.creditor_bic
            else:
                etree.SubElement(fin_instn_id, 'Othr').text = 'NOTPROVIDED'

            # Creditor Scheme Identification
            cdtr_schme_id = etree.SubElement(pmt_inf, 'CdtrSchmeId')
            csi_id = etree.SubElement(cdtr_schme_id, 'Id')
            csi_prvt_id = etree.SubElement(csi_id, 'PrvtId')
            csi_othr = etree.SubElement(csi_prvt_id, 'Othr')
            etree.SubElement(csi_othr, 'Id').text = self.creditor_identifier
            schme_nm = etree.SubElement(csi_othr, 'SchmeNm')
            etree.SubElement(schme_nm, 'Prtry').text = 'SEPA'

            # --- Transaction lines ---
            for line in lines:
                drct_dbt_tx_inf = etree.SubElement(pmt_inf, 'DrctDbtTxInf')

                # Payment ID
                pmt_id = etree.SubElement(drct_dbt_tx_inf, 'PmtId')
                etree.SubElement(pmt_id, 'EndToEndId').text = (
                    line.communication or line.invoice_id.name or 'N/A'
                )

                # Amount
                instd_amt = etree.SubElement(drct_dbt_tx_inf, 'InstdAmt')
                instd_amt.set('Ccy', 'EUR')
                instd_amt.text = '%.2f' % line.amount

                # Mandate Related Information
                drct_dbt_tx = etree.SubElement(drct_dbt_tx_inf, 'DrctDbtTx')
                mndt_rltd_inf = etree.SubElement(drct_dbt_tx, 'MndtRltdInf')
                etree.SubElement(mndt_rltd_inf, 'MndtId').text = (
                    line.mandate_id.unique_mandate_reference
                )
                etree.SubElement(mndt_rltd_inf, 'DtOfSgntr').text = (
                    line.mandate_id.signature_date.strftime('%Y-%m-%d')
                )

                # Debtor Agent (BIC)
                dbtr_agt = etree.SubElement(drct_dbt_tx_inf, 'DbtrAgt')
                dbtr_fin_instn = etree.SubElement(dbtr_agt, 'FinInstnId')
                if line.bic:
                    etree.SubElement(dbtr_fin_instn, 'BIC').text = line.bic
                else:
                    dbtr_othr = etree.SubElement(dbtr_fin_instn, 'Othr')
                    etree.SubElement(dbtr_othr, 'Id').text = 'NOTPROVIDED'

                # Debtor
                dbtr = etree.SubElement(drct_dbt_tx_inf, 'Dbtr')
                etree.SubElement(dbtr, 'Nm').text = line.partner_id.name

                # Debtor Account
                dbtr_acct = etree.SubElement(drct_dbt_tx_inf, 'DbtrAcct')
                dbtr_acct_id = etree.SubElement(dbtr_acct, 'Id')
                etree.SubElement(dbtr_acct_id, 'IBAN').text = (
                    line.iban.replace(' ', '') if line.iban else ''
                )

                # Remittance Information
                rmt_inf = etree.SubElement(drct_dbt_tx_inf, 'RmtInf')
                etree.SubElement(rmt_inf, 'Ustrd').text = (
                    line.communication or 'Alquiler de equipos'
                )

        xml_string = etree.tostring(
            root,
            pretty_print=True,
            xml_declaration=True,
            encoding='UTF-8',
        )
        return xml_string

    def action_mark_sent(self):
        for rem in self:
            if rem.state != 'exported':
                raise UserError(
                    _('La remesa debe estar exportada antes de marcarla como presentada.')
                )
            rem.state = 'sent'

    def action_reconcile(self):
        for rem in self:
            rem.state = 'reconciled'
            # Mark mandates as recurring after first successful collection
            for line in rem.line_ids:
                if line.mandate_id:
                    line.mandate_id.mark_as_recurring()

    def action_close(self):
        for rem in self:
            rem.state = 'closed'

    def action_reset_to_draft(self):
        for rem in self:
            rem.state = 'draft'
            rem.xml_file = False
            rem.xml_filename = False


class SepaRemittanceLine(models.Model):
    _name = 'sepa.remittance.line'
    _description = 'Línea de Remesa SEPA'

    remittance_id = fields.Many2one(
        'sepa.remittance',
        string='Remesa',
        required=True,
        ondelete='cascade',
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Cliente',
        required=True,
    )
    invoice_id = fields.Many2one(
        'account.move',
        string='Factura',
        domain=[('move_type', '=', 'out_invoice')],
    )
    mandate_id = fields.Many2one(
        'sepa.mandate',
        string='Mandato SEPA',
        required=True,
    )
    amount = fields.Monetary(
        string='Importe',
        currency_field='currency_id',
        required=True,
    )
    currency_id = fields.Many2one(
        related='remittance_id.currency_id',
    )
    communication = fields.Char(
        string='Comunicación',
        help='Referencia que aparecerá en el extracto bancario del deudor',
    )
    collection_date = fields.Date(
        string='Fecha de Cobro',
        help='Fecha de cobro específica para este recibo (según ficha del cliente)',
    )
    iban = fields.Char(string='IBAN del Deudor')
    bic = fields.Char(string='BIC del Deudor')

    state = fields.Selection([
        ('pending', 'Pendiente'),
        ('paid', 'Cobrado'),
        ('returned', 'Devuelto'),
    ], string='Estado', default='pending')

    return_reason = fields.Char(
        string='Motivo de Devolución',
        help='Código o motivo de devolución del banco',
    )
    return_date = fields.Date(string='Fecha de Devolución')
