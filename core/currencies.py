"""Currency presets for the store-wide currency configuration.

Every entry provides the defaults that apply when that currency is selected in
Settings. All of those defaults (symbol, position, decimals and separators) can
be overridden per store on the Settings page.
"""

DEFAULT_CURRENCY = 'TZS'
CUSTOM_CURRENCY = 'CUSTOM'

CURRENCIES = {
    'TZS': {
        'name': 'Tanzanian Shilling (TZS)',
        'symbol': 'TZS',
        'decimals': 0,
        'position': 'before',
        'thousands': 'comma',
        'decimal': 'dot',
    },
    'USD': {
        'name': 'US Dollar (USD)',
        'symbol': '$',
        'decimals': 2,
        'position': 'before',
        'thousands': 'comma',
        'decimal': 'dot',
    },
    'EUR': {
        'name': 'Euro (EUR)',
        'symbol': '€',
        'decimals': 2,
        'position': 'before',
        'thousands': 'comma',
        'decimal': 'dot',
    },
    'GBP': {
        'name': 'British Pound (GBP)',
        'symbol': '£',
        'decimals': 2,
        'position': 'before',
        'thousands': 'comma',
        'decimal': 'dot',
    },
    'KES': {
        'name': 'Kenyan Shilling (KES)',
        'symbol': 'KSh',
        'decimals': 2,
        'position': 'before',
        'thousands': 'comma',
        'decimal': 'dot',
    },
    'UGX': {
        'name': 'Ugandan Shilling (UGX)',
        'symbol': 'UGX',
        'decimals': 0,
        'position': 'before',
        'thousands': 'comma',
        'decimal': 'dot',
    },
    'NGN': {
        'name': 'Nigerian Naira (NGN)',
        'symbol': '₦',
        'decimals': 2,
        'position': 'before',
        'thousands': 'comma',
        'decimal': 'dot',
    },
    'ZAR': {
        'name': 'South African Rand (ZAR)',
        'symbol': 'R',
        'decimals': 2,
        'position': 'before',
        'thousands': 'comma',
        'decimal': 'dot',
    },
    'INR': {
        'name': 'Indian Rupee (INR)',
        'symbol': '₹',
        'decimals': 2,
        'position': 'before',
        'thousands': 'comma',
        'decimal': 'dot',
    },
    'JPY': {
        'name': 'Japanese Yen (JPY)',
        'symbol': '¥',
        'decimals': 0,
        'position': 'before',
        'thousands': 'comma',
        'decimal': 'dot',
    },
    'CNY': {
        'name': 'Chinese Yuan (CNY)',
        'symbol': '¥',
        'decimals': 2,
        'position': 'before',
        'thousands': 'comma',
        'decimal': 'dot',
    },
    CUSTOM_CURRENCY: {
        'name': 'Custom — set your own symbol',
        'symbol': '',
        'decimals': 2,
        'position': 'before',
        'thousands': 'comma',
        'decimal': 'dot',
    },
}

CURRENCY_CHOICES = [(code, config['name']) for code, config in CURRENCIES.items()]

# Stored sentinels — 'auto' means "use the selected currency's default".
AUTO = 'auto'

SYMBOL_POSITION_CHOICES = [
    (AUTO, 'Automatic'),
    ('before', 'Before the amount  (e.g. $1,234.56)'),
    ('after', 'After the amount  (e.g. 1,234.56 $)'),
]

DECIMAL_PLACES_CHOICES = [
    (AUTO, 'Automatic (as per currency)'),
    ('0', '0 decimals  (1,234)'),
    ('1', '1 decimal   (1,234.5)'),
    ('2', '2 decimals  (1,234.56)'),
    ('3', '3 decimals  (1,234.567)'),
    ('4', '4 decimals  (1,234.5678)'),
]

THOUSANDS_SEPARATOR_CHOICES = [
    (AUTO, 'Automatic (as per currency)'),
    ('comma', 'Comma  — 1,000,000'),
    ('dot', 'Dot  — 1.000.000'),
    ('space', 'Space  — 1 000 000'),
    ('none', 'None  — 1000000'),
]

DECIMAL_SEPARATOR_CHOICES = [
    (AUTO, 'Automatic (as per currency)'),
    ('dot', 'Dot  — 1,000.00'),
    ('comma', 'Comma  — 1.000,00'),
]

# Characters used once the sentinels above are resolved.
SEPARATOR_CHARS = {
    'comma': ',',
    'dot': '.',
    'space': ' ',
    'none': '',
}


def currency_config(code):
    """Return the preset for `code`, falling back to the default currency."""
    return CURRENCIES.get(code) or CURRENCIES[DEFAULT_CURRENCY]
