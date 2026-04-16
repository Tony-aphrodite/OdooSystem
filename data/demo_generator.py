"""
Generate 250 test customers with SEPA mandates and recurring invoices.

This script runs as a post_init_hook when the module is installed.
All test data can be identified by the 'demo_alquiler' tag in the
partner ref field, making it easy to remove and replace with real data.

To remove all test data, run:
    self.env['res.partner'].search([('ref', 'like', 'DEMO-CLI-')]).unlink()
"""
import logging
import random
from datetime import date, timedelta

_logger = logging.getLogger(__name__)

# --- Spanish test data pools ---
FIRST_NAMES = [
    'Antonio', 'Manuel', 'José', 'Francisco', 'David', 'Juan', 'Carlos',
    'Jesús', 'Javier', 'Daniel', 'Miguel', 'Rafael', 'Pedro', 'Ángel',
    'Alejandro', 'Fernando', 'Pablo', 'Luis', 'Sergio', 'Alberto',
    'María', 'Carmen', 'Ana', 'Isabel', 'Laura', 'Cristina', 'Marta',
    'Rosa', 'Pilar', 'Elena', 'Lucía', 'Sara', 'Paula', 'Raquel',
    'Andrea', 'Beatriz', 'Silvia', 'Rocío', 'Sonia', 'Patricia',
]

LAST_NAMES = [
    'García', 'Martínez', 'López', 'Sánchez', 'González', 'Rodríguez',
    'Fernández', 'Pérez', 'Gómez', 'Díaz', 'Hernández', 'Álvarez',
    'Moreno', 'Muñoz', 'Jiménez', 'Ruiz', 'Domínguez', 'Alonso',
    'Romero', 'Navarro', 'Torres', 'Gutiérrez', 'Gil', 'Vázquez',
    'Serrano', 'Ramos', 'Blanco', 'Molina', 'Suárez', 'Castro',
    'Ortega', 'Delgado', 'Marín', 'Rubio', 'Núñez', 'Medina',
    'Iglesias', 'Castillo', 'Cortés', 'Guerrero', 'Santos', 'Lozano',
    'Cano', 'Herrera', 'Peña', 'Flores', 'Cabrera', 'Campos',
]

COMPANY_TYPES = [
    'Bar', 'Restaurante', 'Cafetería', 'Hotel', 'Hostal', 'Clínica',
    'Peluquería', 'Taller', 'Farmacia', 'Gimnasio', 'Panadería',
    'Carnicería', 'Frutería', 'Ferretería', 'Floristería', 'Óptica',
    'Lavandería', 'Gestoría', 'Inmobiliaria', 'Dentista',
]

COMPANY_SUFFIXES = ['S.L.', 'S.A.', 'S.C.', 'C.B.']

STREETS = [
    'Calle Mayor', 'Calle Real', 'Avenida de la Constitución',
    'Calle San Juan', 'Calle del Sol', 'Calle de la Cruz',
    'Avenida de España', 'Calle Nueva', 'Paseo de la Estación',
    'Calle del Carmen', 'Calle de la Iglesia', 'Calle del Río',
    'Avenida de Madrid', 'Calle San Pedro', 'Calle del Agua',
    'Calle Cervantes', 'Plaza Mayor', 'Calle de la Fuente',
    'Calle del Pilar', 'Avenida de Castilla',
]

CITIES_WITH_ZIP = [
    ('Cuenca', '16001'), ('Cuenca', '16002'), ('Cuenca', '16003'),
    ('Tarancón', '16400'), ('Motilla del Palancar', '16200'),
    ('San Clemente', '16600'), ('Las Pedroñeras', '16660'),
    ('Quintanar del Rey', '16220'), ('Minglanilla', '16260'),
    ('Iniesta', '16235'), ('Casasimarro', '16230'),
    ('Villanueva de la Jara', '16640'), ('Sisante', '16250'),
    ('Ledaña', '16240'), ('Honrubia', '16611'),
    ('Albacete', '02001'), ('Albacete', '02002'),
    ('Toledo', '45001'), ('Ciudad Real', '13001'),
    ('Guadalajara', '19001'), ('Valencia', '46001'),
    ('Madrid', '28001'), ('Madrid', '28002'), ('Madrid', '28003'),
]

# Spanish bank codes for generating fake IBANs
BANK_CODES = [
    '0049',  # Santander
    '0081',  # Sabadell
    '0182',  # BBVA
    '3058',  # Cajamar
    '2100',  # CaixaBank
    '0128',  # Bankinter
    '0487',  # Caja Rural
]


def _generate_fake_iban(bank_code=None):
    """Generate a fake but structurally valid-looking Spanish IBAN."""
    if not bank_code:
        bank_code = random.choice(BANK_CODES)
    branch = '%04d' % random.randint(1, 9999)
    control = '%02d' % random.randint(0, 99)
    account = '%010d' % random.randint(1, 9999999999)
    # Fake check digits (real IBAN validation not needed for demo)
    check = '%02d' % random.randint(10, 99)
    return 'ES%s %s %s %s %s' % (
        check, bank_code, branch, control, account,
    )


