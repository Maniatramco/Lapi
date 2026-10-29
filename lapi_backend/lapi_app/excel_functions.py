"""Excel functions pycel does not have, so formulas that use them can still be calculated.

pycel looks functions up by lower-case name in its function modules; workbook._calculator adds this
module to that list. Arguments arrive as pycel passes them: single values, or ranges as tuples of
row tuples. Dates are Excel serial numbers (days since 1899-12-30).
"""
import datetime as dt
import math
import statistics

NA = '#N/A'
VALUE = '#VALUE!'
NUM = '#NUM!'
EPOCH = dt.date(1899, 12, 30)


def _flat(*args):
    for arg in args:
        if isinstance(arg, (tuple, list)):
            yield from _flat(*arg)
        else:
            yield arg


def _numbers(*args):
    return [v for v in _flat(*args) if isinstance(v, (int, float)) and not isinstance(v, bool)]


def _date(serial):
    return EPOCH + dt.timedelta(days=int(serial))


def _serial(day):
    return (day - EPOCH).days


def _blank(value):
    return value is None or value == ''


def counta(*args):
    return sum(1 for v in _flat(*args) if not _blank(v))


def countblank(*args):
    return sum(1 for v in _flat(*args) if _blank(v))


def textjoin(delimiter, ignore_empty, *args):
    values = ['' if v is None else (str(int(v)) if isinstance(v, float) and v.is_integer() else str(v)) for v in _flat(*args)]
    return str(delimiter).join(v for v in values if v or not ignore_empty)


def proper(text):
    return ' '.join(word[:1].upper() + word[1:].lower() for word in str(text or '').split(' '))


def median(*args):
    values = _numbers(*args)
    return statistics.median(values) if values else NUM


def stdev(*args):
    values = _numbers(*args)
    return statistics.stdev(values) if len(values) > 1 else '#DIV/0!'


def rank(number, ref, order=0):
    values = _numbers(ref)
    if number not in values:
        return NA
    ordered = sorted(values, reverse=not order)
    return ordered.index(number) + 1


def switch(expression, *pairs):
    default = pairs[-1] if len(pairs) % 2 else NA
    for value, result in zip(pairs[0::2], pairs[1::2]):
        if value == expression:
            return result
    return default


def datedif(start, end, unit):
    if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
        return VALUE
    a, b, unit = _date(start), _date(end), str(unit).upper()
    if b < a:
        return NUM
    months = (b.year - a.year) * 12 + b.month - a.month - (b.day < a.day)
    if unit == 'Y':
        return months // 12
    if unit == 'M':
        return months
    if unit == 'D':
        return (b - a).days
    if unit == 'YM':
        return months % 12
    if unit == 'MD':
        return (b - (a.replace(year=b.year, month=b.month) if a.day <= 28 else a.replace(year=b.year, month=b.month, day=28))).days % 31
    if unit == 'YD':
        shifted = a.replace(year=b.year) if (a.month, a.day) != (2, 29) else dt.date(b.year, 3, 1)
        return (b - shifted).days if shifted <= b else (b - a.replace(year=b.year - 1)).days
    return NUM


def _holidays(holidays):
    return {int(v) for v in _numbers(holidays)} if holidays is not None else set()


def networkdays(start, end, holidays=None):
    if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
        return VALUE
    a, b, sign = int(start), int(end), 1
    if b < a:
        a, b, sign = b, a, -1
    off = _holidays(holidays)
    return sign * sum(1 for day in range(a, b + 1) if _date(day).weekday() < 5 and day not in off)


def workday(start, days, holidays=None):
    if not isinstance(start, (int, float)) or not isinstance(days, (int, float)):
        return VALUE
    day, left, step, off = int(start), abs(int(days)), 1 if days >= 0 else -1, _holidays(holidays)
    while left:
        day += step
        if _date(day).weekday() < 5 and day not in off:
            left -= 1
    return day


def _vector(values):
    """A one-row or one-column range as a flat list; None for a 2-D block."""
    if not isinstance(values, (tuple, list)):
        return [values]
    rows = [tuple(r) if isinstance(r, (tuple, list)) else (r,) for r in values]
    if all(len(r) == 1 for r in rows):
        return [r[0] for r in rows]
    if len(rows) == 1:
        return list(rows[0])
    return None


def _same(a, b):
    if isinstance(a, str) and isinstance(b, str):
        return a.lower() == b.lower()
    return a == b


def xmatch(lookup, array, match_mode=0, search_mode=1):
    values = _vector(array)
    if values is None:
        return VALUE
    order = range(len(values)) if search_mode >= 0 else range(len(values) - 1, -1, -1)
    exact = next((i for i in order if _same(values[i], lookup)), None)
    if exact is not None or match_mode == 0:
        return exact + 1 if exact is not None else NA
    comparable = [(i, v) for i, v in enumerate(values) if isinstance(v, type(lookup)) or (isinstance(v, (int, float)) and isinstance(lookup, (int, float)))]
    if match_mode == -1:
        smaller = [(v, i) for i, v in comparable if v < lookup]
        return max(smaller)[1] + 1 if smaller else NA
    if match_mode == 1:
        larger = [(v, i) for i, v in comparable if v > lookup]
        return min(larger)[1] + 1 if larger else NA
    return NA


def xlookup(lookup, lookup_array, return_array, if_not_found=NA, match_mode=0, search_mode=1):
    position = xmatch(lookup, lookup_array, match_mode, search_mode)
    if not isinstance(position, int):
        return if_not_found
    rows = return_array if isinstance(return_array, (tuple, list)) else ((return_array,),)
    rows = [tuple(r) if isinstance(r, (tuple, list)) else (r,) for r in rows]
    keys = _vector(lookup_array)
    if len(rows) == len(keys):                       # vertical: the matching row
        row = rows[position - 1]
        return row[0] if len(row) == 1 else row
    if len(rows) == 1 and len(rows[0]) == len(keys):  # horizontal: the matching column
        return rows[0][position - 1]
    return VALUE
