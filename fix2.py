import sys
c = open('config/settings.py', encoding='utf-8').read()
if 'django_celery_results' not in c:
    c = c.replace(chr(39)+'django_celery_beat'+chr(39)+',', chr(39)+'django_celery_beat'+chr(39)+',\n    '+chr(39)+'django_celery_results'+chr(39)+',')
    open('config/settings.py', 'w', encoding='utf-8').write(c)
    print('fixed')
else:
    print('already there')
