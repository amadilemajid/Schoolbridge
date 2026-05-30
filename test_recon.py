import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from payments.services import MoMoService
from payments.models import MoMoIPNLog, ReconciliationQueue
from schools.models import School
from decimal import Decimal
school = School.objects.first()
ipn_log = MoMoIPNLog.objects.create(school=school, provider='mtn', momo_reference='TEST-RECON-003', phone='256799999999', amount=Decimal('250000'), raw_payload={'test': True}, signature_valid=True)
payment, status = MoMoService._match_and_record(school, ipn_log, '256799999999', Decimal('250000'), 'mtn_momo')
print('Status:', status)
print('Queue count:', ReconciliationQueue.objects.count())
recon = ReconciliationQueue.objects.last()
if recon:
    print('Phone:', recon.phone, 'Amount:', recon.amount, 'Status:', recon.status)