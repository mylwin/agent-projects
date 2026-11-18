import unittest
from decimal import Decimal
from unittest.mock import AsyncMock

from auth_support import handle_application_error
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from app.core.exceptions import ApplicationError
from app.modules.product.exceptions import PriceTemplateNotFoundError
from app.modules.product.models import Product, ProductPrice
from app.modules.product.repository import ProductRepository
from app.modules.product.router import get_product_service, router
from app.modules.product.schemas import (
    PriceField,
    PriceResponse,
    PriceSchema,
    ProductResponse,
)
from app.modules.product.service import ProductService


def make_schema_json() -> dict:
    return {
        "rules": [],
        "title": "试算模板",
        "fields": [
            {
                "key": "plan_code",
                "label": "保障计划",
                "type": "plan_select",
                "required": True,
                "options_ref": "plan_options",
            },
            {
                "key": "coverage.coverage_amount",
                "label": "保额",
                "type": "money",
                "required": True,
                "options": [300000, 500000],
            },
            {
                "key": "insured.age",
                "label": "年龄",
                "type": "integer",
                "required": True,
                "min": 0,
                "max": 35,
            },
        ],
        "plan_options": [{"label": "基础", "value": "basic"}],
    }


class ProductPriceModelTests(unittest.TestCase):
    def test_maps_existing_pricing_schema_table(self):
        table = ProductPrice.__table__

        self.assertEqual(table.name, "product_pricing_schemas")
        self.assertEqual(
            set(table.columns.keys()),
            {
                "id",
                "product_id",
                "scenario",
                "schema_version",
                "schema_json",
                "schema_hash",
                "status",
                "activated_at",
                "created_at",
            },
        )
        self.assertNotIn("updated_at", table.columns)
        self.assertIsInstance(table.c.id.type, PG_UUID)
        self.assertIsInstance(table.c.schema_json.type, JSONB)
        self.assertEqual(
            {fk.target_fullname for fk in table.c.product_id.foreign_keys},
            {"products.id"},
        )


class PriceResponseTests(unittest.TestCase):
    def test_accepts_schema_alias_and_serializes_back_to_schema(self):
        response = PriceResponse(
            product_id=1,
            scenario="premium_by_coverage",
            schema_version="2026-06-09.v1",
            schema=PriceSchema.model_validate(make_schema_json()),
        )

        self.assertEqual(response.price_schema.title, "试算模板")
        self.assertEqual(
            response.model_dump(by_alias=True)["schema"]["title"], "试算模板"
        )


class PriceTemplateServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_maps_schema_json_into_response(self):
        service = ProductService(AsyncMock())
        service.repository = AsyncMock(spec=ProductRepository)
        service.repository.find_pricing_schema_by_id.return_value = ProductPrice(
            product_id=2,
            scenario="premium_by_coverage",
            schema_version="2026-06-09.v1",
            schema_json=make_schema_json(),
            status="active",
        )

        response = await service.find_pricing_schema_by_id(2)

        self.assertEqual(response.product_id, 2)
        self.assertEqual(len(response.price_schema.fields), 3)
        # 完整保留数据库模板的类型与配置
        self.assertEqual(response.price_schema.fields[0].type, "select")
        self.assertEqual(response.price_schema.fields[1].type, "number")
        self.assertEqual(response.price_schema.fields[2].type, "number")
        self.assertEqual(
            [
                (option.label, option.value)
                for option in response.price_schema.fields[0].options
            ],
            [("基础", "basic")],
        )
        self.assertEqual(response.price_schema.fields[1].options, [300000, 500000])
        # 接口不再返回模板内部字段
        self.assertFalse(hasattr(response.price_schema.fields[0], "options_ref"))
        self.assertFalse(hasattr(response.price_schema, "plan_options"))
        self.assertFalse(hasattr(response.price_schema, "rules"))
        service.repository.find_pricing_schema_by_id.assert_awaited_once_with(2)

    async def test_missing_template_raises_not_found(self):
        service = ProductService(AsyncMock())
        service.repository = AsyncMock(spec=ProductRepository)
        service.repository.find_pricing_schema_by_id.return_value = None

        with self.assertRaises(PriceTemplateNotFoundError):
            await service.find_pricing_schema_by_id(999)


class PriceTemplateApiTests(unittest.TestCase):
    def setUp(self):
        self.service = AsyncMock(spec=ProductService)
        app = FastAPI()
        app.include_router(router)
        app.add_exception_handler(ApplicationError, handle_application_error)
        app.dependency_overrides[get_product_service] = lambda: self.service
        self.client = TestClient(app)

    def test_returns_contract_fields(self):
        self.service.find_pricing_schema_by_id.return_value = PriceResponse(
            product_id=2,
            scenario="premium_by_coverage",
            schema_version="2026-06-09.v1",
            schema=PriceSchema(
                title="试算模板",
                fields=[
                    PriceField(
                        key="plan_code",
                        label="保障计划",
                        type="select",
                        required=True,
                        options=[{"label": "基础", "value": "basic"}],
                    ),
                    PriceField(
                        key="coverage.coverage_amount",
                        label="保额",
                        type="number",
                        required=True,
                        options=[300000, 500000],
                    ),
                    PriceField(
                        key="insured.age",
                        label="年龄",
                        type="number",
                        required=True,
                    ),
                ],
            ),
        )

        response = self.client.get("/api/v1/products/2/pricing-schema")

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(set(body["schema"]), {"title", "fields"})
        field_keys = {field["key"]: set(field) for field in body["schema"]["fields"]}
        self.assertEqual(
            field_keys["plan_code"],
            {"key", "label", "type", "required", "options"},
        )
        self.assertEqual(
            field_keys["insured.age"], {"key", "label", "type", "required"}
        )
        self.assertEqual(
            body["schema"]["fields"][0]["options"],
            [{"label": "基础", "value": "basic"}],
        )
        self.assertEqual(body["schema"]["fields"][1]["options"], [300000, 500000])
        self.assertEqual(body["schema"]["fields"][2]["type"], "number")
        self.assertNotIn("plan_options", body["schema"])
        self.assertNotIn("rules", body["schema"])

    def test_missing_template_returns_404(self):
        self.service.find_pricing_schema_by_id.side_effect = PriceTemplateNotFoundError

        response = self.client.get("/api/v1/products/999/pricing-schema")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "PRICING_SCHEMA_NOT_FOUND")


class ProductResponseTests(unittest.TestCase):
    def test_normalizes_nullable_product_columns(self):
        product = Product(
            id=1,
            name="测试产品",
            clause_name="条款.pdf",
            category="medical",
            insurer="测试保险公司",
            image_url=None,
            description=None,
            min_premium=Decimal("100.00"),
            max_premium=None,
            target_group=None,
            highlights=None,
            status="active",
        )

        response = ProductResponse.model_validate(product, from_attributes=True)

        self.assertIsNone(response.image_url)
        self.assertEqual(response.description, "")
        self.assertEqual(response.highlights, [])


if __name__ == "__main__":
    unittest.main()
