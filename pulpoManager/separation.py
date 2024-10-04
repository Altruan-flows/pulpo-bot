import logging
from datetime import datetime
from pulpoFunctions import Pulpo
from pulpoFunctions import pulpoClasses
from .shared_functions import PulpoUtils
from .note_creator import NoteCreator
from . import config


class PulpoSeparator(PulpoUtils):
    """
    This class is responsible for separating orders in Pulpo into different lists.
    It is also responsible for creating single picks for Partnerkunde, Palette
    and orders with priority higher than the set value.

    The separation is based on the following criteria:
    - priority,
    - suitable for batch creation,
    - suitable for cart creation,
    - containing Seni products.

    Batch orders contain all orders, main filtering is done inside the batching
    flow.
    Cart orders contain only orders that are suitable for cart creation. All
    orders are suitable for cart creation during sweeping hours.
    Prio orders are not mixed with non-prio orders.
    Seni orders are not mixed with non-Seni orders.
    """

    def __init__(
        self,
        pulpo: Pulpo,
        is_sweeping_time: bool,
        pickers: dict,
        current_time: datetime,
        product_stock: dict,
    ) -> None:
        self.pulpo = pulpo
        self.is_sweeping_time = is_sweeping_time
        self.pickers = pickers
        self.current_time = current_time
        self.product_stock = product_stock
        self.orders_count = 0
        super().__init__(pulpo=self.pulpo, current_time=self.current_time)

        self.prio_orders_for_batches = []
        self.prio_orders_without_seni = []
        self.seni_prio_orders = []

        self.orders_for_batches = []
        self.orders_without_seni = []
        self.seni_orders = []

        self.get_picks_distribution()

    def get_picks_distribution(self) -> dict:
        """Get picks distribution for Partnerkunden and Palette pickers."""
        self.partnerkunde_pickers = self.pickers["Partnerkunden"]
        self.partnerkunde_pickers_distribution = (
            self.create_picks_per_user_distribution(self.partnerkunde_pickers)
        )
        self.palette_pickers = self.pickers["Palettenversand"]
        self.palette_pickers_distribution = self.create_picks_per_user_distribution(
            self.palette_pickers
        )

    def main(self) -> None:
        """Main function that iterates through the orders in Pulpo
        and separates them into lists based on the set criteria.

        Important: it is necessary to iterate through fulfillment orders, since
        only they have the correct state of the order. When an order is paused
        in Pulpo, it will not reflect in the sales/orders endpoint, only
        the fulfillment orders will have the correct state.
        """
        for order in self.pulpo.iterator(
            "sales/orders/fulfillments", params={"state": "queue"}
        ):
            try:
                self.order = pulpoClasses.FulfillmentOrder(**order)
                if self.check_order_suitability(
                    self.order
                ) and self.check_availability_locally(self.order):
                    self.orders_count += 1  # count all orders in the queue: necessary for running dry calculation
                    prio = self.is_order_prio(self.order)
                    contains_seni = self.check_for_seni(self.order)
                    suitable_for_carts = self.suitable_for_cart_creation(
                        self.order, self.is_sweeping_time
                    )
                    single_pick_created = self.single_picks_creation(is_prio=prio)
                    if not single_pick_created:
                        if prio:
                            # All priority orders are added to the prio_orders_for_batches.
                            self.prio_orders_for_batches.append(self.order)
                            if suitable_for_carts:
                                # All orders suitable for carts are separated into two groups:
                                # containing Seni products and not containing Seni products.
                                if contains_seni:
                                    self.seni_prio_orders.append(self.order)
                                else:
                                    self.prio_orders_without_seni.append(self.order)

                        else:
                            # All non-prio orders are added to the orders_for_batches list.
                            self.orders_for_batches.append(self.order)
                            if suitable_for_carts:
                                # All orders suitable for carts are separated into two groups:
                                # containing Seni products and not containing Seni products.
                                if contains_seni:
                                    self.seni_orders.append(self.order)
                                else:
                                    self.orders_without_seni.append(self.order)

            except Exception as e:
                logging.error(f"An error occurred in PulpoSeparator main: {e}")
                continue

    def single_picks_creation(self, is_prio: bool) -> bool:
        """Create single pick. Return True if a pick was created, False otherwise."""
        label_share = self.extract_size(self.order)
        # If sales channel is Partnerkunde
        if self.order.channel in config.PARTNERKUNDE_SALES_CHANNELS:
            logging.warning(f"Order {self.order.sales_order_id} is Partnerkunde.")
            picker_id = self.create_assigned_picking(
                order=self.order,
                pickers=self.partnerkunde_pickers,
                pickers_distribution=self.partnerkunde_pickers_distribution,
                is_prio=is_prio,
            )
            if picker_id:
                self.partnerkunde_pickers_distribution[picker_id] += 1
                return True

        # If priority value is higher than the set value
        elif self.order.priority > config.NORMAL_PRIORITY_VALUE:
            logging.warning(f"Order {self.order.sales_order_id} is Prio.")
            note_creator = NoteCreator(
                pulpo=self.pulpo, current_time=self.current_time, orders=[self.order]
            )
            note = note_creator.create_note(
                list_of_ids=[self.order.sales_order_id],
                single_order=self.order,
            )
            self.create_picking(
                list_of_ids=[self.order.sales_order_id],
                note=note,
                cart=False,
            )
            return True

        elif (
            label_share >= config.PALETTE_LABEL_SHARE
            or self.order.shipping_method_id in config.SPECIAL_SHIPPING_METHODS
        ):
            logging.warning(f"Order {self.order.sales_order_id} is Palette.")
            picker_id = self.create_assigned_picking(
                order=self.order,
                pickers=self.palette_pickers,
                pickers_distribution=self.palette_pickers_distribution,
                is_prio=is_prio,
                size_note=config.NOTE_PALETTE,
            )
            if picker_id:
                self.palette_pickers_distribution[picker_id] += 1
                return True
        return False

    def create_assigned_picking(
        self,
        order: pulpoClasses.FulfillmentOrder,
        pickers: list,
        pickers_distribution: dict,
        size_note: str = None,
        is_prio: bool = False,
    ) -> str:
        """Create a single pick for Partnerkunde orders. Return id of the picker
        assigned to the order."""
        # Here sweeping time is not considered since Palette and Partnerkunde orders:
        # 1) have no upper limit;
        # 2) only one order is picked at a time (1 order = 1 pick).
        note_creator = NoteCreator(
            pulpo=self.pulpo,
            current_time=self.current_time,
            orders=[order],
            is_prio=is_prio,
        )
        note = note_creator.create_note(
            list_of_ids=[order.sales_order_id], single_order=order, size_note=size_note
        )
        # If there is only one picker or no picker, just use the list. Assigning
        # an empty list to pickers will leave the pick unassigned.
        if len(pickers) <= 1:
            self.create_picking(
                list_of_ids=[order.sales_order_id],
                note=note,
                cart=False,
                pickers=self.partnerkunde_pickers,
            )
            return self.partnerkunde_pickers[0]
        else:
            picker = self.choose_picker(pickers_distribution)
            self.create_picking(
                list_of_ids=[order.sales_order_id],
                note=note,
                cart=False,
                pickers=picker,
            )
            return picker[0]
        return None

    def check_availability_locally(self, order: pulpoClasses.FulfillmentOrder) -> bool:
        """Check if all products in the order are available in the warehouse."""
        for item in order.items:
            if item.product_id not in self.product_stock:
                return False
            if self.product_stock[item.product_id] >= float(item.quantity):
                return True
        return False
