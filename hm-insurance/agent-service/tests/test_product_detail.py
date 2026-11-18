import unittest
from decimal import Decimal
from unittest.mock import AsyncMock

from auth_support import handle_application_error
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.exceptions import ApplicationError
from app.modules.product.exceptions import ProductNotFoundError
from app.modules.product.models import Product
from app.modules.product.repository import ProductRepository
from app.modules.product.router import get_product_service, router
from app.modules.product.schemas import ProductResponse
from app.modules.product.service import ProductService


def make_product(**overrides) -> Product:
    data = {
        "id": 1,
        "name": "测试产品",
        "clause_name": "测试产品条款.pdf",
        "category": "medical",
        "insurer": "测试保险公司",
        "image_url": "https://example.com/product.png",
        "description": "测试产品描述",
        "min_premium": Decimal("128.00"),
        "max_premium": Decimal("999.00"),
        "target_group": "18-60周岁",
        "highlights": ["亮点一", "亮点二"],
        "status": "active",
    }
    return Product(**(data | overrides))


class ProductDetailServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_find_by_id_maps_orm_product(self):
        service = ProductService(AsyncMock())
        service.repository = AsyncMock(spec=ProductRepository)
        service.repository.find_by_id.return_value = make_product()

        product = await service.find_by_id(1)

        self.assertIsInstance(product, ProductResponse)
        self.assertEqual(product.clause_name, "测试产品条款.pdf")
        self.assertEqual(product.highlights, ["亮点一", "亮点二"])
        service.repository.find_by_id.assert_awaited_once_with(1)

    async def test_find_by_id_raises_not_found(self):
        service = ProductService(AsyncMock())
        service.repository = AsyncMock(spec=ProductRepository)
        service.repository.find_by_id.return_value = None

        with self.assertRaises(ProductNotFoundError):
            await service.find_by_id(999)


class ProductDetailApiTests(unittest.TestCase):
    def setUp(self):
        self.service = AsyncMock(spec=ProductService)
        app = FastAPI()
        app.include_router(router)
        app.add_exception_handler(ApplicationError, handle_application_error)
        app.dependency_overrides[get_product_service] = lambda: self.service
        self.client = TestClient(app)

    def test_detail_returns_product_and_clause_name(self):
        self.service.find_by_id.return_value = ProductResponse(
            id=1,
            name="测试产品",
            clause_name="测试产品条款.pdf",
            category="medical",
            insurer="测试保险公司",
            image_url="https://example.com/product.png",
            description="测试产品描述",
            min_premium=Decimal("128.00"),
            max_premium=Decimal("999.00"),
            target_group="18-60周岁",
            highlights=["亮点一"],
            status="active",
        )

        response = self.client.get("/api/v1/products/1")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["clause_name"], "测试产品条款.pdf")
        self.service.find_by_id.assert_awaited_once_with(1)

    def test_missing_product_returns_404(self):
        self.service.find_by_id.side_effect = ProductNotFoundError

        response = self.client.get("/api/v1/products/999")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json(),
            {"code": "PRODUCT_NOT_FOUND", "message": "产品不存在或已下架"},
        )


if __name__ == "__main__":
    unittest.main()
