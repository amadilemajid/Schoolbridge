import re
import uuid
from rest_framework.exceptions import ValidationError

def validate_uuid(value, field_name="ID"):
    if not value:
        return None
    try:
        return uuid.UUID(str(value))
    except ValueError:
        raise ValidationError({field_name: f"Must be a valid UUID. Got: '{value}'"})

def validate_int(value, field_name="ID"):
    if not value:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValidationError({field_name: f"Must be a valid integer. Got: '{value}'"})

def normalise_uganda_phone(phone: str) -> str:
    """
    Normalises any Ugandan phone number to E.164 standard +256XXXXXXXXX (13 characters).
    Accepts 07XXXXXXXX (10 digits), 03XXXXXXXX, 02XXXXXXXX, +256XXXXXXXXX, or 256XXXXXXXXX.
    """
    if not phone:
        return ""
    clean = re.sub(r'[^\d+]', '', str(phone).strip())
    if clean.startswith('+256'):
        digits = '0' + clean[4:]
    elif clean.startswith('256'):
        digits = '0' + clean[3:]
    elif len(clean) == 9 and clean[0] in '237':
        digits = '0' + clean
    else:
        digits = clean

    if digits.startswith('0') and len(digits) == 10:
        return '+256' + digits[1:]
    return clean

def validate_uganda_phone(phone: str, field_name="phone") -> str:
    """
    Validates that a phone number is a valid 10-digit Uganda phone number
    (or +256 followed by 9 digits). Returns the normalised E.164 string (+256XXXXXXXXX).
    """
    if not phone or not str(phone).strip():
        raise ValidationError({field_name: "Phone number is required."})

    clean = re.sub(r'[^\d+]', '', str(phone).strip())
    if clean.startswith('+256'):
        digits = '0' + clean[4:]
    elif clean.startswith('256'):
        digits = '0' + clean[3:]
    elif len(clean) == 9 and clean[0] in '237':
        digits = '0' + clean
    else:
        digits = clean

    if not digits.isdigit():
        raise ValidationError({field_name: "Phone number must contain only digits."})

    if len(digits) != 10:
        raise ValidationError({
            field_name: f"Ugandan phone numbers must be 10 digits (e.g. 0771234567 or +256771234567). Got {len(digits)} digits."
        })

    # Validate valid Uganda carrier prefixes (MTN: 077/078/076/03X, Airtel: 070/075/074/020)
    if not re.match(r'^0(7[0-9]|3[129]|20)\d{7}$', digits):
        raise ValidationError({
            field_name: "Invalid Uganda network prefix. Must start with 07X (MTN/Airtel), 03X (MTN Fixed), or 020 (Airtel Fixed)."
        })

    return '+256' + digits[1:]


