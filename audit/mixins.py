"""
AuditMixin — DRY helper for views that need to emit audit log entries.
"""
from .models import AuditLog


class AuditMixin:
    def log_action(self, action, target=None, extra=None, before=None, after=None, category=None):
        request = self.request
        user = request.user if request.user.is_authenticated else None
        school = getattr(request, 'school', None) or (user.school if user and hasattr(user, 'school') else None)
        # Derive category from action prefix
        if category is None:
            prefix_map = {
                'PAYMENT': 'PAYMENT', 'FEE': 'FEE', 'STUDENT': 'STUDENT',
                'ATTENDANCE': 'ATTENDANCE', 'RESULT': 'RESULT', 'MARK': 'RESULT',
                'MESSAGING': 'MESSAGING', 'SCHOOL': 'SCHOOL', 'STAFF': 'STAFF',
                'TERM': 'SCHOOL', 'MOMO': 'PAYMENT', 'WAIVER': 'FEE',
                'HOLIDAY': 'SCHOOL', 'ACADEMIC': 'SCHOOL', 'ROLE': 'STAFF',
                'LOGIN': 'AUTH', 'LOGOUT': 'AUTH', 'PASSWORD': 'AUTH',
            }
            category = next((v for k, v in prefix_map.items() if action.startswith(k)), 'SYSTEM')

        AuditLog.log(
            actor=user,
            school=school,
            category=category,
            action=action,
            target=target,
            before=before,
            after=after,
            extra=extra,
            request=request,
        )

    def log_auth_event(self, action, user, request):
        AuditLog.log(
            actor=user,
            school=getattr(user, 'school', None),
            category='AUTH',
            action=action,
            request=request,
        )
