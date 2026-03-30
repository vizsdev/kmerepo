from django import template

register = template.Library()


@register.filter
def getfield(form, field_name):
    """Return a bound field from a form by name."""
    try:
        return form[field_name]
    except KeyError:
        return None


@register.filter
def startswith(value, arg):
    return str(value).startswith(arg)


@register.filter
def has_extra_fields(form):
    return any(k.startswith('extra_') for k in form.fields)


@register.filter
def dictsort_by_key(value, key):
    try:
        return sorted(value, key=lambda x: x.get(key, ''))
    except Exception:
        return value


@register.filter
def get_item(dictionary, key):
    if isinstance(dictionary, dict):
        return dictionary.get(key, '')
    return ''
