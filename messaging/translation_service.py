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
                '7️⃣ ABSENT - Report absence\n\n'
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
                '7️⃣ ABSENT - Loopa obutali ku somero\n\n'
                '💬 Wandiika ennamba oba ekiragiro waggulu.'
            ),
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
        phone = str(phone).strip()
        if not phone.startswith('+'):
            phone = '+' + phone
        guardian = Guardian.objects.filter(phone_normalised=phone).first()
        if guardian:
            return cls.get_language(guardian)
        return 'en'
