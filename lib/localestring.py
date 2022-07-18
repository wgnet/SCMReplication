import locale

language, locale_encoding = locale.getlocale()
if locale_encoding is None:
    locale.setlocale(locale.LC_ALL, locale.getdefaultlocale())
    language, locale_encoding = locale.getlocale()


def convert_curr_locale_to_unicode_str(from_str):
    if isinstance(from_str, list):
        return [convert_curr_locale_to_unicode_str(s) for s in from_str]
    return from_str.decode(locale_encoding)


def convert_unicode_to_current_locale(from_str):
    if isinstance(from_str, list):
        return [convert_curr_locale_to_unicode_str(s) for s in from_str]
    return from_str.encode(locale_encoding)


def convert_utf8_to_curr_locale(from_str):
    '''internally pysvn uses/outputs utf8 to encode strings
    '''
    if locale_encoding == 'UTF-8':
        return from_str

    if isinstance(from_str, list):
        return [convert_utf8_to_curr_locale(s) for s in from_str]
    to_str = from_str.decode('utf8').encode(locale_encoding,
                                                errors='ignore')
    return to_str
