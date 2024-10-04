import logging
from datetime import datetime
from typing import List, Dict
from pulpoFunctions import Pulpo
from pulpoFunctions import pulpoClasses
from ..shared_functions import PulpoUtils
from ..note_creator import NoteCreator
from ..config import PackageSizes
from .. import config


class PulpoCartCommon(PulpoUtils):

    """
    This class contains common methods for creating carts.
    """

    def __init__(
        self,
        pulpo: Pulpo,
        orders: List[pulpoClasses.FulfillmentOrder],
        processed_orders: List[int],
        product_stock: Dict[int, float],
        is_prio: bool,
        is_sweeping_time: bool,
        is_running_dry: bool,
        current_time: datetime,
    ) -> None:
        self.pulpo = pulpo
        self.orders = orders
        self.processed_orders = processed_orders
        self.product_stock = product_stock
        self.is_prio = is_prio
        self.is_sweeping_time = is_sweeping_time
        self.is_running_dry = is_running_dry
        self.current_time = current_time
        super().__init__(pulpo=self.pulpo, current_time=self.current_time)
        self.note_creator = NoteCreator(
            pulpo=self.pulpo,
            current_time=self.current_time,
            orders=self.orders,
            is_prio=self.is_prio,
            is_sweeping_time=self.is_sweeping_time,
        )

    def create_cart(
        self,
        new_cart: set,
        size: PackageSizes,
        shelf: str = "",
    ) -> bool:
        """
        Check the cart for the availability of the products. If the cart is more
        than the minimum number of products and less than the maximum number of
        products, create a cart picking order with a note.
        """
        new_cart = list(new_cart)
        cart_minimum = size.value.min
        if self.is_running_dry:
            cart_minimum = cart_minimum * config.RUNNING_DRY_DENOMINATOR
        if self.is_prio and self.is_sweeping_time:
            cart_minimum = config.SWEEPING_MIN_ORDERS
        cart = True
        if len(new_cart) >= cart_minimum and len(new_cart) <= size.value.max:
            # Create a base note for the cart.
            note = self.note_creator.create_note(
                list_of_ids=new_cart, size_note=size.value.note, shelf=shelf
            )
            try:
                # Create a cart picking order.
                self.create_picking(
                    list_of_ids=new_cart,
                    note=note,
                    orders_count=1,
                    cart=cart,
                )
                return True
            except Exception as e:
                logging.error(
                    f"Error when creating cart picking order in PulpoCartsManager: {e}"
                )
        return False

    # def create_base_note(
    #     self,
    #     size: str,
    #     new_cart: list,
    # ) -> str:
    #     """Create a base note for the cart."""
    #     base_note = f"{config.BASE_NOTE}:"
    #     special_note = None

    #     # Add note if contains Seni products
    #     if self.contains_seni_products(new_cart):
    #         base_note = base_note + f" {config.NOTE_SENI}"

    #     # Add priority note if the priority orders are being processed.
    #     if self.is_prio:
    #         base_note = self.create_priority_note(base_note)

    #     if self.is_prio and self.is_sweeping_time:
    #         base_note = base_note + f" {config.NOTE_SWEEPER}"

    #     # Check if the order has a special shipping method. If yes, create
    #     # a special note for the cart.
    #     first_order = new_cart[0]
    #     special_note = self.create_special_note(first_order)

    #     if size == config.NOTE_PALETTE and special_note:
    #         base_note = base_note + f" {special_note}"
    #     else:
    #         base_note = base_note + f" {size}"
    #     return base_note

    # def create_special_note(self, first_order: int) -> Optional[str]:
    #     """Check if the order has a special shipping method."""
    #     order = None
    #     for order_entity in self.orders:
    #         if order_entity.sales_order_id == first_order:
    #             order = order_entity
    #     if order:
    #         if order.shipping_method_id == config.ABHOLUNG:
    #             return config.NOTE_ABHOLUNG
    #         elif order.shipping_method_id == config.DB_SCHENKER:
    #             return config.NOTE_DB_SCHENKER
    #     return None

    def is_order_fully_available(
        self, all_products: dict, order_to_check: pulpoClasses.FulfillmentOrder
    ) -> list:
        """Check the availability of the products in the new cart."""
        for item in order_to_check.items:
            if item.product.id not in self.product_stock:
                product_stock = self.check_stock(item.product.id)
                self.product_stock[item.product.id] = product_stock
            else:
                product_stock = self.product_stock[item.product.id]
            quantity_in_cart = float(item.quantity) + all_products.get(
                item.product.id, 0
            )
            if product_stock < quantity_in_cart:
                logging.warning(f"Order {order_to_check.order_num} not available")
                return False
        return True

    def update_products_dictionary(
        self, all_products: dict, order_to_add: pulpoClasses.FulfillmentOrder
    ) -> None:
        """Update the dictionary of all products with the new products from the order."""
        for item in order_to_add.items:
            if item.product.id in all_products:
                all_products[item.product.id] += float(item.quantity)
            else:
                all_products[item.product.id] = float(item.quantity)
        return all_products

    def update_stock_dictionary(self, cart: list) -> None:
        """Update the dictionary of product stock after the cart is created."""
        for order_id in cart:
            for order in self.orders:
                if order_id == order.sales_order_id:
                    for item in order.items:
                        if item.product.id in self.product_stock:
                            self.product_stock[item.product.id] -= float(item.quantity)
