from django.core.management.base import BaseCommand


def validate_query_parameter(value: str) -> bool:
    return _validate_value(value, ':')


def validate_update_parameter(value: str) -> bool:
    return _validate_value(value, '=')


def write_error(cmd: BaseCommand, error: str) -> None:
    cmd.stdout.write(
        cmd.style.ERROR(error)
    )


# region " Helpers "


def _is_none_or_empty(value: str) -> bool:
    return value is None or value.strip() == ''


# TODO: This logic could use another pass for clean up. Additionally, there could be more helper methods that check
#     :   a full list of values, and allowing ":", "=", or both.
def _validate_value(value: str, separator: str) -> bool:
    if _is_none_or_empty(value):
        return False

    parts = value.split(separator)
    if len(parts) != 2:
        return False

    if _is_none_or_empty(parts[0]) or _is_none_or_empty(parts[1]):
        return False

    return True


# endregion
