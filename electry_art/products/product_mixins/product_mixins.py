from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import Http404

from electry_art.products.models import Like


class SuperuserRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """
    Allows access only to authenticated superusers.
    """
    raise_exception = True  # -> 403

    def test_func(self):
        return self.request.user.is_superuser

    def handle_no_permission(self):
        # Ако не е логнат, LoginRequiredMixin ще го прати към login (по default).
        # Но ти искаш да е "скрито" -> 404 за всички не-superusers.
        raise Http404


class PropsContextMixin:
    """
    Mixin to provide common context data for Product Type, Material, and Color edit views.
    """
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Assuming self.object is already available from the UpdateView/DetailView
        # We use self.object._meta.model to dynamically get the current model class
        current_model = self.object._meta.model
        object_props = current_model.objects.filter(name=self.object.name).get()
        context['object_props'] = object_props
        return context


class LikedIdsContextMixin:
    """
    Adds `liked_ids` (set of product IDs liked by the current user) to the context.
    """
    def get_liked_ids(self):
        user = self.request.user
        if user.is_authenticated:
            return set(
                Like.objects.filter(user=user).values_list('product_id', flat=True)
            )
        return set()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["liked_ids"] = self.get_liked_ids()
        return context