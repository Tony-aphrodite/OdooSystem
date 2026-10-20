"""Checks for the identifiers written to the pain.008 file.

Banks reject the whole file when one of them is wrong, so the module
checks them before the file is generated.
"""
import re

from odoo.exceptions import ValidationError

from odoo.addons.base_iban.models.res_partner_bank import validate_iban

# Pattern of BICIdentifier in the pain.008.001.02 schema
BIC_PATTERN = re.compile(r'[A-Z]{6}[A-Z2-9][A-NP-Z0-9]([A-Z0-9]{3})?')
CREDITOR_IDENTIFIER_PATTERN = re.compile(r'[A-Z]{2}[0-9]{2}[A-Z0-9]{3}[A-Z0-9]{1,28}')


def is_valid_iban(iban):
    try:
        validate_iban(iban)
    except ValidationError:
        return False
    return True


def is_valid_bic(bic):
    return bool(bic and BIC_PATTERN.fullmatch(bic))


def is_valid_creditor_identifier(identifier):
    """Check a SEPA creditor identifier (AT-02), for example ES97000B12345678.

    It is the country code, two check digits, a three-character creditor
    business code and the national identifier (the NIF in Spain). The
    check digits are ISO 7064 MOD 97-10 over the national identifier
    followed by the country code; the business code is not part of it.
    """
    if not identifier or not CREDITOR_IDENTIFIER_PATTERN.fullmatch(identifier):
        return False
    digits = ''.join(str(int(char, 36)) for char in identifier[7:] + identifier[:4])
    return int(digits) % 97 == 1