def _generate_fake_cif():
    """Generate a fake Spanish CIF."""
    letter = random.choice('ABCDEFGHJ')
    number = '%07d' % random.randint(1, 9999999)
    control = random.choice('0123456789ABCDEFGHIJ')
    return '%s%s%s' % (letter, number, control)


def _generate_fake_phone():
    """Generate a fake Spanish phone number."""
    prefix = random.choice(['6', '7', '9'])
    return '+34 %s%s %s %s' % (
        prefix,
        '%02d' % random.randint(10, 99),
        '%03d' % random.randint(100, 999),
        '%03d' % random.randint(100, 999),
    )


def generate_demo_customers(env):
    """Generate 250 demo customers with mandates and recurring invoices.

    Called from post_init_hook.
    """
    _logger.info('=== Generating 250 demo customers for Alquiler Equipos ===')

    Partner = env['res.partner']
    PartnerBank = env['res.partner.bank']
    Mandate = env['sepa.mandate']
    Recurring = env['recurring.invoice']

    spain = env.ref('base.es')
    cuenca_state = env.ref('base.state_es_cu', raise_if_not_found=False)
    company = env.company
    mandate_counter = 1

    # Mix of individual persons and businesses
    for i in range(1, 251):
        # 60% businesses, 40% individuals
        is_company = random.random() < 0.6

        if is_company:
            btype = random.choice(COMPANY_TYPES)
            last = random.choice(LAST_NAMES)
            name = '%s %s %s' % (btype, last, random.choice(COMPANY_SUFFIXES))
            company_type = 'company'
            vat = 'ES%s' % _generate_fake_cif()
        else:
            first = random.choice(FIRST_NAMES)
            last1 = random.choice(LAST_NAMES)
            last2 = random.choice(LAST_NAMES)
            name = '%s %s %s' % (first, last1, last2)
            company_type = 'person'
            vat = False

        city, zipcode = random.choice(CITIES_WITH_ZIP)
        street_name = random.choice(STREETS)
        street_num = random.randint(1, 120)

        # Rental amount between 15 and 180 EUR
        rental_amount = round(random.uniform(15.0, 180.0), 2)

        # Collection day: 1-28
        collection_day = random.choice([1, 5, 10, 15, 20, 25])

        # Invoice generation day: typically a few days before collection
        invoice_day = max(1, collection_day - random.randint(3, 7))

        # Rental start date: between 1 and 5 years ago
        days_ago = random.randint(365, 365 * 5)
        start_date = date.today() - timedelta(days=days_ago)

        # Create partner
        partner = Partner.create({
            'name': name,
            'company_type': company_type,
            'ref': 'DEMO-CLI-%04d' % i,
            'vat': vat,
            'street': '%s, %d' % (street_name, street_num),
            'city': city,
            'zip': zipcode,
            'state_id': cuenca_state.id if cuenca_state else False,
            'country_id': spain.id,
            'phone': _generate_fake_phone(),
            'email': 'cliente%04d@example.com' % i,
            'tz': 'Europe/Madrid',
            'customer_rank': 1,
            'is_rental_customer': True,
            'rental_active': True,
            'rental_monthly_amount': rental_amount,
            'rental_concept': 'Alquiler mensual de equipos - %s' % name,
            'rental_day_of_month': invoice_day,
            'rental_collection_day': collection_day,
            'rental_start_date': start_date,
        })

        # Create bank account
        iban = _generate_fake_iban()
        bank_account = PartnerBank.create({
            'acc_number': iban,
            'partner_id': partner.id,
        })

        # Create SEPA mandate (active)
        mandate_ref = 'APV-%04d-%04d' % (start_date.year, mandate_counter)
        mandate_counter += 1

        mandate = Mandate.create({
            'unique_mandate_reference': mandate_ref,
            'partner_id': partner.id,
            'partner_bank_id': bank_account.id,
            'signature_date': start_date,
            'state': 'active',
            'scheme': 'CORE',
            'sequence_type': 'RCUR',
            'creditor_identifier': 'ES91000B16612525',
            'company_id': company.id,
        })

        # Create recurring invoice subscription (active)
        next_invoice = date.today().replace(day=invoice_day)
        if next_invoice < date.today():
            month = next_invoice.month + 1
            year = next_invoice.year
            if month > 12:
                month = 1
                year += 1
            next_invoice = date(year, month, invoice_day)

        Recurring.create({
            'partner_id': partner.id,
            'product_description': 'Alquiler mensual de equipos',
            'amount': rental_amount,
            'interval': 'monthly',
            'day_of_month': invoice_day,
            'next_invoice_date': next_invoice,
            'start_date': start_date,
            'state': 'active',
            'mandate_id': mandate.id,
            'company_id': company.id,
        })

        if i % 50 == 0:
            _logger.info('... %d/250 clientes demo creados', i)

    _logger.info('=== 250 demo customers created successfully ===')
