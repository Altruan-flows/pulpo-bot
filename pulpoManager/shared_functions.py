import logging
import json
import pytz
from datetime import datetime, timedelta
from typing import Optional, List
from pulpoFunctions import Pulpo, pulpoClasses
from pulpoFunctions.pulpoError import PulpoError
from . import config


class PulpoUtils:
    """Utility class for Pulpo functions. Contains functions that are used in
    multiple flows."""

    def __init__(self, pulpo: Pulpo, current_time: datetime = None) -> None:
        self.pulpo = pulpo
        if not current_time:
            berlin_tz = pytz.timezone("Europe/Berlin")
            current_time = datetime.now(berlin_tz)
        self.current_time = current_time

    def is_order_prio(self, order: pulpoClasses.FulfillmentOrder) -> bool:
        """Check if the order is a priority order."""
        plz = order.ship_to.address.zip
        # 0-9 Uhr: if PLZ 1-4 and delivery date is in the past.
        if (
            self.current_time.hour < config.YESTERDAY_ORDERS_START_TIME
            and self.current_time.weekday() in config.WORKING_DAYS
            and order.ship_to.address.country_code == config.GERMANY_COUNTRY_CODE
            and plz[0] in config.PLZ_FAR_RANGE
            and self.is_past_delivery_date(order)
        ):
            return True
        # 9-14 Uhr: if delivery date is in the past.
        elif (
            (
                self.current_time.hour >= config.YESTERDAY_ORDERS_START_TIME
                and self.current_time.hour <= config.YESTERDAY_ORDERS_END_TIME
            )
            or self.current_time.weekday() not in config.WORKING_DAYS
        ) and self.is_past_delivery_date(order):
            return True
        # 14-24 Uhr: if PLZ 1-4.
        elif (
            self.current_time.hour > config.YESTERDAY_ORDERS_END_TIME
            and self.current_time.weekday() in config.WORKING_DAYS
            and order.ship_to.address.country_code == config.GERMANY_COUNTRY_CODE
            and plz[0] in config.PLZ_FAR_RANGE
        ):
            return True

        return False

    def is_past_delivery_date(self, order: pulpoClasses.FulfillmentOrder) -> bool:
        """Check if the order is late for delivery. Return True if it is,
        False otherwise.
        """
        # If the delivery date is in the past, the order is late
        delivery_date = order.delivery_date
        if not delivery_date:
            return False
        delivery_date = datetime.strptime(
            delivery_date, config.TIME_FORMAT
        ) + timedelta(hours=config.CORRECTION_HOURS)
        if delivery_date.date() < self.current_time.date():
            return True

        return False

    def cleaner(self) -> None:
        """Cleaner function that deletes picking orders that are in queue and
        have not yet been taken by anyone."""
        for order in self.pulpo.iterator("picking/orders", params={"state": "queue"}):
            if order and not order.get("owner", None):
                try:
                    self.pulpo.askPulpo(
                        endpoint=f"picking/orders/{order['id']}", method="DELETE"
                    )
                    logging.warning(f"Picking order {order['id']} deleted")
                except PulpoError as e:
                    logging.error(f"Error at order {order['id']}: {e}")
                except Exception as e:
                    logging.error(
                        f"An error occurred in Pulpo shared_functions cleaner: {e}"
                    )
        logging.warning("Cleaner finished")

    def create_picking(
        self,
        list_of_ids: list,
        note: str,
        orders_count: int = 1,
        cart: bool = False,
        pickers: list = [],
    ) -> None:
        """Create a picking order in Pulpo for the given list of sales order ids.

        Args:
        - list_of_ids - list of order ids.

        - orders_count - the number of picking order to be created: if this number
        exceeds the number of sales orders, it will create a picking order for
        each sales order and stops when there are no more sales orders.
            - Example: if there are 3 sales orders and orders_count is 5,
            it will create 3 picking orders.

        - cart - if True, creates a cart picking order.
        - pickers - list of pickers' IDs to assign the picking order to.
        """
        # If there is only one order, a single pick is created (no cart)
        if len(list_of_ids) == 1:
            cart = False
        try:
            self.pulpo.askPulpo(
                "picking/orders",
                method="POST",
                body={
                    "sales_orders": list_of_ids,
                    "orders_count": orders_count,
                    "pickers": pickers,
                    "cart": cart,
                    "notes": note,
                },
            )
            logging.warning(f"Picking order with note {note} created for {list_of_ids}")
        except PulpoError as e:
            logging.error(
                f"Error when creating picking order with note {note} "
                f"for {list_of_ids}: {e}"
            )
        except Exception as e:
            logging.error(
                f"An error occurred in Pulpo shared_functions create_picking: {e}"
            )

    def check_availability(self, order: pulpoClasses.FulfillmentOrder) -> bool:
        """Check if the order is available for picking."""
        for item in order.items:
            product_id = item.product.id
            current_stock = self.check_stock(product_id)
            if current_stock < float(item.quantity):
                return False
        return True

    def create_bulk_picking(self, picking_orders: List[dict]) -> None:
        try:
            body = {"picking_orders": picking_orders}
            logging.warning(f"Creating picking order bulk: {body}")
            self.pulpo.askPulpo("picking/orders/bulk", method="POST", body=body)
            logging.warning("Picking order bulk creation finished")
        except PulpoError as e:
            logging.error(f"Error when creating picking orders in a bulk: {e}")
        except Exception as e:
            logging.error(
                f"An error occurred in Pulpo shared_functions create_bulk_picking: {e}"
            )

    def sort_orders(self, unsorted_dict: dict, manufacturer: bool = False) -> dict:
        """Sort the dictionaries by the quantity of the items in the order.

        Args:
        - unsorted_dict: dictionary to be sorted.
        - manufacturer: if True - sorts by the number of different items in the
        order and then by total quantity of the items in the order.
        """
        if not manufacturer:
            sorted_dict = dict(sorted(unsorted_dict.items(), key=lambda item: item[1]))
        else:
            sorted_dict = dict(
                sorted(
                    unsorted_dict.items(), key=lambda x: (len(x[1]), sum(x[1].values()))
                )
            )
        return sorted_dict

    def extract_size(self, order: pulpoClasses.FulfillmentOrder) -> float:
        """Extract the size of the shipment from the tags.
        The tag is in format: "LA_NUM_NUM". Example: "LA_0_5" means that
        label share for the shipment is 0.5.
        """
        float_value = 0.0
        tags = order.criterium.split(",")
        for tag in tags:
            if tag.startswith(config.TAG_IDENTIFIER_LABEL_SHARE):
                try:
                    # Split the string by underscore
                    splitted_string = tag.split("_")
                    # Combine the last two parts of the string
                    last_part = splitted_string[1] + "." + splitted_string[2]

                    # Convert to float
                    float_value = float(last_part)
                except Exception as e:
                    logging.error(f"An error occurred while extracting the size: {e}")
        return float_value

    def define_size_note(self, label_share: float) -> str:
        """Define the note for the order based on the label share.
        Return: the note for the order."""
        if label_share:
            for label, size in sorted(config.LABEL_SHARE_DIVIDERS.items()):
                if label_share <= label:
                    return size
        return config.NOTE_PALETTE

    def update_product(self, product_id: int, dict_to_update: dict) -> None:
        """Update the product in Pulpo with the given dictionary."""
        try:
            response = self.pulpo.askPulpo(
                f"inventory/products/{product_id}", method="PUT", body=dict_to_update
            )
            logging.warning(f"Product {product_id} updated: {response}")
        except PulpoError as e:
            logging.error(
                f"An error occurred in Pulpo shared_functions update_product: {e}. Response: {response}"
            )
        except Exception as e:
            logging.error(
                f"An error occurred in Pulpo shared_functions update_product: {e}. Response: {response}"
            )

    def check_stock(self, product_id: int) -> int:
        """Check the stock for the given product id. Only stock quantities from
        actual storing zones are considered (zones as "Pack41",
        "reception", etc. are ignored)."""
        available_stock = 0
        try:
            stocks = self.pulpo.askPulpo(
                "inventory/stocks", method="GET", params={"product_id": product_id}
            )
            if stocks:
                for stock in stocks:
                    stock = pulpoClasses.Stock(**stock)
                    if stock.location.zone_id in config.WAREHOUSE_ZONES_ALLOWED_FOR_PICKING:
                        available_stock += float(stock.quantity)
        except PulpoError as e:
            logging.error(
                f"An error occurred in Pulpo shared_functions check_stock: {e}."
            )
        except Exception as e:
            logging.error(
                f"An error occurred in Pulpo shared_functions check_stock: {e}."
            )
        return available_stock

    def check_order_suitability(self, order: pulpoClasses.FulfillmentOrder) -> bool:
        """Check if order is suitable for picking orders creation."""
        # Exclude orders that are not in the queue state
        if order.state != config.QUEUE_STATE:
            return False
        # Exclude orders with delivery in the future
        # if self.is_delivery_in_future(order):
        #     return False
        return True

    def suitable_for_cart_creation(
        self, order: pulpoClasses.FulfillmentOrder, is_sweeping_time: bool
    ) -> bool:
        """Check if the order is suitable for cart creation. Return: True if the
        order is suitable for cart creation, False otherwise."""
        # During sweeping time all orders are suitable for carts creation
        if is_sweeping_time:
            return True
        # If order contains products that should be batched, it is not suitable
        # for carts creation
        for item in order.items:
            if item.product.sku in self.skus_to_batch:
                return False
        # Palette orders are not suitable for carts creation
        label_share = self.extract_size(order)
        if label_share >= config.PALETTE_LABEL_SHARE:
            return False
        if order.shipping_method_id in config.SPECIAL_SHIPPING_METHODS:
            return False
        return True

    def check_for_seni(self, order: pulpoClasses.FulfillmentOrder) -> bool:
        """Check if the order contains Seni products. Return: True if the order
        contains Seni products, False otherwise."""
        for item in order.items:
            if item.product.product_categories:
                for category in item.product.product_categories:
                    if category["id"] == config.TZMO_MANUFACTURER:  # Seni products
                        return True
            if config.SENI_PRODUCTS_IDENTIFIER in item.product.name:
                return True
        return False

    def is_delivery_in_future(self, order: pulpoClasses.FulfillmentOrder) -> bool:
        """Check if the delivery day is in the future. Return: True if the
        delivery day is in the future, False otherwise."""
        delivery_date = datetime.strptime(order.delivery_date, config.TIME_FORMAT)
        delivery_date = delivery_date + timedelta(hours=config.CORRECTION_HOURS)
        if delivery_date.date() > self.current_time.date():
            return True
        return False

    def is_order_in_queue(self, order_id: int) -> bool:
        """Check if the sales order is in the correct state for picking orders
        creation. Searches for the fulfillment order with the given sales order
        id and checks if the state is "queue".
        Return: True if the order is in the queue state, False otherwise."""
        try:
            check = self.pulpo.askPulpo(
                "sales/orders/fulfillments",
                method="GET",
                params={"sales_order_id": order_id},
            )
            if check and check[0]["state"] == config.QUEUE_STATE:
                return True
        except PulpoError as e:
            logging.error(
                f"An error occurred in Pulpo shared_functions check_order_state: {e}. Check: {check}"
            )
        except Exception as e:
            logging.error(
                f"An error occurred in Pulpo shared_functions check_order_state: {e}. Check: {check}"
            )
        return False

    def find_user(self, username: str) -> Optional[pulpoClasses.User]:
        """Find the user in Pulpo by the username. Return: User object if found,
        None otherwise."""
        result = self.pulpo.askPulpo("iam/users", params={"username": username})
        if result:
            return pulpoClasses.User(**result[0])
        return None

    def distribute_orders(current_orders: dict) -> str:
        """Get the picker with the least number of orders and return their id."""
        # Create a list of pickers sorted by their current number of orders
        sorted_pickers = sorted(current_orders, key=current_orders.get)

        current_picker = sorted_pickers[0]
        return current_picker

    def find_num_picks_for_user(self, user_id: int) -> int:
        """Find the number of picks for the user."""
        try:
            picks = self.pulpo.askPulpo(
                "picking/orders", params={"state": "queue", "owner_id": user_id}
            )
            return len(picks)
        except PulpoError as e:
            logging.error(
                f"An error occurred in Pulpo shared_functions find_num_picks_for_user: {e}"
            )
        except Exception as e:
            logging.error(
                f"An error occurred in Pulpo shared_functions find_num_picks_for_user: {e}"
            )
        return 0

    def create_picks_per_user_distribution(self, pickers: list) -> dict:
        """Create picking orders for the users based on the distribution.
        Return: Dict {user_id: number_of_picks}."""
        picks_distribution = {}
        for user_id in pickers:
            picks = self.find_num_picks_for_user(user_id)
            picks_distribution[user_id] = picks
        return picks_distribution

    def choose_picker(self, picks_distribution: dict) -> list:
        """Return a list containing the picker for the order. If there is only
        one picker, return the list as is. If there are multiple pickers, return
        a list with the picker that has the least amount of picks assigned."""
        if len(picks_distribution) <= 1:
            return list(picks_distribution.keys())
        else:
            sorted_pickers = dict(
                sorted(picks_distribution.items(), key=lambda item: item[1])
            )
            picker = next(iter(sorted_pickers))
            return [picker]

    @property
    def skus_to_batch(self) -> dict:
        """SKUs with special handling, which should be batched."""
        try:
            with open(config.SKUS_TO_BATCH, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            logging.error(f"File not found: {config.SKUS_TO_BATCH}")
        except json.JSONDecodeError:
            logging.error(f"Invalid JSON in file: {config.SKUS_TO_BATCH}")
        except Exception as e:
            logging.error(f"An error occurred while opening SKU Data: {e}")
        return {}

    # def add_note_to_order(self, sales_order_id: int, note: str) -> None:
    #     """Add a note to the order in Pulpo. Only one note can exist per sales order!"""
    #     try:
    #         self.pulpo.askPulpo(
    #             f"sales/orders/{sales_order_id}", method="PUT", body={"notes": note}
    #         )
    #     except PulpoError as e:
    #         logging.error(f"Error when adding note to order {sales_order_id}: {e}")
    #     except Exception as e:
    #         logging.error(
    #             f"An error occurred in Pulpo shared_functions add_note_to_order: {e}"
    #         )
