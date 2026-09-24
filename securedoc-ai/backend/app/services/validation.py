from decimal import Decimal

def validate_invoice(items:list[dict], subtotal:Decimal, discount:Decimal, tax:Decimal, total:Decimal)->dict:
    calculated=sum(Decimal(str(i.get('quantity',0)))*Decimal(str(i.get('unit_price',0))) for i in items)
    base=calculated if calculated else subtotal
    expected=base-discount+tax
    difference=expected-total
    return {'items_subtotal':str(calculated),'expected_total':str(expected),'difference':str(difference),'valid':abs(difference)<=Decimal('0.01')}
