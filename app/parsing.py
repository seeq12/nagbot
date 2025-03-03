import re
from dataclasses import dataclass
from datetime import datetime


from typing import Optional


# Return a datetime.datetime formatted date, or None if the string is not a date
def parse_date(date_str: str) -> Optional[datetime]:
    # noinspection PyBroadException
    try:
        return datetime.strptime(date_str, '%Y-%m-%d')
    except Exception:
        return None


# Take a datetime.datetime and return a string in the appropriate format
def date_to_string(datetime_value: datetime) -> Optional[str]:
    if datetime_value is None:
        return None
    return datetime_value.strftime('%Y-%m-%d')


@dataclass
class ParsedDate:
    expiry_date: Optional[str]   # Looks like: 2019-12-31
    on_weekends: bool
    warning_date: Optional[str]  # Looks like: 2019-12-31

    def __str__(self) -> str:
        if self.on_weekends:
            result = 'On Weekends'
        elif self.expiry_date is not None:
            result = self.expiry_date
        else:
            result = ''

        if self.warning_date is not None:
            result += ' (Nagbot: Warned on ' + self.warning_date + ')'
        return result


def parse_date_tag(date_tag: str) -> ParsedDate:
    parsed_date = ParsedDate(None, False, None)

    match = re.match(r'^(\d{4}-\d{2}-\d{2})', date_tag)
    if match:
        try:
            expiry_date = datetime.strptime(match.group(1), '%Y-%m-%d')
            parsed_date.expiry_date = date_to_string(expiry_date)
        except ValueError:
            # The data may not be valid
            pass

    match = re.match(r'^On Weekends', date_tag, re.IGNORECASE)
    if match:
        parsed_date.on_weekends = True

    match = re.match(r'.*\(Nagbot: Warned on (\d{4}-\d{2}-\d{2})\)$', date_tag)
    if match:
        warning_date = datetime.strptime(match.group(1), '%Y-%m-%d')
        parsed_date.warning_date = date_to_string(warning_date)

    return parsed_date


def add_warning_to_tag(old_date_tag: str, warning_date: str, replace=False) -> str:
    parsed_date = parse_date_tag(old_date_tag)
    if parsed_date.warning_date is None or replace:
        parsed_date.warning_date = warning_date
    return str(parsed_date)
