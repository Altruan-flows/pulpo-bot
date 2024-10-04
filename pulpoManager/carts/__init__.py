import logging
from datetime import datetime
from typing import List
from pulpoFunctions import Pulpo
from pulpoFunctions import pulpoClasses
from ..shared_functions import PulpoUtils
from ..config import PackageSizes
from .. import config
from .process_shelves import CartsCreatorShelves
from .process_random import CartsCreatorRandom


class PulpoCartsManager(PulpoUtils):
    """
    This class is responsible for creating carts and palette orders in Pulpo.
    1 Cart = 1 Size.

    1. First, the space left is checked and the orders of the given size are selected.

    2. If there are orders for this size and there is space left, or it is sweeping
    time, the carts are created based on the shelves. If by the end of the process
    there is still space left, the carts are created randomly.

    3. Creation of carts:
        - The number of carts is limited by the space left (PACKAGE_SIZE_THRESHOLDS).
        - All orders of the given size are found.
        - The frequency of shelves is calculated (if an article is on several
        shelves, all shelves are considered).Only unique shelves
        are considered (one set of shelves per order). If one shelf has more than
        the minimum number of orders, it is selected.
        - Carts are created for the selected shelves. Each cart has a maximum
        number of orders that can be added to it.
        - Each cart has a note in the format: "Bot: <size> <number of orders> <shelf>"
        if the cart is created based on the shelves. If the cart is created randomly,
        the note is in the format: "Bot: <size> <number of orders> Rest".

    NB! Orders of size more than palette are processed separately.
    """

    def __init__(
        self,
        pulpo: Pulpo,
        shelves_index: dict,
        current_time: datetime,
        is_running_dry: bool = False
    ) -> None:
        self.pulpo = pulpo
        self.orders = []
        self.processed_orders = []
        self.is_prio = False
        self.is_sweeping_time = False
        self.is_running_dry = is_running_dry
        self.current_time = current_time
        super().__init__(pulpo=self.pulpo)
        self.shelves_index = shelves_index
        self.no_space_left = False
        # self.create_shelves_index()

    def main(
        self,
        size: PackageSizes,
        orders: List[pulpoClasses.FulfillmentOrder],
        is_prio: bool,
        is_sweeping_time: bool,
        product_stock: dict,
    ) -> None:
        """Main function that separates the orders into carts."""
        self.is_prio = is_prio
        self.is_sweeping_time = is_sweeping_time
        self.orders = orders
        self.product_stock = product_stock

        space_left = self.check_space()
        orders_to_process = self.select_orders_by_size(size.value.note)
        logging.warning(f"Space left: {space_left}")
        if (
            orders_to_process
            and (space_left > 0 or self.is_sweeping_time)
        ):
            carts_creator_shelves = CartsCreatorShelves(
                pulpo=self.pulpo,
                orders=orders_to_process,
                processed_orders=self.processed_orders,
                product_stock=self.product_stock,
                is_prio=self.is_prio,
                is_sweeping_time=self.is_sweeping_time,
                is_running_dry=self.is_running_dry,
                shelves_index=self.shelves_index,
                current_time=self.current_time,
            )
            space_left = carts_creator_shelves.main(size=size, space_left=space_left)
            self.processed_orders.extend(carts_creator_shelves.processed_orders)
            self.product_stock = carts_creator_shelves.product_stock
            logging.warning(
                f"Space left after processing {size.name} orders: {space_left}"
            )
            if space_left > 0:
                logging.warning("Still space left. Carts will be created randomly.")
                orders_to_process = self.remove_processed_orders(orders_to_process)
                carts_creator_random = CartsCreatorRandom(
                    pulpo=self.pulpo,
                    orders=orders_to_process,
                    processed_orders=self.processed_orders,
                    product_stock=self.product_stock,
                    is_prio=self.is_prio,
                    is_sweeping_time=self.is_sweeping_time,
                    is_running_dry=self.is_running_dry,
                    current_time=self.current_time,
                )
                carts_creator_random.main(size=size, space_left=space_left)

    def remove_processed_orders(
        self, orders: List[pulpoClasses.FulfillmentOrder]
    ) -> None:
        """Remove processed orders from the list of orders."""
        for order in reversed(orders):
            if order.sales_order_id in self.processed_orders:
                orders.remove(order)
        return orders

    def select_orders_by_size(self, size: str) -> List[pulpoClasses.FulfillmentOrder]:
        """Select the orders for the given size. Return the list of orders to process."""
        orders_to_process = []
        for order in self.orders:
            if order.sales_order_id not in self.processed_orders:
                note = None
                # Try to define size by label share.
                label_share = self.extract_size(order)
                if label_share:
                    note = self.define_size_note(label_share)

                if note and note == size:
                    orders_to_process.append(order)

        return orders_to_process

    def check_space(self) -> int:
        """Check the space left for the carts creation. The left space is defined
        by the maximum threshold for prio/non-prio orders minus the number of
        picking orders. The space left is returned."""
        if self.is_prio:
            return config.PRIO_THRESHOLD
        left_space = 0
        count_picking_orders = self.check_picking()
        logging.warning(f"Found {count_picking_orders} picking orders")
        left_space = config.NON_PRIO_THRESHOLD - count_picking_orders
        if left_space < 0:
            self.no_space_left = True
        return left_space

    def check_picking(self) -> int:
        """Check the number of picking orders in "queue" and "taken" states."""
        orders_counter = 0
        for state in config.PICKING_STATES:
            check = self.pulpo.askPulpo(
                "picking/orders",
                params={"limit": config.DEFAULT_PAGE_SIZE, "state": state},
            )
            for order in check:
                orders_counter += 1
        return orders_counter

    # def create_shelves_index(self) -> None:
    #     """Create the index of shelves."""
    #     logging.info("Creating shelves index...")
    #     shelves_index_creator = PulpoShelvesIndexCreator(pulpo=self.pulpo)
    #     shelves_index_creator.main()
    #     self.shelves_index = shelves_index_creator.shelves_index
    #     self.all_products = shelves_index_creator.all_products
    #     logging.warning("Shelves index created.")

    # def create_cart(
    #     self,
    #     new_cart: set,
    #     size: PackageSizes,
    #     shelf: str = "",
    # ) -> bool:
    #     """
    #     Check the cart for the availability of the products. If the cart is more
    #     than the minimum number of products and less than the maximum number of
    #     products, create a cart picking order with a note.
    #     """
    #     new_cart = list(new_cart)
    #     cart_minimum = size.value.min
    #     if self.is_prio and self.is_sweeping_time:
    #         cart_minimum = config.SWEEPING_MIN_ORDERS
    #     cart = True
    #     if len(new_cart) >= cart_minimum and len(new_cart) <= size.value.max:
    #         # Create a base note for the cart.
    #         base_note = self.create_base_note(size, new_cart)
    #         # If the size is XXL (Palette), do not create a cart picking order.
    #         if size == config.NOTE_XXL:
    #             cart = False
    #         try:
    #             # Create a cart picking order.
    #             self.create_picking(
    #                 list_of_ids=new_cart,
    #                 note=f"{base_note} {len(new_cart)} {shelf}",
    #                 orders_count=1,
    #                 cart=cart,
    #             )
    #             return True
    #         except Exception as e:
    #             logging.error(
    #                 f"Error when creating cart picking order in PulpoCartsManager: {e}"
    #             )
    #     return False

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
    #     if self.is_prio or self.contains_priority_orders(new_cart):
    #         if (
    #             self.current_time.hour >= config.CLOSE_RANGE_START_TIME
    #             and self.current_time.hour <= config.CLOSE_RANGE_END_TIME
    #         ):
    #             base_note = base_note + f" {config.NOTE_YESTERDAY}"
    #         else:
    #             base_note = base_note + f" {config.NOTE_PLZ_FAR_RANGE}"

    #     if self.is_prio and self.is_sweeping_time:
    #         base_note = base_note + f" {config.NOTE_SWEEPER}"

    #     # Check if the order has a special shipping method. If yes, create
    #     # a special note for the cart.
    #     first_order = new_cart[0]
    #     special_note = self.create_special_note(first_order)

    #     if size == config.NOTE_XXL and special_note:
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

    # def contains_priority_orders(self, cart: list) -> bool:
    #     """Check if there is even one priority order in the cart."""
    #     for order_id in cart:
    #         for order in self.prio_orders:
    #             if order_id == order.sales_order_id:
    #                 return True
    #     return False

    # def contains_seni_products(self, cart: list) -> bool:
    #     """Check if there is even one order in the cart that contains Seni products."""
    #     for order_id in cart:
    #         for order in self.orders:
    #             if order_id == order.sales_order_id:
    #                 if self.check_for_seni(order):
    #                     return True
    #     return False

    # def is_order_fully_available(
    #     self, all_products: dict, order_to_check: pulpoClasses.FulfillmentOrder
    # ) -> list:
    #     """Check the availability of the products in the new cart."""
    #     for item in order_to_check.items:
    #         if item.product.id not in self.product_stock:
    #             product_stock = self.check_stock(item.product.id)
    #             self.product_stock[item.product.id] = product_stock
    #         else:
    #             product_stock = self.product_stock[item.product.id]
    #         quantity_in_cart = float(item.quantity) + all_products.get(
    #             item.product.id, 0
    #         )
    #         if product_stock < quantity_in_cart:
    #             return False
    #     return True

    # def update_products_dictionary(
    #     self, all_products: dict, order_to_add: pulpoClasses.FulfillmentOrder
    # ) -> None:
    #     """Update the dictionary of all products with the new products from the order."""
    #     for item in order_to_add.items:
    #         if item.product.id in all_products:
    #             all_products[item.product.id] += float(item.quantity)
    #         else:
    #             all_products[item.product.id] = float(item.quantity)
    #     return all_products

    # def update_stock_dictionary(self, cart: list) -> None:
    #     """Update the dictionary of product stock after the cart is created."""
    #     for order_id in cart:
    #         for order in self.orders:
    #             if order_id == order.sales_order_id:
    #                 for item in order.items:
    #                     if item.product.id in self.product_stock:
    #                         self.product_stock[item.product.id] -= float(item.quantity)
