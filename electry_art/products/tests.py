
from django.test import TestCase
from electry_art.products.models import Product, ProductType, ProductPhoto
from django.urls import reverse
from django.db.utils import IntegrityError


class ProductModelTests(TestCase):
    def setUp(self):
        self.product_type = ProductType.objects.create(product_type='Test Type')

    def test_create_product(self):
        product = Product.objects.create(
            name='Sample Product',
            serial_number='SN12345',
            type=self.product_type,
            description='A test product description.',
            size='30x30x10',
            weight=1.5,
            price=49.99,
        )

        self.assertEqual(product.name, 'Sample Product')
        self.assertEqual(product.serial_number, 'SN12345')
        self.assertTrue(product.is_available)
        self.assertIsNotNone(product.date_created)
        self.assertIsNotNone(product.updated_on)

    def test_str_method_returns_serial_number(self):
        product = Product.objects.create(
            name='Another Product',
            serial_number='XYZ999',
            type=self.product_type,
            description='Description.',
            size='10x10',
            weight=1.0,
            price=19.99
        )
        self.assertEqual(str(product), 'XYZ999')

    def test_like_count_returns_zero_initially(self):
        product = Product.objects.create(
            name='No Likes Yet',
            serial_number='NL0001',
            type=self.product_type,
            description='No one liked this yet.',
            size='20x20',
            weight=2.0,
            price=9.99
        )
        self.assertEqual(product.like_count, 0)


class ProductPhotoModelTests(TestCase):
    def setUp(self):
        self.product_type = ProductType.objects.create(product_type='Photo Type')
        self.product = Product.objects.create(
            name='Photo Product',
            serial_number='PHOTO123',
            type=self.product_type,
            description='With a photo.',
            size='20x20x10',
            weight=2.5,
            price=99.99,
        )

    def test_create_photo(self):
        photo = ProductPhoto.objects.create(
            photo_name='front_view',
            product=self.product
        )

        self.assertEqual(photo.photo_name, 'front_view')
        self.assertEqual(photo.product, self.product)

    def test_photo_name_must_be_unique(self):
        ProductPhoto.objects.create(
            photo_name='unique_view',
            product=self.product
        )

        with self.assertRaises(IntegrityError):
            ProductPhoto.objects.create(
                photo_name='unique_view',
                product=self.product
            )


class ProductViewTests(TestCase):
    def setUp(self):
        self.product_type = ProductType.objects.create(product_type='Keychain')
        self.product = Product.objects.create(
            name='Keychain Test',
            serial_number='KC1001',
            type=self.product_type,
            description='Keychain test product.',
            size='5x5x1',
            weight=0.2,
            price=12.99,
            is_available=True,
        )

    def test_product_list_view(self):
        response = self.client.get(reverse('product list'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'products/get_all_products.html')
        self.assertContains(response, 'All Products')
        self.assertContains(response, self.product.name)

    def test_product_detail_view(self):
        response = self.client.get(reverse('product details', kwargs={'pk': self.product.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'products/product_details.html')
        self.assertContains(response, self.product.description)

    def test_product_category_view(self):
        response = self.client.get(reverse('product category', kwargs={'category': 'Keychain'}))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'products/get_all_products.html')
        self.assertContains(response, 'Keychain')
        self.assertContains(response, self.product.name)

    def test_product_detail_404(self):
        response = self.client.get(reverse('product details', kwargs={'pk': 9999}))
        self.assertEqual(response.status_code, 404)

    def test_product_list_view_no_products(self):
        Product.objects.all().delete()
        response = self.client.get(reverse('product list'))
        self.assertContains(response, 'All Products')
        self.assertNotContains(response, 'Keychain Test')

