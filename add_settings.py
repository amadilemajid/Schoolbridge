import re

with open('config/settings.py', 'r', encoding='utf-8') as f:
    content = f.read()

momo_settings = '''
# MTN MoMo Sandbox (US-026)
MTN_MOMO_SUBSCRIPTION_KEY = env('MTN_MOMO_SUBSCRIPTION_KEY', default='')
MTN_MOMO_API_USER = env('MTN_MOMO_API_USER', default='')
MTN_MOMO_API_KEY = env('MTN_MOMO_API_KEY', default='')
MTN_MOMO_ENVIRONMENT = env('MTN_MOMO_ENVIRONMENT', default='sandbox')
MTN_MOMO_BASE_URL = env('MTN_MOMO_BASE_URL', default='https://sandbox.momodeveloper.mtn.com')
'''

# Add before the last line
content = content.rstrip() + '\n' + momo_settings

with open('config/settings.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Done')
