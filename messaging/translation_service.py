"""
US-A05: Translation Service for WhatsApp command responses.
Supports English (en) and Luganda (lg) for all self-service commands.
"""


class TranslationService:
    """
    Provides translations for WhatsApp command responses.
    """

    TRANSLATIONS = {
        # TIMETABLE command
        'timetable_header': {
            'en': '📚 *{student_name} - {class_name} Timetable*\n\n{content}',
            'lg': '📚 *{student_name} - {class_name} Emirimu*\n\n{content}',
        },
        'timetable_not_available': {
            'en': '📚 *{student_name}*: No timetable published yet. Contact the school.',
            'lg': '📚 *{student_name}*: Emirimu teginnafulumizibwa. Tukirira essomero.',
        },
        'timetable_no_class': {
            'en': 'No class timetable available for your linked learner records.',
            'lg': 'Emirimu gy\'ekiraalagana tegiriwo ku byafaanani byammwe.',
        },

        # RESULTS command
        'results_header': {
            'en': '📊 *SchoolBridge Results*\n',
            'lg': '📊 *SchoolBridge Ebivudde*\n',
        },
        'results_detail': {
            'en': '🎓 *{student_name}*\n   Term: {term_name}\n   Total Marks: {total_marks}\n   Average: {average_marks}\n   Rank: {rank} of {total_students}\n   Division: {division}\n',
            'lg': '🎓 *{student_name}*\n   Ekiseera: {term_name}\n   Obubonero Bwonna: {total_marks}\n   Omutindo: {average_marks}\n   Ekifo: {rank} ku {total_students}\n   Division: {division}\n',
        },
        'results_not_available': {
            'en': '• *{student_name}*: No results available yet.\n',
            'lg': '• *{student_name}*: Ebivudde tebinnaba kufulumizibwa.\n',
        },

        # BALANCE command
        'balance_header': {
            'en': '📚 *SchoolBridge Fee Balance*\n',
            'lg': '📚 *SchoolBridge Ensimbi z\'Essomero*\n',
        },
        'balance_detail': {
            'en': '{icon} *{student_name}*\n   Class: {class_name}\n   Total: UGX {total:,}\n   Paid: UGX {paid:,}\n   Balance: UGX {balance:,}\n',
            'lg': '{icon} *{student_name}*\n   Ekkiraalagana: {class_name}\n   Zonna: UGX {total:,}\n   Ezisasuliddwa: UGX {paid:,}\n   Ezisigaddewo: UGX {balance:,}\n',
        },
        'balance_no_record': {
            'en': '• *{student_name}*: No fee record for current term.\n',
            'lg': '• *{student_name}*: Ensimbi z\'ekiseera kino teziriwo.\n',
        },
        'balance_no_term': {
            'en': '• *{student_name}*: No active term found.\n',
            'lg': '• *{student_name}*: Ekiseera tekiriwo.\n',
        },
        'balance_not_registered': {
            'en': (
                'Your number is not registered in our system. '
                'Please contact the school office to register. '
                'Reply HELP for more information.'
            ),
            'lg': (
                'Ennamba yo teriko mu enkola yaffe. '
                'Tukirira woofiisi y\'essomero okwewandiisa. '
                'Wandiika HELP ofune ebiragiro.'
            ),
        },

        # RECEIPT command
        'receipt_header': {
            'en': '🧾 *Payment Receipts*\n',
            'lg': '🧾 *Ebiragiro by\'Okusasula*\n',
        },
        'receipt_line': {
            'en': '• {date} — UGX {amount:,} via {method}',
            'lg': '• {date} — UGX {amount:,} okuyita mu {method}',
        },
        'receipt_not_registered': {
            'en': 'Number not registered. Reply HELP.',
            'lg': 'Ennamba teriko. Wandiika HELP.',
        },
        'receipt_none_found': {
            'en': 'No payments found{date_suffix}.',
            'lg': 'Tewasuulwa ndala{date_suffix}.',
        },
        'receipt_date_suffix': {
            'en': ' for {date}',
            'lg': ' ku {date}',
        },
        'receipt_invalid_date': {
            'en': 'Invalid date format. Use: RECEIPT YYYY-MM-DD',
            'lg': 'Akabonero k\'ennaku tekituufu. Kozesa: RECEIPT YYYY-MM-DD',
        },

        # ATTEND command
        'attend_header': {
            'en': '📅 *SchoolBridge Attendance*\n',
            'lg': '📅 *SchoolBridge Okubaawo*\n',
        },
        'attend_detail': {
            'en': '{icon} *{student_name}*\n   Attendance: {rate:.1f}%\n   {status}\n',
            'lg': '{icon} *{student_name}*\n   Okubaawo: {rate:.1f}%\n   {status}\n',
        },
        'attend_status_good': {
            'en': 'Good standing',
            'lg': 'Embeera nnungi',
        },
        'attend_status_low': {
            'en': 'Below 75% threshold - please contact school',
            'lg': 'Wansi wa 75% - tukirira essomero',
        },
        'attend_no_records': {
            'en': '• *{student_name}*: No attendance records yet.\n',
            'lg': '• *{student_name}*: Ebikwata ku kubaawo tebinnaba kuteekebwa.\n',
        },

        # LUGANDA/ENGLISH command
        'language_switched': {
            'en': '✅ Language switched to *English*. All future replies will be in English.',
            'lg': '✅ Olulimi lwaakyusibwa okutuuka *Oluganda*. Ebisubizo byonna bijja kuba mu Luganda.',
        },

        # MENU command
        'menu_text': {
            'en': (
                '👋 *Welcome to SchoolBridge*\n\n'
                'Please reply with a number or command:\n\n'
                '1️⃣ BALANCE - Fee balance\n'
                '2️⃣ RESULTS - Exam results\n'
                '3️⃣ ATTEND - Attendance rate\n'
                '4️⃣ RECEIPT - Payment history\n'
                '5️⃣ TIMETABLE - Class schedule\n'
                '6️⃣ PLAN - Request payment plan\n'
                '7️⃣ ABSENT - Report absence\n'
                '8️⃣ PAY - Pay fees via MoMo\n\n'
                '💬 Type any number or command above.'
            ),
            'lg': (
                '👋 *Tusanyukidde kukusanga ku SchoolBridge*\n\n'
                'Wandiika ennamba oba ekiragiro:\n\n'
                '1️⃣ BALANCE - Ensimbi ezisigaddewo\n'
                '2️⃣ RESULTS - Ebivudde mu bibuuzo\n'
                '3️⃣ ATTEND - Okubaawo\n'
                '4️⃣ RECEIPT - Ebyafaanani by\'okusasula\n'
                '5️⃣ TIMETABLE - Emirimu\n'
                '6️⃣ PLAN - Saba entereera y\'okusasula\n'
                '7️⃣ ABSENT - Loopa obutali ku somero\n'
                '8️⃣ PAY - Sasula ensimbi ku MoMo\n\n'
                '💬 Wandiika ennamba oba ekiragiro waggulu.'
            ),
        },

        # PAY command (US-A03)
        'pay_initiated': {
            'en': (
                '✅ *Payment Request Sent*\n\n'
                'Student: {student_name}\n'
                'Amount: UGX {amount:,}\n\n'
                'A MoMo prompt has been sent to your phone.\n'
                'Please enter your PIN to confirm payment.\n\n'
                'Reply BALANCE after payment to check your updated balance.'
            ),
            'lg': (
                '✅ *Okusaba Okusasula Kwetikkiddwa*\n\n'
                'Omuyizi: {student_name}\n'
                'Omuwendo: UGX {amount:,}\n\n'
                'Obubaka bwa MoMo butumiddwa ku ssimu yo.\n'
                'Wandiika PIN yo okukakasa okusasula.\n\n'
                'Wandiika BALANCE oluvannyuma okukebera ensimbi zo.'
            ),
        },
        'pay_failed': {
            'en': (
                '❌ *Payment Request Failed*\n\n'
                'We could not initiate your MoMo payment.\n'
                'Please try again later or pay directly via MoMo to: {merchant_phone}\n\n'
                'Reply HELP for assistance.'
            ),
            'lg': (
                '❌ *Okusasula Tegusobodde*\n\n'
                'Tetusobodde kutandika kusasula kwa MoMo.\n'
                'Gezaako nate oluvannyuma oba osasula butereevu ku MoMo: {merchant_phone}\n\n'
                'Wandiika HELP ofune obuyambi.'
            ),
        },
        'pay_invalid_amount': {
            'en': (
                '⚠️ Invalid amount. Please use format:\n'
                'PAY <amount> — e.g. PAY 150000\n'
                'PAY <amount> <child name> — e.g. PAY 150000 John\n\n'
                'Amount must be between 1,000 and 5,000,000 UGX.'
            ),
            'lg': (
                '⚠️ Omuwendo si mutuufu. Kozesa:\n'
                'PAY <omuwendo> — eky. PAY 150000\n'
                'PAY <omuwendo> <erinnya ly\'omwana> — eky. PAY 150000 John\n\n'
                'Omuwendo gusaanidde okuba wakati wa 1,000 ne 5,000,000 UGX.'
            ),
        },
        'pay_multiple_siblings': {
            'en': (
                '👨‍👩‍👧‍👦 You have {count} children registered:\n\n'
                '{children_list}\n\n'
                'Please specify which child to pay for:\n'
                'PAY <amount> <child name>\n'
                'Example: PAY 150000 {example_name}'
            ),
            'lg': (
                '👨‍👩‍👧‍👦 Olina abaana {count} abawandiisiddwa:\n\n'
                '{children_list}\n\n'
                'Laga omwana gw\'oyagala okusasulira:\n'
                'PAY <omuwendo> <erinnya ly\'omwana>\n'
                'Ekyokulabirako: PAY 150000 {example_name}'
            ),
        },
        'pay_no_balance': {
            'en': '✅ *{student_name}* has no outstanding balance. No payment needed!',
            'lg': '✅ *{student_name}* talina nsimbi zisigaddewo. Tokusasula!',
        },
        'pay_student_not_found': {
            'en': '⚠️ Could not find a child named "{identifier}". Reply MENU to see options.',
            'lg': '⚠️ Omwana "{identifier}" tazuuliddwa. Wandiika MENU obone ebiragiro.',
        },

        # Common messages
        'not_registered': {
            'en': 'Your number is not registered. Contact the school office. Reply HELP for commands.',
            'lg': 'Ennamba yo teriko. Tukirira woofiisi y\'essomero. Wandiika HELP ofune ebiragiro.',
        },
        'help_suffix': {
            'en': '\n\nReply HELP for more commands.',
            'lg': '\n\nWandiika HELP ofune ebiragiro ebirala.',
        },
        'unknown_command': {
            'en': "Sorry, I didn't understand that command. Reply HELP for a list of commands.",
            'lg': 'Nsonyiwa, sitegedde kiragiro kyo. Wandiika HELP ofune ebiragiro.',
        },

        # ABSENT command (US-052)
        'absent_invalid_format': {
            'en': (
                '⚠️ Invalid format. Use:\n'
                'ABSENT YYYY-MM-DD [reason]\n'
                'Example: ABSENT 2026-07-15 Sick\n\n'
                'Reply HELP for all commands.'
            ),
            'lg': (
                '⚠️ Endabika si ntuufu. Kozesa:\n'
                'ABSENT YYYY-MM-DD [ensonga]\n'
                'Ekyokulabirako: ABSENT 2026-07-15 Mulwadde\n\n'
                'Wandiika HELP ofune ebiragiro byonna.'
            ),
        },
        'absent_invalid_date': {
            'en': (
                '⚠️ Invalid date format. Use YYYY-MM-DD.\n'
                'Example: ABSENT 2026-07-15 Sick'
            ),
            'lg': (
                '⚠️ Akabonero k\'ennaku si ntuufu. Kozesa YYYY-MM-DD.\n'
                'Ekyokulabirako: ABSENT 2026-07-15 Mulwadde'
            ),
        },
        'absent_noted': {
            'en': '✅ Absence noted for {student_names} on {date_str}. The class teacher has been informed. Thank you.',
            'lg': '✅ Obutaliwo bwa {student_names} ku {date_str} buwandiikiddwa. Mwalimu ategeezeddwa. Webale.',
        },
    }

    @classmethod
    def get(cls, key, lang='en', **kwargs):
        """
        Get a translated string for the given key and language.
        
        Args:
            key: Translation key (e.g. 'timetable_header')
            lang: Language code ('en' or 'lg')
            **kwargs: Format parameters for the translation string
        
        Returns:
            Formatted translated string, or English fallback if key/lang not found
        """
        lang = lang if lang in ('en', 'lg') else 'en'
        translation_dict = cls.TRANSLATIONS.get(key, {})
        template = translation_dict.get(lang, translation_dict.get('en', ''))
        
        if kwargs:
            try:
                return template.format(**kwargs)
            except KeyError:
                return template
        return template

    @classmethod
    def get_language(cls, guardian):
        """
        Get guardian's preferred language, defaulting to English.
        
        Args:
            guardian: Guardian model instance
        
        Returns:
            Language code ('en' or 'lg')
        """
        if hasattr(guardian, 'preferred_language'):
            return guardian.preferred_language if guardian.preferred_language in ('en', 'lg') else 'en'
        return 'en'

    @classmethod
    def get_language_from_phone(cls, phone):
        """
        Get preferred language for a phone number by looking up guardian record.
        Normalises phone to +256... format to match Guardian.phone_normalised.
        """
        from students.models import Guardian
        import hashlib
        phone = str(phone).strip()
        if not phone.startswith('+'):
            phone = '+' + phone
        phone_hash = hashlib.sha256(phone.encode()).hexdigest()
        guardian = Guardian.objects.filter(phone_hash=phone_hash).first()
        if guardian:
            return cls.get_language(guardian)
        return 'en'
