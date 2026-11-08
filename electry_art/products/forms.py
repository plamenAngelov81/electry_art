from django import forms

from electry_art.products.models import Product, ProductPhoto, ProductType, ProductMaterial, ProductColor


class BaseCreateForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['name_en'].required = True
        self.fields['description_en'].required = True

        self.fields['name_bg'].required = False
        self.fields['description_bg'].required = False


class ProductCreateForm(BaseCreateForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['product_image'].required = True

    class Meta(BaseCreateForm.Meta):
        fields = [
            'name_en',
            'name_bg',
            'serial_number',
            'type',
            'description_en',
            'description_bg',
            'material',
            'color',
            'size',
            'weight',
            'price',
            'url_link',
            'product_image',
        ]


class ProductEditForm(BaseCreateForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Existing image can be retained without uploading another file.
        # Legacy products without an image must receive one before saving.
        self.fields['product_image'].required = not bool(
            self.instance.pk and self.instance.product_image
        )

    def clean_product_image(self):
        image = self.cleaned_data.get('product_image')
        if not image:
            raise forms.ValidationError('A main product image is required.')
        return image

    class Meta(BaseCreateForm.Meta):
        fields = [
            'name_en',
            'name_bg',
            'serial_number',
            'type',
            'description_en',
            'description_bg',
            'material',
            'color',
            'size',
            'weight',
            'price',
            'is_available',
            'url_link',
            'product_image',
        ]

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