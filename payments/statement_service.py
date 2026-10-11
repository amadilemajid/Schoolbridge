"""
US-030: Bank Statement & MoMo CSV Reconciliation Import Service.
Supports Centenary Bank Uganda, Stanbic Bank Uganda, MTN MoMo, and Airtel Money exports.
"""
import csv
import io
import re
import uuid
import hashlib
import logging
from decimal import Decimal
from datetime import datetime
from django.utils import timezone
from django.db import transaction
from payments.models import ReconciliationQueue, MoMoIPNLog, Payment
from students.models import Student, Guardian

logger = logging.getLogger('payments')


class StatementImportService:
    """
    Parses and queues transactions from bank & MoMo statement CSV exports.
    """

    FORMAT_PROFILES = {
        'centenary': {
            'name': 'Centenary Bank Uganda',
            'provider': 'centenary',
            'date_cols': ['date', 'posting date', 'value date', 'txn date'],
            'ref_cols': ['reference', 'ref no', 'txn ref', 'cheque no', 'document no', 'ref'],
            'narration_cols': ['description', 'details', 'narration', 'remarks', 'particulars'],
            'credit_cols': ['credit', 'deposit', 'credit amount'],
            'debit_cols': ['debit', 'withdrawal', 'debit amount'],
            'amount_cols': ['amount'],
            'phone_cols': ['phone', 'msisdn', 'payer'],
        },
        'stanbic': {
            'name': 'Stanbic Bank Uganda',
            'provider': 'stanbic',
            'date_cols': ['posting date', 'transaction date', 'value date', 'date'],
            'ref_cols': ['reference', 'transaction reference', 'ref', 'cheque number', 'cust ref'],
            'narration_cols': ['narrative', 'narration', 'description', 'details'],
            'credit_cols': ['credit amount', 'credit'],
            'debit_cols': ['debit amount', 'debit'],
            'amount_cols': ['amount'],
            'phone_cols': ['phone', 'msisdn', 'payer'],
        },
        'mtn_momo': {
            'name': 'MTN Mobile Money / Airtel Money',
            'provider': 'mtn_momo',
            'date_cols': ['date', 'transaction time', 'time', 'timestamp'],
            'ref_cols': ['external transaction id', 'transaction id', 'financial transaction id', 'ref id', 'id', 'reference'],
            'narration_cols': ['narrative', 'note', 'reason', 'description', 'payment reason'],
            'credit_cols': ['amount', 'gross amount', 'credit'],
            'debit_cols': [],
            'amount_cols': ['amount'],
            'phone_cols': ['from', 'payer', 'msisdn', 'phone number', 'sender', 'phone'],
        },
    }

    @classmethod
    def detect_format(cls, headers):
        """
        Auto-detect format profile based on header column names.
        Detection order: MoMo-specific first (most distinctive), then bank-specific.
        This prevents generic column names like 'narrative' from triggering a Stanbic
        false-positive on MoMo exports.
        """
        clean_headers = [h.strip().lower() for h in headers if h]

        # ── MoMo / Mobile Money (check FIRST — most distinctive headers) ──────
        # 'external transaction id' and 'financial transaction id' are unique to MoMo exports.
        # 'from' column for sender phone is also MoMo-specific.
        if any(h in (
            'external transaction id', 'financial transaction id',
            'msisdn', 'transaction id'
        ) for h in clean_headers):
            return 'mtn_momo'

        # Also treat 'from' + 'amount' combination as MoMo (Airtel Money export style)
        if 'from' in clean_headers and 'amount' in clean_headers:
            return 'mtn_momo'

        # ── Centenary Bank Uganda (check SECOND — has unique column names) ────────
        # 'particulars', 'cheque no', 'document no' are Centenary-specific.
        if any(h in ('particulars', 'cheque no', 'document no') for h in clean_headers):
            return 'centenary'

        # ── Stanbic Bank Uganda (check THIRD) ─────────────────────────────────────
        # 'posting date' + 'narrative' together are Stanbic-specific.
        # 'credit amount' is also Stanbic-specific (MoMo uses plain 'amount').
        if any(h in ('posting date', 'credit amount', 'transaction reference') for h in clean_headers):
            return 'stanbic'
        # 'narrative' alone (without MoMo-specific keys) leans Stanbic
        if 'narrative' in clean_headers:
            return 'stanbic'

        return 'auto'

    @classmethod
    def _parse_amount(cls, val):
        if val is None:
            return None
        val_str = str(val).strip()
        # Accounting negative: (50000) or -50000
        is_negative = val_str.startswith('-') or (val_str.startswith('(') and val_str.endswith(')'))
        cleaned = re.sub(r'[^\d.]', '', val_str)
        if not cleaned:
            return None
        try:
            amt = Decimal(cleaned)
            if is_negative:
                return None  # Negative amounts are debits/charges, not incoming deposits
            return amt if amt > 0 else None
        except Exception:
            return None

    @classmethod
    def _parse_date(cls, date_str):
        if not date_str:
            return timezone.now()
        date_str = str(date_str).strip()
        formats = [
            '%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M', '%d/%m/%Y',
            '%d/%m/%Y %I:%M:%S %p', '%d/%m/%Y %I:%M %p',
            '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d',
            '%d-%m-%Y', '%d-%b-%Y', '%d-%b-%y', '%Y/%m/%d',
            '%m/%d/%Y', '%m/%d/%Y %H:%M:%S',
        ]
        for fmt in formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                if timezone.is_naive(dt):
                    return timezone.make_aware(dt, timezone.get_current_timezone())
                return dt
            except ValueError:
                pass
        return timezone.now()

    @classmethod
    def _find_column(cls, row_keys, candidates):
        row_keys_map = {k.strip().lower(): k for k in row_keys if k}
        for cand in candidates:
            if cand in row_keys_map:
                return row_keys_map[cand]
        return None

    @classmethod
    def _find_suggested_students(cls, school, narration, phone=None):
        suggestions = []
        if not narration and not phone:
            return suggestions

        # 1. Search for student ID pattern or tokens
        matches = re.findall(r'SCH[-_\s]?\d{4}[-_\s]?\d{3,5}', narration or '', re.IGNORECASE)
        for m in matches:
            norm_code = re.sub(r'[\s_]', '-', m.upper())
            s = Student.all_objects.filter(school=school, student_id__iexact=norm_code).first()
            if s and not any(item['student_id'] == str(s.id) for item in suggestions):
                suggestions.append({
                    'student_id': str(s.id),
                    'name': s.get_full_name(),
                    'phone': getattr(s, 'primary_contact', '') or '',
                    'score': 100,
                })

        # Check alphanumeric tokens against all active students in school
        tokens = re.findall(r'[A-Za-z0-9_\-]+', narration or '')
        for tok in tokens:
            if len(tok) >= 4:
                s = Student.all_objects.filter(school=school, student_id__iexact=tok).first()
                if s and not any(item['student_id'] == str(s.id) for item in suggestions):
                    suggestions.append({
                        'student_id': str(s.id),
                        'name': s.get_full_name(),
                        'phone': getattr(s, 'primary_contact', '') or '',
                        'score': 95,
                    })

        # 2. Search for student names mentioned in narration
        words = [w.strip() for w in re.findall(r'[A-Za-z]+', narration or '') if len(w.strip()) >= 3]
        ignore_words = {'fees', 'school', 'term', 'payment', 'paid', 'bank', 'slip', 'grade',
                        'class', 'primary', 'senior', 'from', 'with', 'tuition', 'uniform'}
        candidate_words = [w for w in words if w.lower() not in ignore_words]
        from django.db.models import Q
        for w in candidate_words:
            matched_students = Student.all_objects.filter(
                school=school, is_active=True
            ).filter(
                Q(first_name__iexact=w) | Q(last_name__iexact=w)
            )[:3]
            for s in matched_students:
                if not any(item['student_id'] == str(s.id) or item['name'].strip().lower() == s.get_full_name().strip().lower() for item in suggestions):
                    # Higher score (90) if multiple words in narration match student's name
                    full = f"{s.first_name} {s.last_name}".lower()
                    other_match = any(o.lower() in full for o in candidate_words if o.lower() != w.lower())
                    score = 90 if other_match else 75
                    suggestions.append({
                        'student_id': str(s.id),
                        'name': s.get_full_name(),
                        'phone': getattr(s, 'primary_contact', '') or '',
                        'score': score,
                    })

        # 3. Match phone to guardians if phone available
        if phone and len(phone) >= 9:
            clean_phone = re.sub(r'[^\d+]', '', phone)
            guardians = Guardian.objects.filter(
                student__school=school,
                phone_normalised__icontains=clean_phone[-9:]
            ).select_related('student')[:3]
            for g in guardians:
                if not any(item['student_id'] == str(g.student.id) for item in suggestions):
                    suggestions.append({
                        'student_id': str(g.student.id),
                        'name': g.student.get_full_name(),
                        'phone': g.phone_normalised,
                        'score': 85,
                    })

        suggestions.sort(key=lambda x: x.get('score', 0), reverse=True)
        return suggestions[:3]

    @classmethod
    @transaction.atomic
    def process_csv_file(cls, *, school, file_obj, user=None, format_hint='auto'):
        """
        Process uploaded CSV file, extract deposits, and queue for reconciliation.
        """
        content = file_obj.read()
        try:
            text = content.decode('utf-8-sig')
        except UnicodeDecodeError:
            try:
                text = content.decode('latin-1')
            except UnicodeDecodeError:
                text = content.decode('cp1252', errors='replace')

        f = io.StringIO(text)
        # Check first non-empty line for delimiter (handles European/Excel semicolon exports)
        sample = text[:8192]
        delimiter = ','
        header_line_index = 0  # Track which line is the actual header

        # Scan through first 15 non-empty lines to find the real header row.
        # Some bank exports (e.g. Centenary Bank) have a title/report metadata row
        # before the actual column headers. A header row has ≥3 delimiter-separated
        # tokens containing recognisable column-name keywords.
        HEADER_KEYWORDS = {
            'date', 'amount', 'reference', 'ref', 'narration', 'particulars',
            'description', 'credit', 'debit', 'balance', 'narrative', 'from',
            'cheque', 'posting', 'value', 'transaction', 'account',
        }
        all_lines = [l for l in sample.splitlines() if l.strip()]
        for idx, line in enumerate(all_lines[:15]):
            # Sniff delimiter from this line
            if ';' in line and ',' not in line:
                candidate_delim = ';'
            elif '\t' in line and ',' not in line:
                candidate_delim = '\t'
            else:
                candidate_delim = ','
            parts = [p.strip().strip('"\'') for p in line.split(candidate_delim)]
            if len(parts) >= 3:
                lower_parts = [p.lower() for p in parts]
                has_keywords = any(
                    any(kw in p for kw in HEADER_KEYWORDS)
                    for p in lower_parts
                )
                if has_keywords:
                    delimiter = candidate_delim
                    header_line_index = idx
                    break
        else:
            # Fallback: use first non-empty line and sniff its delimiter
            for line in all_lines[:3]:
                if ';' in line and ',' not in line:
                    delimiter = ';'
                elif '\t' in line and ',' not in line:
                    delimiter = '\t'
                break

        # Skip to the header line by re-creating StringIO from the correct position
        if header_line_index > 0:
            # Find byte offset of the header line in the original text
            lines_so_far = 0
            offset = 0
            for ch in text:
                if ch == '\n':
                    lines_so_far += 1
                    if lines_so_far == header_line_index:
                        offset += 1
                        break
                offset += 1
            f = io.StringIO(text[offset:])
        else:
            f = io.StringIO(text)

        reader = csv.DictReader(f, delimiter=delimiter)
        if not reader.fieldnames:
            raise ValueError("CSV file is empty or missing headers.")

        # Strip whitespace from fieldnames
        clean_fieldnames = [fn.strip() for fn in reader.fieldnames if fn]
        reader.fieldnames = clean_fieldnames

        detected_profile_key = format_hint if format_hint in cls.FORMAT_PROFILES else cls.detect_format(reader.fieldnames)
        if detected_profile_key not in cls.FORMAT_PROFILES:
            detected_profile_key = 'centenary'  # fallback generic bank profile

        profile = cls.FORMAT_PROFILES[detected_profile_key]
        headers = reader.fieldnames

        date_col = cls._find_column(headers, profile['date_cols'])
        ref_col = cls._find_column(headers, profile['ref_cols'])
        narr_col = cls._find_column(headers, profile['narration_cols'])
        credit_col = cls._find_column(headers, profile['credit_cols'])
        debit_col = cls._find_column(headers, profile['debit_cols'])
        amount_col = cls._find_column(headers, profile['amount_cols'])
        phone_col = cls._find_column(headers, profile['phone_cols'])

        imported = 0
        skipped = 0
        total_rows = 0

        for row in reader:
            total_rows += 1
            # Check debit column - skip outgoing withdrawals
            if debit_col and row.get(debit_col):
                d_amt = cls._parse_amount(row.get(debit_col))
                c_amt = cls._parse_amount(row.get(credit_col)) if credit_col else None
                if d_amt and (not c_amt or c_amt == 0):
                    continue

            # Determine incoming amount
            amount = None
            if credit_col and row.get(credit_col):
                amount = cls._parse_amount(row.get(credit_col))
            if not amount and amount_col and row.get(amount_col):
                amount = cls._parse_amount(row.get(amount_col))

            if not amount or amount <= 0:
                continue

            narration = str(row.get(narr_col, '')).strip() if narr_col else ''
            # Also store normalised key in payload so serializer can retrieve it reliably
            # regardless of original column capitalisation.
            date_raw = row.get(date_col) if date_col else None
            parsed_date = cls._parse_date(date_raw)

            # Reference
            ref_raw = str(row.get(ref_col, '')).strip() if ref_col else ''
            if not ref_raw:
                # Generate stable ref from content
                hash_input = f"{school.id}_{date_raw}_{amount}_{narration}"
                ref_raw = f"BNK-{hashlib.md5(hash_input.encode()).hexdigest()[:12].upper()}"

            # Phone extraction — try mapped column first, then scan all row values
            phone_raw = str(row.get(phone_col, '')).strip() if phone_col else ''
            if not phone_raw:
                # Scan narration text for a Ugandan phone number (+256 or 07/03/04)
                phone_match = re.search(r'(?:\+?256|0)[347]\d{8}', narration)
                if phone_match:
                    phone_raw = phone_match.group(0)
            if not phone_raw:
                # Last-resort: scan all row values for a phone number
                for val in row.values():
                    m = re.search(r'(?:\+?256|0)[347]\d{8}', str(val))
                    if m:
                        phone_raw = m.group(0)
                        break

            clean_phone = phone_raw if phone_raw else 'N/A'

            # Idempotency check against existing payments & queue
            if MoMoIPNLog.objects.filter(school=school, momo_reference=ref_raw).exists() or \
               ReconciliationQueue.all_objects.filter(school=school, momo_reference=ref_raw).exists() or \
               Payment.all_objects.filter(school=school, momo_reference=ref_raw).exists():
                skipped += 1
                continue

            # AI / Regex suggestion matching
            suggestions = cls._find_suggested_students(school, narration, clean_phone)

            # Create MoMoIPNLog and ReconciliationQueue item
            provider = profile['provider']

            # Build a normalised payload: original row + a guaranteed 'narration' key
            # so the ReconciliationQueueSerializer.get_narration() can always find it.
            normalised_payload = {k.strip().lower().replace(' ', '_'): v for k, v in row.items()}
            normalised_payload['narration'] = narration  # guaranteed present

            # Map the profile provider to the MoMoIPNLog.provider choices ('mtn' | 'airtel').
            # The full provider detail is preserved in ReconciliationQueue.provider.
            # Bank imports (centenary, stanbic) use 'mtn' as a neutral audit sentinel.
            ipn_provider = 'mtn' if ('momo' in provider or 'mtn' in provider or provider in ('centenary', 'stanbic')) else 'airtel'

            ipn_log = MoMoIPNLog.objects.create(
                school=school,
                provider=ipn_provider,
                momo_reference=ref_raw,
                phone=clean_phone,
                amount=amount,
                raw_payload=normalised_payload,
                signature_valid=True,
                processed=False,
            )

            ReconciliationQueue.all_objects.create(
                school=school,
                momo_ipn_log=ipn_log,
                momo_reference=ref_raw,
                phone=clean_phone,
                amount=amount,
                provider=provider,
                status='pending',
                received_at=parsed_date,
                suggested_students=suggestions if suggestions else None,
            )
            imported += 1

        logger.info(
            f"Statement import complete for {school.name}: {imported} queued, "
            f"{skipped} duplicates skipped, profile={detected_profile_key}"
        )

        return {
            'imported': imported,
            'skipped': skipped,
            'total_rows': total_rows,
            'detected_format': detected_profile_key,
            'format_name': profile['name'],
        }
