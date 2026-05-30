with open('payments/services.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace(
    '''            ).annotate(
                  balance=ExpressionWrapper(
                      F('total_amount') - F('amount_paid') - F('amount_waived'),
                      output_field=DecimalField()
                  )
              ).filter(balance__gt=0)''',
    '''            ).annotate(
                  outstanding_balance=ExpressionWrapper(
                      F('total_amount') - F('amount_paid') - F('amount_waived'),
                      output_field=DecimalField()
                  )
              ).filter(outstanding_balance__gt=0)'''
)

with open('payments/services.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Fixed')
