"""
Utility to remove all demo test data and prepare for real customer import.

Run from Odoo shell:
    from odoo.addons.alquiler_equipos.data.demo_cleanup import cleanup_demo_data
    cleanup_demo_data(env)

Or from the Odoo developer console:
    self.env['res.partner'].search([('ref', 'like', 'DEMO-CLI-')]).unlink()
"""
import logging

_logger = logging.getLogger(__name__)


def cleanup_demo_data(env):
    """Remove all demo customers, mandates, and recurring invoices."""
    _logger.info('=== Removing demo data for Alquiler Equipos ===')

    # Find demo partners
    demo_partners = env['res.partner'].search([
        ('ref', 'like', 'DEMO-CLI-'),
    ])

    if not demo_partners:
        _logger.info('No demo data found.')
        return

    partner_ids = demo_partners.ids

    # Remove recurring invoices linked to demo partners
    recurring = env['recurring.invoice'].search([
        ('partner_id', 'in', partner_ids),
    ])
    if recurring:
        _logger.info('Removing %d recurring invoices...', len(recurring))
        recurring.unlink()

    # Remove SEPA mandates linked to demo partners
    mandates = env['sepa.mandate'].search([
        ('partner_id', 'in', partner_ids),
    ])
    if mandates:
        _logger.info('Removing %d SEPA mandates...', len(mandates))
        mandates.unlink()

    # Remove bank accounts linked to demo partners
    banks = env['res.partner.bank'].search([
        ('partner_id', 'in', partner_ids),
    ])
    if banks:
        _logger.info('Removing %d bank accounts...', len(banks))
        banks.unlink()

    # Remove demo partners
    _logger.info('Removing %d demo partners...', len(demo_partners))
    demo_partners.unlink()

    _logger.info('=== Demo data removed successfully ===')
    _logger.info('You can now import real customer data.')
