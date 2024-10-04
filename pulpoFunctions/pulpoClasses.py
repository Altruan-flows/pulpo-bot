from pydantic import BaseModel
from typing import Optional, List
from pulpoFunctions import Pulpo


def createDataClassTemplate(newClassName: str, entity: dict, itemsName: str = ""):
    # helps to generate Neu classes
    print(f"class {newClassName}(BaseModel, Blueprint):")
    for key, value in entity.items():
        if key == itemsName:
            classNameItemName = f"{itemsName[:1].upper()}{itemsName[1:]}"
            print(f"\t{key}: List[{classNameItemName}] = []")
        elif key == "customAttributes":
            print(f"\t{key}: List[WeclappMetaData] = []")
        else:
            print(f"\t{key}: {type(value).__name__}")
    print()
    print("\t# AutomationData")
    print(f'\tITEMS_NAME: str = "{itemsName}"')
    print("\tUSED_KEYS: set = set()")


class Blueprint:

    @classmethod
    def fromPulpo(cls, endpoint: str, entity_id: str, pulpo: Pulpo = None):
        if not pulpo:
            pulpo = Pulpo()
        response = pulpo.askPulpo(
            method="GET",
            endpoint=f"{endpoint}/{entity_id}"
        )
        return cls(**response)

#     # @classmethod
#     # def fromDict(cls, entity:dict):

#     #     return cls(**entity)

#     @classmethod
#     def blank(cls):
#         fields = {field: None for field in cls.__fields__}
#         return cls(**fields)


################################################################################
class Address(BaseModel, Blueprint):
    additional_info: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    country_code: Optional[str] = None
    email: Optional[str] = None
    house_nr: Optional[str] = None
    state: Optional[str] = None
    street: Optional[str] = None
    zip: Optional[str] = None

    # AutomationData
    ITEMS_NAME: str = ""
    USED_KEYS: set = set()


class ShipTo(BaseModel, Blueprint):
    address: Optional[Address] = {}
    company_name: Optional[str] = None
    name: Optional[str] = None
    phone_number: Optional[str] = None

    # AutomationData
    ITEMS_NAME: str = ""
    USED_KEYS: set = set()


class ProductAttributes(BaseModel):
    article_image_id: Optional[str] = None
    weclapp_article_id: Optional[str] = None

    # AutomationData
    ITEMS_NAME: str = ""
    USED_KEYS: set = set()


class Product(BaseModel, Blueprint):
    id: Optional[int] = None
    name: Optional[str] = None
    description: Optional[str] = None
    product_categories: Optional[list] = []
    third_party_id: Optional[int] = None
    barcodes: Optional[list] = []
    sku: Optional[str] = None
    supplier_product_id: Optional[int] = None
    third_party: Optional[str] = None
    merchant_channel_ids: Optional[list] = []
    attributes: Optional[ProductAttributes] = {}
    cost_price: Optional[float] = None
    hs_code: Optional[str] = None
    management_type: Optional[str] = None
    merchant_id: Optional[int] = None
    minimum_purchase_unit: Optional[int] = None
    minimum_sales_unit: Optional[int] = None
    origin_country: Optional[str] = None
    sales_measure_units: Optional[str] = None
    tenant_id: Optional[int] = None
    units_per_pallet: Optional[int] = None
    units_per_purchase_package: Optional[int] = None
    units_per_sales_package: Optional[int] = None
    weight: Optional[float] = None
    volume: Optional[float] = None
    length: Optional[float] = None
    height: Optional[float] = None
    width: Optional[float] = None

    # AutomationData
    ITEMS_NAME: str = ""
    USED_KEYS: set = set()


class Item(BaseModel):
    product: Optional[Product] = {}
    batches: Optional[list] = []
    attributes: Optional[dict] = {}
    fulfilled_quantity: Optional[int] = None
    id: Optional[int] = None
    line_order_id: Optional[str] = None
    notes: Optional[str] = None
    product_id: Optional[int] = None
    quantity: Optional[int] = None
    required_date: Optional[str] = None
    sales_item_id: Optional[int] = None
    state: Optional[str] = None

    # AutomationData
    ITEMS_NAME: str = ""
    USED_KEYS: set = set()


class SalesOrder(BaseModel, Blueprint):
    id: int
    items: Optional[List[Item]] = []
    attachments: Optional[list] = []
    third_party_id: Optional[int] = None
    shipping_method: Optional[dict] = {}
    fulfillment_orders: Optional[list] = []
    shipping_method_id: Optional[int] = None
    third_party: Optional[dict] = {}
    is_cart: Optional[bool] = None
    purchase_order_id: Optional[int] = None
    type: Optional[str] = None
    channel: Optional[str] = None
    warehouse_id: Optional[int] = None
    inserted_at: Optional[str] = None
    priority: Optional[int] = None
    updated_at: Optional[str] = None
    merchant_channel_id: Optional[int] = None
    custom_filter_strategy: Optional[str] = None
    warehouse: Optional[dict] = {}
    estimated_total_volume: Optional[float] = None
    process_information: Optional[str] = None
    creator_id: Optional[int] = None
    destination_warehouse_id: Optional[int] = None
    delivery_date: Optional[str] = None
    destination_warehouse: Optional[str] = None
    attributes: Optional[dict] = {}
    ship_to: Optional[ShipTo] = {}
    creator: Optional[dict] = {}
    criterium: Optional[str] = None
    notes: Optional[str] = None
    merchant_id: Optional[int] = None
    estimated_total_weight: Optional[float] = None
    shipment_instructions: Optional[dict] = {}
    service_point_id: Optional[int] = None
    order_num: Optional[str] = None
    missing_stock_items_cancelled: Optional[bool] = None
    custom_filter_strategy_id: Optional[int] = None
    return_labels: Optional[list] = []
    state_transitions: Optional[list] = []
    process_information_id: Optional[int] = None
    state: Optional[str] = None
    packing_location_id: Optional[int] = None

    # AutomationData
    ITEMS_NAME: str = ""
    USED_KEYS: set = set()


