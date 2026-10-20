import base64
from datetime import date, timedelta

from lxml import etree

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import AlquilerTestCommon

NS = {'p': 'urn:iso:std:iso:20022:tech:xsd:pain.008.001.02'}


@tagged('post_install', '-at_install')
class TestSepaRemittance(AlquilerTestCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.invoice_a = cls._create_invoice(cls.debtor_a, 120.50)
        cls.invoice_a2 = cls._create_invoice(cls.debtor_a, 45.00)
        cls.invoice_b = cls._create_invoice(cls.debtor_b, 80.25)

    def _line_vals(self, invoice, mandate, collection_date, bic='CAIXESBBXXX'):
        return {
            'partner_id': invoice.partner_id.id,
            'invoice_id': invoice.id,
            'mandate_id': mandate.id,
            'amount': invoice.amount_residual,
            'communication': invoice.name,
            'collection_date': collection_date,
            'iban': mandate.partner_bank_id.acc_number,
            'bic': bic,
        }

    def _create_remittance_with_lines(self):
        remittance = self._create_remittance()
        remittance.write({'line_ids': [
            Command.create(self._line_vals(self.invoice_a, self.mandate_a, date(2026, 11, 5))),
            Command.create(self._line_vals(self.invoice_a2, self.mandate_a, date(2026, 11, 5))),
            Command.create(self._line_vals(self.invoice_b, self.mandate_b, date(2026, 11, 20), bic='')),
        ]})
        return remittance

    def test_add_pending_invoices(self):
        without_mandate = self._create_invoice(self.partner_without_mandate, 50.0)
        draft = self._create_invoice(self.debtor_a, 30.0, post=False)
        paid = self._create_invoice(self.debtor_b, 60.0)
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=paid.ids,
        ).create({})._create_payments()

        remittance = self._create_remittance()
        remittance.action_add_pending_invoices()

        invoices = remittance.line_ids.invoice_id
        self.assertIn(self.invoice_a, invoices)
        self.assertIn(self.invoice_a2, invoices)
        self.assertIn(self.invoice_b, invoices)
        self.assertNotIn(without_mandate, invoices)
        self.assertNotIn(draft, invoices)
        self.assertNotIn(paid, invoices)

        line = remittance.line_ids.filtered(lambda l: l.invoice_id == self.invoice_a)
        self.assertEqual(line.partner_id, self.debtor_a)
        self.assertEqual(line.mandate_id, self.mandate_a)
        self.assertEqual(line.amount, 120.50)
        self.assertEqual(line.communication, self.invoice_a.name)
        self.assertEqual(line.iban.replace(' ', ''), 'ES7921000813610123456789')
        self.assertEqual(line.bic, 'CAIXESBBXXX')

        # The collection date is the next occurrence of the customer's collection day
        today = fields.Date.today()
        self.assertEqual(line.collection_date.day, 5)
        self.assertGreaterEqual(line.collection_date, today)
        self.assertLess(line.collection_date, today + timedelta(days=32))

        # Invoices that are already in the remittance are not added again
        with self.assertRaises(UserError):
            remittance.action_add_pending_invoices()

    def test_add_pending_invoices_only_in_draft(self):
        remittance = self._create_remittance_with_lines()
        remittance.action_confirm()
        with self.assertRaises(UserError):
            remittance.action_add_pending_invoices()

    def test_confirm_requires_lines_and_creditor_data(self):
        remittance = self._create_remittance()
        with self.assertRaises(UserError):
            remittance.action_confirm()

        remittance.write({'line_ids': [
            Command.create(self._line_vals(self.invoice_a, self.mandate_a, date(2026, 11, 5))),
        ]})
        remittance.creditor_identifier = False
        with self.assertRaises(UserError):
            remittance.action_confirm()

        remittance.creditor_identifier = self.company.sepa_creditor_identifier
        remittance.creditor_iban = False
        with self.assertRaises(UserError):
            remittance.action_confirm()

        remittance.creditor_iban = self.creditor_iban
        with self.assertRaises(UserError):
            remittance.action_generate_xml()

        remittance.action_confirm()
        self.assertEqual(remittance.state, 'confirmed')

    def test_pain008_export(self):
        remittance = self._create_remittance_with_lines()
        self.assertEqual(remittance.line_count, 3)
        self.assertAlmostEqual(remittance.total_amount, 245.75)

        remittance.action_confirm()
        action = remittance.action_generate_xml()

        self.assertEqual(remittance.state, 'exported')
        self.assertEqual(action['type'], 'ir.actions.act_url')
        self.assertTrue(remittance.xml_filename.startswith('SEPA_DD_'))
        self.assertTrue(remittance.xml_filename.endswith('.xml'))

        root = etree.fromstring(base64.b64decode(remittance.xml_file))
        self.assertEqual(root.tag, '{%s}Document' % NS['p'])

        header = root.find('p:CstmrDrctDbtInitn/p:GrpHdr', NS)
        self.assertEqual(header.findtext('p:NbOfTxs', namespaces=NS), '3')
        self.assertEqual(header.findtext('p:CtrlSum', namespaces=NS), '245.75')
        self.assertEqual(header.findtext('p:InitgPty/p:Nm', namespaces=NS), 'Alquileres Test S.L.')

        # One payment block per collection date, in date order
        blocks = root.findall('p:CstmrDrctDbtInitn/p:PmtInf', NS)
        self.assertEqual(
            [b.findtext('p:ReqdColltnDt', namespaces=NS) for b in blocks],
            ['2026-11-05', '2026-11-20'],
        )
        self.assertEqual([b.findtext('p:NbOfTxs', namespaces=NS) for b in blocks], ['2', '1'])
        self.assertEqual([b.findtext('p:CtrlSum', namespaces=NS) for b in blocks], ['165.50', '80.25'])

        for block in blocks:
            self.assertEqual(block.findtext('p:PmtMtd', namespaces=NS), 'DD')
            self.assertEqual(block.findtext('p:PmtTpInf/p:SvcLvl/p:Cd', namespaces=NS), 'SEPA')
            self.assertEqual(block.findtext('p:PmtTpInf/p:LclInstrm/p:Cd', namespaces=NS), 'CORE')
            self.assertEqual(block.findtext('p:PmtTpInf/p:SeqTp', namespaces=NS), 'RCUR')
            self.assertEqual(block.findtext('p:Cdtr/p:Nm', namespaces=NS), 'Alquileres Test S.L.')
            self.assertEqual(
                block.findtext('p:CdtrAcct/p:Id/p:IBAN', namespaces=NS),
                'ES9121000418450200051332',
            )
            self.assertEqual(
                block.findtext('p:CdtrAgt/p:FinInstnId/p:BIC', namespaces=NS), 'CAIXESBBXXX',
            )
            self.assertEqual(
                block.findtext('p:CdtrSchmeId/p:Id/p:PrvtId/p:Othr/p:Id', namespaces=NS),
                'ES97000B12345678',
            )

        tx = blocks[1].find('p:DrctDbtTxInf', NS)
        self.assertEqual(tx.findtext('p:PmtId/p:EndToEndId', namespaces=NS), self.invoice_b.name)
        amount = tx.find('p:InstdAmt', NS)
        self.assertEqual((amount.text, amount.get('Ccy')), ('80.25', 'EUR'))
        self.assertEqual(
            tx.findtext('p:DrctDbtTx/p:MndtRltdInf/p:MndtId', namespaces=NS), 'MND-TEST-B',
        )
        self.assertEqual(
            tx.findtext('p:DrctDbtTx/p:MndtRltdInf/p:DtOfSgntr', namespaces=NS), '2024-01-15',
        )
        # A line without BIC is exported as NOTPROVIDED
        self.assertEqual(
            tx.findtext('p:DbtrAgt/p:FinInstnId/p:Othr/p:Id', namespaces=NS), 'NOTPROVIDED',
        )
        self.assertEqual(tx.findtext('p:Dbtr/p:Nm', namespaces=NS), 'Debtor B')
        self.assertEqual(
            tx.findtext('p:DbtrAcct/p:Id/p:IBAN', namespaces=NS), 'ES6621000418401234567891',
        )
        self.assertEqual(tx.findtext('p:RmtInf/p:Ustrd', namespaces=NS), self.invoice_b.name)

    def test_workflow_and_first_debit(self):
        self.mandate_a.sequence_type = 'FRST'
        remittance = self._create_remittance()
        remittance.write({'line_ids': [
            Command.create(self._line_vals(self.invoice_a, self.mandate_a, date(2026, 11, 5))),
        ]})

        remittance.action_confirm()
        with self.assertRaises(UserError):
            remittance.action_mark_sent()

        remittance.action_generate_xml()
        remittance.action_mark_sent()
        self.assertEqual(remittance.state, 'sent')

        # After the first successful collection the mandate becomes recurring
        remittance.action_reconcile()
        self.assertEqual(remittance.state, 'reconciled')
        self.assertEqual(self.mandate_a.sequence_type, 'RCUR')

        remittance.action_close()
        self.assertEqual(remittance.state, 'closed')

    def test_reset_to_draft_clears_file(self):
        remittance = self._create_remittance_with_lines()
        remittance.action_confirm()
        remittance.action_generate_xml()
        self.assertTrue(remittance.xml_file)

        remittance.action_reset_to_draft()
        self.assertEqual(remittance.state, 'draft')
        self.assertFalse(remittance.xml_file)
        self.assertFalse(remittance.xml_filename)
