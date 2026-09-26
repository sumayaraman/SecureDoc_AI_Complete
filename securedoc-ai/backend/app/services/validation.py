from decimal import Decimal

def validate_invoice(
    items: list[dict],
    subtotal: Decimal,
    discount: Decimal,
    tax: Decimal,
    total: Decimal,
    shipping: Decimal = Decimal('0')
) -> dict:
    if items:
        calculated = sum(
            Decimal(str(i.get('total', 0))) if float(i.get('total', 0) or 0) > 0
            else Decimal(str(i.get('quantity', 0))) * Decimal(str(i.get('unit_price', 0)))
            for i in items
        )
    else:
        calculated = Decimal('0')

    base = calculated if calculated > Decimal('0') else subtotal
    expected = base - discount + tax + shipping
    difference = expected - total
    # Allow 0.05 tolerance for rounding across multi-line tax percentages
    is_valid = abs(difference) <= Decimal('0.05')

    message = 'Validated successfully' if is_valid else 'Invoice totals could not be fully validated (calculation mismatch requires review)'
    return {
        'items_subtotal': str(calculated),
        'expected_total': str(expected),
        'difference': str(difference),
        'valid': is_valid,
        'message': message
    }
