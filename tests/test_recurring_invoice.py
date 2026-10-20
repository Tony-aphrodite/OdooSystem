from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import AlquilerTestCommon


@tagged('post_install', '-at_install')
class TestRecurringInvoice(AlquilerTestCommon):

    def setUp(self):
        super().setUp()
        # Keep the scheduled action away from subscriptions that already exist
        # in the database (for example the demo data).
        self.env['recurring.invoice'].sudo().search([('state', '=', 'active')]).write({'state': 'paused'})
        self.today = fields.Date.today()

    def _create_subscription(self, **vals):
        return self.env['recurring.invoice'].create({
            'partner_id': self.debtor_a.id,
            'mandate_id': self.mandate_a.id,
            'product_description': 'Alquiler mensual de equipos',
            'amount': 99.0,
            'next_invoice_date': self.today,
            **vals,
        })

    def test_activate_requires_amount(self):
        subscription = self._create_subscription(amount=0.0)
        with self.assertRaises(UserError):
            subscription.action_activate()
        self.assertEqual(subscription.state, 'draft')

    def test_cron_creates_invoice_and_moves_next_date(self):
        monthly = self._create_subscription()
        quarterly = self._create_subscription(interval='quarterly', amount=250.0)
        yearly = self._create_subscription(
            interval='yearly', partner_id=self.debtor_b.id, mandate_id=self.mandate_b.id,
        )
        (monthly + quarterly + yearly).action_activate()

        self.env['recurring.invoice']._cron_generate_recurring_invoices()

        invoice = monthly.invoice_ids
        self.assertEqual(len(invoice), 1)
        self.assertEqual(monthly.invoice_count, 1)
        self.assertEqual(invoice.move_type, 'out_invoice')
        self.assertEqual(invoice.state, 'draft')
        self.assertEqual(invoice.partner_id, self.debtor_a)
        self.assertEqual(invoice.invoice_date, self.today)
        self.assertEqual(invoice.invoice_line_ids.name, 'Alquiler mensual de equipos')
        self.assertEqual(invoice.invoice_line_ids.price_unit, 99.0)
        self.assertEqual(quarterly.invoice_ids.invoice_line_ids.price_unit, 250.0)
        self.assertEqual(yearly.invoice_ids.partner_id, self.debtor_b)

        self.assertEqual(monthly.next_invoice_date, self.today + relativedelta(months=1))
        self.assertEqual(quarterly.next_invoice_date, self.today + relativedelta(months=3))
        self.assertEqual(yearly.next_invoice_date, self.today + relativedelta(years=1))

        # The next run on the same day finds nothing due
        self.env['recurring.invoice']._cron_generate_recurring_invoices()
        self.assertEqual(monthly.invoice_count, 1)

    def test_cron_skips_inactive_future_and_ended(self):
        draft = self._create_subscription()
        paused = self._create_subscription()
        paused.action_activate()
        paused.action_pause()
        future = self._create_subscription(next_invoice_date=self.today + timedelta(days=1))
        ended = self._create_subscription(end_date=self.today - timedelta(days=1))
        (future + ended).action_activate()

        self.env['recurring.invoice']._cron_generate_recurring_invoices()

        for subscription in draft + paused + future + ended:
            self.assertFalse(subscription.invoice_ids, subscription.name)
        self.assertEqual(future.next_invoice_date, self.today + timedelta(days=1))
