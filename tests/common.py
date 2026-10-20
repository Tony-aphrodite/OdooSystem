from datetime import date

from odoo import Command, fields
from odoo.tests import TransactionCase


class AlquilerTestCommon(TransactionCase):
    """Separate company with SEPA creditor data and two debtors with active mandates.

    The tests use their own company and user, so they do not depend on the
    data or the accounting setup that already exists in the database.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env['res.company'].create({
            'name': 'Alquileres Test S.L.',
            'sepa_creditor_identifier': 'ES97000B12345678',
        })
        cls.env['account.chart.template'].try_loading(
            'generic_coa', company=cls.company, install_demo=False,
        )
        cls.creditor_iban = 'ES91 2100 0418 4502 0005 1332'

        cls.user = cls.env['res.users'].create({
            'name': 'Alquiler Test Manager',
            'login': 'alquiler_test_manager',
            'company_id': cls.company.id,
            'company_ids': [Command.set(cls.company.ids)],
            'groups_id': [Command.set([
                cls.env.ref('base.group_user').id,
                cls.env.ref('account.group_account_invoice').id,
                cls.env.ref('alquiler_equipos.group_alquiler_manager').id,
            ])],
        })
        cls.env = cls.env(context=dict(cls.env.context, allowed_company_ids=cls.company.ids))

        cls.debtor_a, cls.mandate_a = cls._create_debtor(
            'Debtor A', 'ES79 2100 0813 6101 2345 6789', 'MND-TEST-A', collection_day=5,
        )
        cls.debtor_b, cls.mandate_b = cls._create_debtor(
            'Debtor B', 'ES66 2100 0418 4012 3456 7891', 'MND-TEST-B', collection_day=20,
        )
        cls.partner_without_mandate = cls.env['res.partner'].create({'name': 'No Mandate'})

        cls.env = cls.env(user=cls.user)

    @classmethod
    def _create_debtor(cls, name, iban, reference, collection_day):
        partner = cls.env['res.partner'].create({
            'name': name,
            'is_rental_customer': True,
            'rental_collection_day': collection_day,
        })
        bank = cls.env['res.partner.bank'].create({
            'partner_id': partner.id,
            'acc_number': iban,
        })
        mandate = cls.env['sepa.mandate'].create({
            'unique_mandate_reference': reference,
            'partner_id': partner.id,
            'partner_bank_id': bank.id,
            'bic': 'CAIXESBBXXX',
            'signature_date': date(2024, 1, 15),
            'sequence_type': 'RCUR',
        })
        mandate.action_activate()
        return partner, mandate

    @classmethod
    def _create_invoice(cls, partner, amount, post=True):
        invoice = cls.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': partner.id,
            'invoice_date': fields.Date.today(),
            'invoice_line_ids': [Command.create({
                'name': 'Alquiler mensual de equipos',
                'quantity': 1,
                'price_unit': amount,
                'tax_ids': [Command.clear()],
            })],
        })
        if post:
            invoice.action_post()
        return invoice

    @classmethod
    def _create_remittance(cls, **vals):
        return cls.env['sepa.remittance'].create({
            'requested_collection_date': date(2026, 11, 5),
            'creditor_name': 'Alquileres Test S.L.',
            'creditor_identifier': cls.company.sepa_creditor_identifier,
            'creditor_iban': cls.creditor_iban,
            'creditor_bic': 'CAIXESBBXXX',
            **vals,
        })
