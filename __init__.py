from . import models
from . import wizard


def _post_init_generate_demo(env):
    """Generate 250 demo customers after module installation."""
    from .data.demo_generator import generate_demo_customers
    generate_demo_customers(env)
