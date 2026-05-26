import os

# Fix payments/services.py
with open('payments/services.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace('models.F(', 'F(')
content = content.replace('models.Sum(', 'Sum(')
content = content.replace('models.Count(', 'Count(')

if 'from django.db.models import F' not in content:
    content = content.replace(
        'from django.db import models',
        'from django.db import models\nfrom django.db.models import F, Sum, Count, Q, Case, When, Value, CharField, ExpressionWrapper, DecimalField'
    )

with open('payments/services.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("payments/services.py fixed")

# Fix payments/views.py - replace perform_create method
with open('payments/views.py', 'r', encoding='utf-8') as f:
    content = f.read()

old = """    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = self.perform_create(serializer)
        return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)"""

new = """    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            payment = self.perform_create(serializer)
            if payment:
                return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)
            return Response({'error': 'Payment creation failed.'}, status=400)
        except Exception as e:
            import logging
            logging.getLogger('payments').exception(f"Payment create error: {e}")
            return Response({'error': str(e)}, status=400)"""

content = content.replace(old, new)
with open('payments/views.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("payments/views.py fixed")

# Fix attendance/services.py encoding issue
try:
    with open('attendance/services.py', 'r', encoding='utf-8') as f:
        content = f.read()
    content = content.replace('models.F(', 'F(')
    if 'from django.db.models import F' not in content:
        content = content.replace(
            'from django.db import models',
            'from django.db import models\nfrom django.db.models import F, Count, Q'
        )
    with open('attendance/services.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("attendance/services.py fixed")
except Exception as e:
    print(f"attendance/services.py: {e}")

# Fix results/services.py
try:
    with open('results/services.py', 'r', encoding='utf-8') as f:
        content = f.read()
    content = content.replace('models.F(', 'F(')
    if 'from django.db.models import F' not in content:
        content = content.replace(
            'from django.db import models',
            'from django.db import models\nfrom django.db.models import F, Sum, Count, Q'
        )
    with open('results/services.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("results/services.py fixed")
except Exception as e:
    print(f"results/services.py: {e}")

print("\nAll fixes applied!")
