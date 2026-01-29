from django.db.models import Q

def apply_filters(qs, params, locked_type_slug=None):
    q = (params.get("q") or "").strip()
    type_slug = (params.get("type") or "").strip()
    material = (params.get("material") or "").strip()
    color = (params.get("color") or "").strip()
    min_price = (params.get("min_price") or "").strip()
    max_price = (params.get("max_price") or "").strip()
    available = (params.get("available") or "").strip()

    # Ако сме в category view, type е заключен от URL
    if locked_type_slug:
        qs = qs.filter(type__slug=locked_type_slug)
    elif type_slug:
        qs = qs.filter(type__slug=type_slug)

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

    if min_price:
        try:
            qs = qs.filter(price__gte=min_price)
        except (ValueError, TypeError):
            pass

    if max_price:
        try:
            qs = qs.filter(price__lte=max_price)
        except (ValueError, TypeError):
            pass

    if available == "1":
        qs = qs.filter(is_available=True, quantity__gt=0)

    return qs


def apply_sort(qs, sort):
    sort = (sort or "new").strip()
    if sort == "old":
        return qs.order_by("pk")
    if sort == "price_asc":
        return qs.order_by("price", "-pk")
    if sort == "price_desc":
        return qs.order_by("-price", "-pk")
    return qs.order_by("-pk")  # new