################################################################################


class StockLocation(BaseModel):
    id: int
    zone: Optional[dict] = {}
    product_categories: Optional[list] = []
    zone_code: Optional[str] = None
    stock_state: Optional[str] = None
    active: Optional[bool] = None
    actual_location_id: Optional[int] = None
    attributes: Optional[dict] = {}
    code: Optional[str] = None
    current_location_control_id: Optional[int] = None
    deleted_at: Optional[str] = None
    deleted_by: Optional[str] = None
    dimension_depth: Optional[int] = None
    dimension_height: Optional[int] = None
    dimension_weight: Optional[int] = None
    dimension_width: Optional[int] = None
    hallway: Optional[int] = None
    is_defined: Optional[bool] = None
    is_volume: Optional[bool] = None
    level: Optional[int] = None
    location_type_id: Optional[int] = None
    module: Optional[int] = None
    position: Optional[int] = None
    priority: Optional[int] = None
    rack_id: Optional[int] = None
    row: Optional[int] = None
    stock_state_id: Optional[int] = None
    updated_at: Optional[str] = None
    warehouse_id: Optional[int] = None
    zone_id: Optional[int] = None

    # AutomationData
    ITEMS_NAME: str = ""
    USED_KEYS: set = set()


class StockBatch(BaseModel):
    id: int
    product: Optional[Product] = {}
    third_party: Optional[dict] = {}
    client_id: Optional[int] = None
    expiration_date: Optional[str] = None
    number: Optional[str] = None
    product_id: Optional[int] = None
    third_party_id: Optional[int] = None
    type: Optional[str] = None

    # AutomationData
    ITEMS_NAME: str = ""
    USED_KEYS: set = set()


class Stock(BaseModel):
    id: int
    location: Optional[StockLocation] = {}
    product: Optional[Product] = {}
    updated_at: Optional[str] = None
    location_id: Optional[int] = None
    product_id: Optional[int] = None
    merchant_id: Optional[int] = None
    quantity: Optional[int] = None
    batch_id: Optional[int] = None
    stock_state_id: Optional[int] = None
    batch: Optional[StockBatch] = {}
    stock_loading_units: Optional[list] = []

    # AutomationData
    ITEMS_NAME: str = ""
    USED_KEYS: set = set()

################################################################################


class FulfillmentOrder(BaseModel, Blueprint):
    id: int
    items: Optional[List[Item]] = []
    attachments: Optional[list] = []
    sales_order: Optional[dict] = {}
    sales_order_id: Optional[int] = None
    sequence_number: Optional[str] = None
    third_party_id: Optional[int] = None
    shipping_method: Optional[dict] = {}
    shipping_method_id: Optional[int] = None
    third_party: Optional[dict] = {}
    is_cart: Optional[bool] = None
    purchase_order_id: Optional[int] = None
    type: Optional[str] = None
    channel: Optional[str] = None
    warehouse_id: Optional[int] = None
    inserted_at: Optional[str] = None
    priority: Optional[int] = None
    updated_at: Optional[str] = None
    merchant_channel_id: Optional[int] = None
    custom_filter_strategy: Optional[str] = None
    warehouse: Optional[dict] = {}
    estimated_total_volume: Optional[float] = None
    process_information: Optional[dict] = {}
    creator_id: Optional[int] = None
    destination_warehouse_id: Optional[int] = None
    delivery_date: Optional[str] = None
    destination_warehouse: Optional[str] = None
    attributes: Optional[dict] = {}
    ship_to: Optional[ShipTo] = {}
    creator: Optional[dict] = {}
    criterium: Optional[str] = None
    notes: Optional[str] = None
    merchant_id: Optional[int] = None
    estimated_total_weight: Optional[float] = None
    shipment_instructions: Optional[dict] = {}
    service_point_id: Optional[int] = None
    order_num: Optional[str] = None
    missing_stock_items_cancelled: Optional[bool] = None
    custom_filter_strategy_id: Optional[int] = None
    return_labels: Optional[list] = []
    process_information_id: Optional[int] = None
    state: Optional[str] = None
    packing_location_id: Optional[int] = None

    # AutomationData
    ITEMS_NAME: str = ""
    USED_KEYS: set = set()

################################################################################


class User(BaseModel, Blueprint):
    id: int
    product_categories: Optional[list] = []
    tenant: Optional[dict] = {}
    profiles: Optional[list] = []
    merchants: Optional[list] = []
    socket_profiles: Optional[list] = []
    warehouses: Optional[list] = []
    active: Optional[bool] = None
    email: Optional[str] = None
    employee_id: Optional[str] = None
    first_name: Optional[str] = None
    is_billable: Optional[bool] = None
    language: Optional[str] = None
    last_name: Optional[str] = None
    tenant_id: Optional[int] = None
    type: Optional[str] = None
    updated_at: Optional[str] = None
    username: Optional[str] = None

    # AutomationData
    ITEMS_NAME: str = ""
    USED_KEYS: set = set()
