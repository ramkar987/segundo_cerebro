from django import template

register = template.Library()


@register.filter
def timecode(value):
    try:
        total = max(0, int(float(value)))
    except (TypeError, ValueError):
        return ''

    hours, rem = divmod(total, 3600)
    minutes, seconds = divmod(rem, 60)
    if hours:
        return f'{hours:02d}:{minutes:02d}:{seconds:02d}'
    return f'{minutes:02d}:{seconds:02d}'
