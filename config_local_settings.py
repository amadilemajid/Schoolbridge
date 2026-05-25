"""
config/local_settings.py — Local development overrides.
This file is NEVER committed to git (.gitignore covers it).
Import it at the bottom of settings.py during development:

    try:
        from config.local_settings import *
    except ImportError:
        pass
"""
DEBUG = True

# Use SQLite for ultra-fast local testing (optional)
# Uncomment if you don't have PostgreSQL running yet:
# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.sqlite3',
#         'NAME': BASE_DIR / 'db.sqlite3',
#     }
# }

# Show emails in console instead of sending
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Disable HTTPS requirements locally
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# Django Debug Toolbar (install separately: pip install django-debug-toolbar)
# INSTALLED_APPS += ['debug_toolbar']
# MIDDLEWARE = ['debug_toolbar.middleware.DebugToolbarMiddleware'] + MIDDLEWARE
# INTERNAL_IPS = ['127.0.0.1']

# Faster password hashing in tests
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.MD5PasswordHasher',  # DEV ONLY — never use in production
]

# Celery runs synchronously in tests (no worker needed)
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Logging — show everything in dev
LOGGING['loggers']['schoolbridge']['level'] = 'DEBUG'
LOGGING['loggers']['payments']['level'] = 'DEBUG'
LOGGING['loggers']['messaging']['level'] = 'DEBUG'
