from django import forms

from electry_art.products.models import Product, ProductPhoto, ProductType, ProductMaterial, ProductColor


class BaseCreateForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = '__all__'



class ProductCreateForm(BaseCreateForm):
    class Meta(BaseCreateForm.Meta):
        exclude = ['is_available', 'slug']


class ProductEditForm(BaseCreateForm):
    class Meta(BaseCreateForm.Meta):
        exclude = ['is_available', 'slug']

class PhotoCreateForm(forms.ModelForm):
    class Meta:
        model = ProductPhoto
        fields = '__all__'


class TypeCreateForm(forms.ModelForm):
    class Meta:
        model = ProductType
        exclude = ['slug']


class MaterialCreateForm(forms.ModelForm):
    class Meta:
        model = ProductMaterial
        fields = '__all__'


class ColorCreateForm(forms.ModelForm):
    class Meta:
        model = ProductColor
        fields = '__all__'