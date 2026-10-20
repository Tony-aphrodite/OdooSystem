from . import models
from . import wizard


def _post_init_generate_demo(env):
    """Generate 250 demo customers when the module is installed with demo data."""
    module = env['ir.module.module'].search([('name', '=', 'alquiler_equipos')])
    if not module.demo:
        return
    from .data.demo_generator import generate_demo_customers
    generate_demo_customers(env)
