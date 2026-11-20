from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


class ProductResponse(BaseModel):
    """保险产品相应结果"""

    id: int
    name: str
    clause_name: str
    category: str
    insurer: str
    image_url: str | None
    description: str
    min_premium: Decimal | None
    max_premium: Decimal | None
    target_group: str | None
    highlights: list[str]
    status: str

    @field_validator("description", mode="before")
    @classmethod
    def normalize_description(cls, value: object) -> object:
        """数据库允许 description 为空，接口统一返回空字符串。"""
        return "" if value is None else value

    @field_validator("highlights", mode="before")
    @classmethod
    def normalize_highlights(cls, value: object) -> object:
        """数据库允许 highlights 为空，接口统一返回空数组。"""
        return [] if value is None else value


class PriceOption(BaseModel):
    """试算模板的带标签选项。"""

    value: int | str
    label: str


class PriceField(BaseModel):
    """价格试算模板字段"""

    key: str = Field(description="字段key，提交试算时放入 answers")
    label: str = Field(description="字段label，前端展示名称")
    type: str = Field(description="字段类型")
    required: bool = Field(description="是否必填")
    options: list[PriceOption | int | str] | None = Field(
        default=None, description="供试算表单选择的有效值"
    )


class PriceSchema(BaseModel):
    """保险价格试算模板"""

    title: str = Field(description="表单标题")
    fields: list[PriceField] = Field(description="表单字段列表")


class PriceResponse(BaseModel):
    """保险价格模板查询响应"""

    product_id: int = Field(description="产品ID")
    scenario: str = Field(description="试算场景")
    schema_version: str = Field(description="模板版本")
    schema: PriceSchema = Field(description="前端动态表单模板")
