import logging
from typing import List, Dict
from datetime import datetime
from pulpoFunctions import Pulpo
from pulpoFunctions import pulpoClasses
from .common import PulpoCartCommon
from ..config import PackageSizes, RUNNING_DRY_DENOMINATOR


class CartsCreatorShelves(PulpoCartCommon):
    """
    This class is responsible for creating carts based on the shelves. If there
    are enough orders that have products from the same shelf, a cart is created.
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
        shelves_index: Dict[str, set],
        current_time: datetime,
    ) -> None:
        self.pulpo = pulpo
        self.pulpo = pulpo
        self.orders = orders
        self.processed_orders = processed_orders
        self.product_stock = product_stock
        self.is_prio = is_prio
        self.is_sweeping_time = is_sweeping_time
        self.shelves_index = shelves_index
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
        logging.warning(f"Processing {size.name}")
        shelves_frequency = self.find_total_shelves_frequency()
        logging.info(f"Shelves frequency: {shelves_frequency} for {size.name}")
        selected_shelves = self.select_shelves(shelves_frequency, size.value.min)
        if selected_shelves:
            logging.info(f"Selected shelves: {selected_shelves} for {size.name}")
            space_left = self.generate_carts(selected_shelves, space_left, size)
        return space_left

    def generate_carts(
        self,
        shelves: list,
        space_left: int,
        size: PackageSizes,
    ) -> None:
        """Iterate through the selected shelves and create carts."""
        for shelf in shelves:
            # If no more space left, stop creating carts.
            if space_left == 0:
                break
            # Get ids of all the products that are on the shelf.
            products_from_the_shelf = self.shelves_index[shelf]
            # Refresh the cart.
            new_cart = set()
            new_cart = self.fill_cart_from_shelf(
                new_cart, size.value.max, products_from_the_shelf
            )
            if new_cart:
                cart_created = self.create_cart(
                    new_cart=new_cart, size=size, shelf=shelf
                )
                if cart_created:
                    space_left -= 1
                    self.processed_orders.extend(new_cart)
                    self.update_stock_dictionary(new_cart)
        return space_left

    def fill_cart_from_shelf(
        self,
        new_cart: set,
        max_cart_size: int,
        products_from_the_shelf: set,
    ) -> set:
        """Fill the cart with orders."""
        all_products_in_cart = {}
        for order in self.orders:
            # If the cart is full, stop adding orders to it.
            if len(new_cart) >= max_cart_size:
                break
            if (
                order.sales_order_id not in self.processed_orders
                and order.sales_order_id not in new_cart
                and self.order_has_products_on_shelf(order, products_from_the_shelf)
                and self.is_order_fully_available(all_products_in_cart, order)
            ):
                new_cart.add(order.sales_order_id)
                all_products_in_cart = self.update_products_dictionary(
                    all_products_in_cart, order
                )
        return new_cart

    def order_has_products_on_shelf(
        self, order: pulpoClasses.FulfillmentOrder, products_from_the_shelf: set
    ) -> bool:
        """Check if the order has products on the shelf."""
        for item in order.items:
            if item.product.id in products_from_the_shelf:
                return True
        return False

    def select_shelves(self, shelves: Dict[str, int], minimum_orders: int) -> List[str]:
        """Select shelves that have more than the minimum number of orders."""
        if self.is_running_dry:
            minimum_orders = minimum_orders * RUNNING_DRY_DENOMINATOR
        selected_shelves = []
        for shelf in shelves:
            if shelves[shelf] >= minimum_orders:
                selected_shelves.append(shelf)
        return selected_shelves

    def find_total_shelves_frequency(self) -> Dict[str, int]:
        """Find the total frequency of shelves for the list of orders.
        Return the dictionary of shelves sorted by frequency in descending order.
        The dictionary is in the format: {shelf: frequency}."""
        shelves_frequency = {}
        for order in self.orders:
            shelves_per_order = self.find_shelves_frequency_per_order(order)
            for shelf in shelves_per_order:
                if shelf in shelves_frequency:
                    shelves_frequency[shelf] += 1
                else:
                    shelves_frequency[shelf] = 1
        shelves_frequency = dict(
            sorted(shelves_frequency.items(), key=lambda x: x[1], reverse=True)
        )
        return shelves_frequency

    def find_shelves_frequency_per_order(
        self, order: pulpoClasses.FulfillmentOrder
    ) -> set:
        """Find all shelves that associate with the order. Return the set of shelves."""
        shelves_per_order = set()
        for item in order.items:
            for shelf, products in self.shelves_index.items():
                if item.product.id in products:
                    shelves_per_order.add(shelf)
        return shelves_per_order
