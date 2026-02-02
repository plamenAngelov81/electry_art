from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy, reverse
from django.utils.text import slugify
from django.views import generic, View
from electry_art.products.forms import ProductCreateForm, ProductEditForm, PhotoCreteForm, TypeCreateForm, \
    MaterialCreateForm, ColorCreateForm
from electry_art.products.models import Product, ProductPhoto, Like, ProductType, ProductMaterial, ProductColor
from electry_art.products.product_mixins.product_mixins import LikedIdsContextMixin, PropsContextMixin, \
    SuperuserRequiredMixin
from electry_art.products.product_mixins.sorting_filtering import apply_filters, apply_sort


def index(request):
    products = Product.objects.all()[:3]
    context = {
        'products': products
    }
    return render(request, 'products/index.html', context=context)


class FilteredProductsBaseView(LikedIdsContextMixin, generic.ListView):
    template_name = 'products/get_all_products.html'
    model = Product
    context_object_name = 'products'


    locked_type_slug = None

    page_title = 'All Products'

    def get_locked_type_slug(self):
        return self.locked_type_slug

    def get_queryset(self):
        qs = Product.objects.all().select_related("type", "material", "color")
        qs = apply_filters(qs, self.request.GET, locked_type_slug=self.get_locked_type_slug())
        qs = apply_sort(qs, self.request.GET.get("sort"))
        return qs

    def get_filters_context(self):
        """
        Filters dict.
        """
        return {
            "material": self.request.GET.get("material", ""),
            "color": self.request.GET.get("color", ""),
            "min_price": self.request.GET.get("min_price", ""),
            "max_price": self.request.GET.get("max_price", ""),
            "available": self.request.GET.get("available", ""),
            "sort": self.request.GET.get("sort", "new"),
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context['type'] = self.page_title

        context["materials"] = ProductMaterial.objects.all().order_by("name")
        context["colors"] = ProductColor.objects.all().order_by("name")

        context["filters"] = self.get_filters_context()
        return context


class ProductListView(FilteredProductsBaseView):
    paginate_by = 8
    page_title = 'All Products'

# Product Type CRUD operations
class ProductTypeCreateView(SuperuserRequiredMixin, generic.CreateView):
    model = ProductType
    form_class = TypeCreateForm
    template_name = 'products/type_create.html'
    success_url = reverse_lazy('superuser panel')


class ProductPropsListView(SuperuserRequiredMixin, generic.ListView):
    model = ProductType
    template_name = 'products/get_props.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        types = ProductType.objects.all().order_by('-pk')
        colors = ProductColor.objects.all().order_by('-pk')
        materials = ProductMaterial.objects.all().order_by('-pk')
        context["types"] = types
        context["colors"] = colors
        context["materials"] = materials
        context['all_objects'] = 'Types, Colors, Materials'
        return context


class ProductTypeEditView(SuperuserRequiredMixin, PropsContextMixin, generic.UpdateView):
    model = ProductType
    template_name = 'products/type_edit.html'
    form_class = TypeCreateForm
    success_url = reverse_lazy('props list')


class ProductTypeDeleteView(SuperuserRequiredMixin, generic.DeleteView):
    model = ProductType
    template_name = 'products/props_delete.html'
    success_url = reverse_lazy('props list')


# Product Material CRUD operations
class ProductMaterialCreateView(SuperuserRequiredMixin, generic.CreateView):
    model = ProductMaterial
    form_class = MaterialCreateForm
    template_name = 'products/material_create.html'
    success_url = reverse_lazy('superuser panel')


class ProductMaterialEditView(SuperuserRequiredMixin, PropsContextMixin, generic.UpdateView):
    model = ProductMaterial
    template_name = 'products/type_edit.html'
    form_class = MaterialCreateForm
    success_url = reverse_lazy('props list')


class ProductMaterialDeleteView(SuperuserRequiredMixin, generic.DeleteView):
    model = ProductMaterial
    template_name = 'products/props_delete.html'
    success_url = reverse_lazy('props list')


# Product colors CRUD operations
class ProductColorCreateView(SuperuserRequiredMixin, generic.CreateView):
    model = ProductColor
    form_class = ColorCreateForm
    template_name = 'products/color_create.html'
    success_url = reverse_lazy('superuser panel')


class ProductColorEditView(SuperuserRequiredMixin, PropsContextMixin, generic.UpdateView):
    model = ProductColor
    template_name = 'products/type_edit.html'
    form_class = ColorCreateForm
    success_url = reverse_lazy('props list')


class ProductColorDeleteView(SuperuserRequiredMixin, generic.DeleteView):
    model = ProductColor
    template_name = 'products/props_delete.html'
    success_url = reverse_lazy('props list')


# Photos
class PhotoCreateView(SuperuserRequiredMixin, generic.CreateView):
    model = ProductPhoto
    form_class = PhotoCreteForm
    template_name = 'products/create_photo.html'
    success_url = reverse_lazy('photo create')


class PhotoDetailsView(generic.DetailView):
    template_name = 'products/photo_details.html'
    model = ProductPhoto

    def get_queryset(self):
        return ProductPhoto.objects.filter(product__pk=self.kwargs['product_pk'])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["product"] = self.object.product
        return context


class PhotoEditView(SuperuserRequiredMixin, generic.UpdateView):
    model = ProductPhoto
    fields = ['photo_name', 'product_image']
    template_name = 'products/photo_edit.html'

    def get_success_url(self):
        return reverse_lazy('product details', kwargs={'slug': self.object.product.slug})



class PhotoDeleteView(SuperuserRequiredMixin, generic.DeleteView):
    model = ProductPhoto
    template_name = 'products/photo_confirm_delete.html'

    def get_success_url(self):
        return reverse('product details', kwargs={'slug': self.object.product.slug})


class ProductCreateView(SuperuserRequiredMixin, generic.CreateView):
    model = Product
    form_class = ProductCreateForm
    template_name = 'products/product_create.html'
    success_url = reverse_lazy('photo create')


class ProductDetailsView(generic.DetailView):
    template_name = 'products/product_details.html'
    model = Product
    slug_field = 'slug'
    slug_url_kwarg = 'slug'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        new_products = Product.objects.filter(type=self.object.type).exclude(pk=self.object.pk).order_by('date_created')[:6]
        photos = ProductPhoto.objects.filter(product_id=self.object.pk).order_by('pk')

        context["product"] = self.object
        context["photos"] = photos
        context["new_products"] = new_products

        if self.request.user.is_authenticated:
            context["user_liked"] = self.object.likes.filter(user=self.request.user).exists()
        else:
            context["user_liked"] = False

        return context


class ProductDetailsRedirectView(View):
    @staticmethod
    def get(request, *args, **kwargs):
        product = get_object_or_404(Product, pk=kwargs['pk'])
        return redirect('product details', slug=product.slug, permanent=True)


class ProductEditView(SuperuserRequiredMixin, LoginRequiredMixin, generic.UpdateView):
    model = Product
    template_name = 'products/product_edit.html'
    form_class = ProductEditForm

    def get_success_url(self):
        return reverse_lazy('product details', kwargs={'slug': self.object.slug})


class ProductCategoryListView(FilteredProductsBaseView):
    paginate_by = 12

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.type_obj = None

    def dispatch(self, request, *args, **kwargs):
        self.type_obj = get_object_or_404(ProductType, slug=self.kwargs['type_slug'])
        return super().dispatch(request, *args, **kwargs)

    def get_locked_type_slug(self):
        return self.type_obj.slug

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['type'] = self.type_obj.name
        context["current_type"] = self.type_obj
        return context


class ProductCategoryRedirectView(View):
    @staticmethod
    def get(request, *args, **kwargs):
        old_name = kwargs['category']
        type_obj = ProductType.objects.filter(name=old_name).first()

        if not type_obj:
            # fallback ако някой има стар URL с различен casing/spacing
            s = slugify(old_name, allow_unicode=True)
            type_obj = ProductType.objects.filter(slug=s).first()

        if not type_obj:
            raise Http404

        return redirect('product category', type_slug=type_obj.slug, permanent=True)


class ToggleLikeView(LoginRequiredMixin, View):
    @staticmethod
    def post(request, *args, **kwargs):
        product = get_object_or_404(Product, pk=kwargs['pk'])
        like, created = Like.objects.get_or_create(user=request.user, product=product)
        if not created:
            like.delete()  # Unlike
        return redirect(request.META.get('HTTP_REFERER', reverse('product list')))


class WishlistView(LoginRequiredMixin, generic.ListView):
    model = Product
    template_name = 'products/wishlist.html'
    context_object_name = 'wishlist'
    paginate_by = 8

    def get_queryset(self):
        return Product.objects.filter(likes__user=self.request.user).order_by('-pk')


class SearchView(generic.ListView):
    model = Product
    template_name = 'products/search_results.html'
    context_object_name = 'results'
    paginate_by = 12  # (optional)

    def get_queryset(self):
        query = self.request.GET.get('q')
        if query:
            return Product.objects.filter(name__icontains=query)
        return Product.objects.none()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['query'] = self.request.GET.get('q', '')
        return context


