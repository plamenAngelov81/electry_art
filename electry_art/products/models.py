from django.core.validators import MinLengthValidator, MinValueValidator
from django.conf import settings
from django.db import models
from django.utils.text import slugify


class BaseModel(models.Model):
    product_image = models.ImageField(
        verbose_name='Product Image',
        null=True,
        blank=True,
    )

    class Meta:
        abstract = True


class ProductTypeMaterialColor(models.Model):
    name = models.CharField(
        max_length=30,
        validators=[MinLengthValidator(3)],
        null=False,
        blank=False
    )

    class Meta:
        abstract = True

    def __str__(self):
        return self.name


class ProductType(ProductTypeMaterialColor):
    slug = models.SlugField(
        max_length=120,
        unique=True,
        null=True,
        blank=True,
        allow_unicode=True,
    )

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name, allow_unicode=True) or "type"
            slug = base
            i = 1
            while ProductType.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                i += 1
                slug = f"{base}-{i}"
            self.slug = slug
        super().save(*args, **kwargs)


class ProductMaterial(ProductTypeMaterialColor):
    pass


class ProductColor(ProductTypeMaterialColor):
    pass


class Product(BaseModel):
    name = models.CharField(
        max_length=300,
        verbose_name='Product Name',
        validators=[MinLengthValidator(2)],
        null=False,
        blank=False
    )

    serial_number = models.CharField(
        max_length=20,
        verbose_name='Serial Number',
        validators=[MinLengthValidator(5)],
        unique=True,
        null=False,
        blank=False
    )

    type = models.ForeignKey(
        ProductType,
        on_delete=models.CASCADE,
        null=False,
        blank=False
    )

    description = models.TextField(
        verbose_name='Description',
        null=False,
        blank=False
    )

    material = models.ForeignKey(
        ProductMaterial,
        on_delete=models.CASCADE,
        null=False,
        blank=False
    )

    color = models.ForeignKey(
        ProductColor,
        on_delete=models.CASCADE,
        null=False,
        blank=False
    )

    size = models.CharField(
        max_length=30,
        verbose_name='Size',
        validators=[MinLengthValidator(5)],
        null=False,
        blank=False
    )

    weight = models.FloatField(
        verbose_name='Weight',
        validators=[MinValueValidator(0)],
        null=False,
        blank=False
    )

    price = models.DecimalField(
        verbose_name='Price',
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        null=False,
        blank=False
    )

    date_created = models.DateTimeField(
        auto_now_add=True
    )

    updated_on = models.DateTimeField(
        auto_now=True
    )

    is_available = models.BooleanField(
        verbose_name='Available Quantity',
        null=False,
        blank=False,
        default=True
    )

    quantity = models.IntegerField(
        verbose_name='Quantity',
        null=False,
        blank=False,
        default=1
    )

    url_link = models.URLField(
        null=True,
        blank=True,
    )

    slug = models.SlugField(
        max_length=255,
        unique=True,
        null=True,
        blank=True,
        allow_unicode=True,
    )

    class Meta:
        verbose_name_plural = 'Products'
        ordering = ['-pk']

    @property
    def like_count(self):
        return self.likes.count()

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name, allow_unicode=True) or "product"
            slug = base
            i = 1
            while Product.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                i += 1
                slug = f"{base}-{i}"
            self.slug = slug
        super().save(*args, **kwargs)

    def is_liked_by(self, user):
        return self.likes.filter(user=user).exists()

    def __str__(self):
        return self.serial_number


class ProductPhoto(BaseModel):
    photo_name = models.CharField(
        verbose_name='Photo Name',
        max_length=30,
        null=False,
        blank=False,
        unique=True,
        validators=[MinLengthValidator(3)]
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        null=False,
        blank=False
    )

    class Meta:
        ordering = ['-pk']


class Like(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='likes'
    )

    product = models.ForeignKey(
        'Product',
        on_delete=models.CASCADE,
        related_name='likes'
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'product')

    def __str__(self):
        return f"{self.user.username} likes {self.product.name}"
