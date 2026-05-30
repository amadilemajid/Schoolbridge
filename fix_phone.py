from django.db import connection
from students.models import Guardian

with connection.cursor() as cursor:
    cursor.execute("UPDATE guardians SET phone_normalised = '256708826558' WHERE phone_normalised = '+256701111002'")
    print('Rows updated:', cursor.rowcount)

g = Guardian.objects.filter(phone_normalised='256708826558').first()
print('Found:', g)
print('Student:', g.student.get_full_name() if g else None)
