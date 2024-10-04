import logging
import math
from datetime import datetime
from typing import List, Dict
from pulpoFunctions import Pulpo
from pulpoFunctions import pulpoClasses
from .common import PulpoCartCommon
from ..config import PackageSizes


class CartsCreatorRandom(PulpoCartCommon):
    """
    This class is responsible for creating carts randomly. If there are enough
    orders that can be added to a cart, a cart is created.
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
        self.pulpo = pulpo
        self.orders = orders
        self.processed_orders = processed_orders
        self.product_stock = product_stock
        self.is_prio = is_prio
        self.is_sweeping_time = is_sweeping_time
        self.is_running_dry = is_running_dry
        super().__init__(
            pulpo=self.pulpo,
            orders=self.orders,
            processed_orders=self.processed_orders,
            product_stock=self.product_stock,
            is_prio=self.is_prio,
            is_sweeping_time=self.is_sweeping_time,
            is_running_dry=self.is_running_dry,
            current_time=current_time,
        )

    def main(
        self,
        size: PackageSizes,
        space_left: int,
    ) -> int:
        """Handle the size threshold for the given sizes tuple."""
        logging.warning(f"Processing size {size.name}")
        space_left = self.fill_cart_randomly(space_left, size)

        return space_left

    def fill_cart_randomly(
        self,
        space_left: int,
        size: PackageSizes,
    ) -> set:
        """Fill the cart with orders randomly."""
        all_products_in_cart = {}
        logging.warning(f"Processing size {size.name} with {len(self.orders)} orders")

        number_of_carts = math.ceil(len(self.orders) / size.value.max)
        if self.is_prio and self.is_sweeping_time:
            number_of_carts = math.ceil(len(self.orders) / size.value.max)

        logging.warning(f"Number of carts that can be created: {number_of_carts}")

        for num in range(int(number_of_carts) + 1):
            new_cart = set()
            for order in self.orders:
                if len(new_cart) >= size.value.max:
                    break
                if (
                    order.sales_order_id not in self.processed_orders
                    and order.sales_order_id not in new_cart
                    and self.is_order_fully_available(all_products_in_cart, order)
                ):
                    new_cart.add(order.sales_order_id)
                    all_products_in_cart = self.update_products_dictionary(
                        all_products_in_cart, order
                    )
            if new_cart:
                cart_created = self.create_cart(new_cart=new_cart, size=size, shelf="")
                if cart_created:
                    space_left -= 1
                    self.processed_orders.extend(new_cart)
                    self.update_stock_dictionary(new_cart)
            return space_left
