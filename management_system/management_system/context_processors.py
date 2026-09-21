from django.conf import settings


def branding(request):
    return {
        'brand_name': 'Nzeru Digital',
        'brand_product': 'ERP',
        'currency_code': getattr(settings, 'CURRENCY_CODE', 'MWK'),
        'currency_symbol': getattr(settings, 'CURRENCY_SYMBOL', 'MK'),
        'currency_name': getattr(settings, 'CURRENCY_NAME', 'Malawian Kwacha'),
    }