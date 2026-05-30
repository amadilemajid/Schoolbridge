import re

with open('messaging/services.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix class-level TOKEN to be a property loaded dynamically
old = '    TOKEN = settings.WHATSAPP_ACCESS_TOKEN'
new = '    TOKEN = None  # Loaded dynamically per request'

content = content.replace(old, new)

# Fix send_text_message to load token dynamically
old2 = "                'Authorization': f'Bearer {cls.TOKEN}',"
new2 = "                'Authorization': f'Bearer {settings.WHATSAPP_ACCESS_TOKEN}',"

content = content.replace(old2, new2)

with open('messaging/services.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Done')
