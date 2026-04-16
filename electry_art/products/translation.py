from modeltranslation.translator import translator, TranslationOptions
from .models import Product, ProductType, ProductMaterial, ProductColor


class ProductTranslationOptions(TranslationOptions):
    fields = ('name', 'description')


class ProductTypeTranslationOptions(TranslationOptions):
    fields = ('name',)


class ProductMaterialTranslationOptions(TranslationOptions):
    fields = ('name',)


class ProductColorTranslationOptions(TranslationOptions):
    fields = ('name',)


translator.register(Product, ProductTranslationOptions)
translator.register(ProductType, ProductTypeTranslationOptions)
translator.register(ProductMaterial, ProductMaterialTranslationOptions)
translator.register(ProductColor, ProductColorTranslationOptions)