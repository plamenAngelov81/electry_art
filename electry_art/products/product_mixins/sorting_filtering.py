from decimal import Decimal, InvalidOperation
from django.db.models import Q


def _to_decimal(value: str):
    if value is None:
        return None
    value = str(value).strip()
    if not value:
        return None
    try:
        # приема "12.50"
        return Decimal(value)
    except (InvalidOperation, ValueError):
        return None


def apply_filters(qs, params, locked_type_slug=None):
    q = (params.get("q") or "").strip()
    type_slug = (params.get("type") or "").strip()
    material = (params.get("material") or "").strip()
    color = (params.get("color") or "").strip()
    min_price = _to_decimal(params.get("min_price"))
    max_price = _to_decimal(params.get("max_price"))
    available = (params.get("available") or "").strip()


    if locked_type_slug:
        qs = qs.filter(type__slug=locked_type_slug)
    elif type_slug:
        qs = qs.filter(type__slug=type_slug)

    # search
    if q:
        qs = qs.filter(
            Q(name__icontains=q) |
            Q(description__icontains=q) |
            Q(serial_number__icontains=q)
        )

    if material.isdigit():
        qs = qs.filter(material_id=int(material))

    if color.isdigit():
        qs = qs.filter(color_id=int(color))

    if min_price is not None:
        qs = qs.filter(price__gte=min_price)

    if max_price is not None:
        qs = qs.filter(price__lte=max_price)

    if available == "1":
        qs = qs.filter(is_available=True, quantity__gt=0)

    return qs


def apply_sort(qs, sort):
    sort = (sort or "new").strip()

    sort_map = {
        "new": ("-pk",),
        "old": ("pk",),
        "price_asc": ("price", "-pk"),
        "price_desc": ("-price", "-pk"),
    }
    ordering = sort_map.get(sort, sort_map["new"])
    return qs.order_by(*ordering)
