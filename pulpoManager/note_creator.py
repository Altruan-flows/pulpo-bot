import logging
from typing import List
from datetime import datetime
from pulpoFunctions import pulpoClasses, Pulpo
from .shared_functions import PulpoUtils
from . import config


class NoteCreator(PulpoUtils):
    """
    This class is responsible for creating notes for the picking orders in Pulpo.

    Attributes:
    - current_time: current time in Berlin timezone.
    - orders: list of orders that are being used as a base for creation of the
    picking order. The sole purpose of this is to get access to FulfillmentOrder
    object of a certain order (since list_of_ids contains only order ids).
    - is_prio: boolean value that indicates if the orders are prio orders.
    - is_batch: boolean value that indicates if the orders are batch orders.
    - is_sweeping_time: boolean value that indicates if it is the time to sweep
    the orders (process all orders that are in queue). The sweeping time is
    chosen based on the time the shipping LKV is going out of the warehouse.
    """

    def __init__(
        self,
        pulpo: Pulpo,
        current_time: datetime,
        orders: List[pulpoClasses.FulfillmentOrder],
        is_prio: bool = False,
        is_batch: bool = False,
        is_sweeping_time: bool = False,
    ) -> None:
        self.pulpo = pulpo
        self.current_time = current_time
        self.orders = orders
        self.is_prio = is_prio
        self.is_batch = is_batch
        self.sweeping_time = is_sweeping_time
        super().__init__(pulpo=self.pulpo, current_time=self.current_time)

    def create_note(
        self,
        list_of_ids: list,
        single_order: pulpoClasses.FulfillmentOrder = None,
        size_note: str = None,
        batched_quantity: int = None,
        batched_product: str = None,
        shelf: str = None,
    ) -> str:
        """
        Main function to create a note for the picking order. The note creation
        is consisted of multiple blocks that are added to the base note in a
        specific order.
        """
        note = config.BASE_NOTE
        if not size_note and single_order:
            size_note = self.get_size_note(single_order)
        # Contains Seni products
        if self.contains_seni_products(list_of_ids):
            note += f" {config.NOTE_SENI}"
        # Prio / Non-prio
        if single_order and single_order.priority > config.NORMAL_PRIORITY_VALUE:
            note += f" {config.NOTE_PRIO} {single_order.priority}"
        elif self.is_prio:
            note += f" {self.create_base_of_priority_note()}"
        # Batch
        if self.is_batch:
            note += f" {config.NOTE_BATCH}"
        # Special shipping method
        if single_order and self.add_special_shipping_method(single_order):
            note += f" {self.add_special_shipping_method(single_order)}"
        # Partnerkunde
        if single_order and single_order.channel in config.PARTNERKUNDE_SALES_CHANNELS:
            note += f" {config.NOTE_PARTNERKUNDE}"
        # Rest
        if self.sweeping_time and self.is_prio:
            note += f" {config.NOTE_SWEEPER}"
        # Size
        if size_note:
            note += f" {size_note}"
        # Batched quantity
        if batched_quantity and batched_product:
            note += f" {batched_quantity} {batched_product}"
        # Shelf
        if shelf:
            note += f" {shelf}"
        # Number of orders in the pick (for sweeping time only)
        if self.sweeping_time and self.is_prio:
            note += f" {len(list_of_ids)}"
        logging.info(f"Created note: {note}")
        return note

    def add_special_shipping_method(self, order: pulpoClasses.FulfillmentOrder) -> str:
        """Get the base note for the order."""
        if order.shipping_method_id == config.ABHOLUNG:
            return config.NOTE_ABHOLUNG
        elif order.shipping_method_id == config.DB_SCHENKER:
            return config.NOTE_DB_SCHENKER
        elif order.shipping_method_id == config.ALTRUAN_LIEFERDIENST:
            return config.NOTE_ALTRUAN_LIEFERDIENST
        elif order.shipping_method_id == config.DB_SCHENKER_EUROPALETTE:
            return config.NOTE_PALETTE
        return None

    def get_size_note(self, order: pulpoClasses.FulfillmentOrder) -> str:
        """Define size note based on the order size."""
        size = self.extract_size(order)
        size_note = self.define_size_note(size)
        return size_note

    def create_base_of_priority_note(self) -> str:
        """Create a priority note for the cart."""
        if (
            self.current_time.hour >= config.YESTERDAY_ORDERS_START_TIME
            and self.current_time.hour <= config.YESTERDAY_ORDERS_END_TIME
        ) or self.current_time.weekday() not in config.WORKING_DAYS:
            return config.NOTE_YESTERDAY
        return config.NOTE_PLZ_FAR_RANGE

    def contains_seni_products(
        self,
        cart: list,
    ) -> bool:
        """Check if there is even one order in the cart that contains Seni products."""
        for order_id in cart:
            for order in self.orders:
                if order_id == order.sales_order_id:
                    if self.check_for_seni(order):
                        return True
        return False
