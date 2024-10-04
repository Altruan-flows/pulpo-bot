import logging
from typing import Dict, List
from datetime import datetime
from pyWeclapp import weclappClasses, weclapp
from util import customAttributes  # custom file, not in the repo
from pulpoFunctions import Pulpo
from pulpoFunctions import pulpoClasses
from .shared_functions import PulpoUtils
from .note_creator import NoteCreator
from . import config


class PulpoBatchingManager(PulpoUtils):
    """
    This class is responsible for batching orders in Pulpo.
    1 Batch = 1 SKU (multiple orders).

    1. Iterate through the orders with 1 SKU that are in queue and count
    total quantity of orders for each SKU.
    If the quantity of orders is greater than the MIN_BATCH_SIZE, add the product
    to the list of products to batch.

    2. Iterate through the list of products to batch and create picking batches.
    Batching logic is different for special SKUs and regular SKUs.

    - For special SKUs a separate run through the orders is done. If the total
    quantity of items in the orders is greater than the separate_batch_from value,
    this order will not be included in the batch -> a separate palette picking
    order is created with the note "Bot Palette: <batched_quantity> <product_name>".

    - All the rest orders and orders with regular SKUs are batched based on the
    max value of one palette. Field "Einheiten pro Palette" is used to determine
    the maximum number of items per palette. If this field is not filled in Pulpo,
    the information is taken from WeClapp. If WeClapp does not have this
    information, a message is sent to Teams and the batch maximum size is
    set to infinity.

    3. The stock is checked before batching. If the stock is not enough to fulfill
    all orders, the batch is created with the available stock.

    4. If the total quantity is greater than the maximum number of items per palette,
    the orders are split into multiple batches. Too small batches are not created.

    5. The batch is created with the note with the following structure:
    "Bot Batch: <batched_quantity> <product_name>".
    """

    def __init__(self, pulpo: Pulpo, current_time: datetime, is_running_dry: bool = False) -> None:
        self.pulpo = pulpo
        self.current_time = current_time
        self.cat = customAttributes.CAT()
        self.orders = {}
        self.product_name = ""
        self.processed_orders = set()
        self.special_ids_to_batch = [sku["id"] for sku in self.skus_to_batch.values()]
        self.picking_orders = []
        self.orders_to_include = []
        self.seni_ids = []
        self.is_running_dry = is_running_dry
        super().__init__(pulpo=self.pulpo, current_time=self.current_time)

    def main(
        self,
        orders_to_include: List[pulpoClasses.FulfillmentOrder],
        is_prio: bool,
        product_stock: dict,
    ) -> None:
        """Main function that iterates through list of SKUs, iterates through
        the orders that contain this SKU and creates picking batches."""
        self.orders_to_include = orders_to_include
        self.is_prio = is_prio
        self.product_stock = product_stock
        self.note_creator = NoteCreator(
            pulpo=self.pulpo,
            current_time=self.current_time,
            orders=self.orders_to_include,
            is_prio=is_prio,
            is_batch=True,
        )
        try:
            logging.info("Starting batching flow.")
            product_ids_to_batch = self.find_products_to_batch()
            logging.warning(f"Found {product_ids_to_batch} products to batch.")
            for product_id in product_ids_to_batch:
                self.batching_products(product_id=product_id)
            # if self.picking_orders:
            #     self.create_bulk_picking(self.picking_orders)
        except Exception as e:
            logging.error(f"An error occurred in PulpoBatchingManager main: {e}")

    def batching_products(self, product_id: int) -> None:
        """Batch the products for the given product id."""
        max_units_per_palette = self.extract_max_units_per_palette(product_id)
        min_batch_size = self.get_batch_size(product_id)
        orders = self.extract_quantities(product_id)
        total_quantity = sum(orders.values())
        current_stock = self.check_stock_locally(product_id)
        logging.info(
            f"For product {product_id} stock is {current_stock}. "
            f"Found {total_quantity} items in orders. Max units per palette: {max_units_per_palette}"
        )

        if total_quantity > current_stock:
            logging.warning(
                f"Current stock is not enough! Only {current_stock} items can be shipped."
            )
            if self.is_batch_size_sufficient(current_stock, orders, min_batch_size):
                total_quantity = current_stock
            else:
                logging.warning("Not enough items in the queue to create a batch.")
                return None

        if product_id in self.special_ids_to_batch:
            self.special_batching(
                max_units_per_palette,
                total_quantity,
                orders,
                product_id,
                min_batch_size,
            )
        else:
            self.regular_batching(
                max_units_per_palette, total_quantity, orders, product_id
            )

    def regular_batching(
        self,
        max_units_per_palette: int,
        total_quantity: int,
        orders: dict,
        product_id: int,
    ) -> None:
        """Regular batching logic: orders are batched based on the maximum
        number of items per palette.
        """
        # batch_items = []
        if total_quantity <= max_units_per_palette and len(orders) <= config.MAX_BATCH_SIZE:
            list_of_ids = list(orders.keys())
            note = self.note_creator.create_note(
                list_of_ids=list_of_ids,
                batched_quantity=total_quantity,
                batched_product=self.product_name,
            )
            # note = f"{config.BASE_NOTE}: "
            # if product_id in self.seni_ids:
            #     note = note + f" {config.NOTE_SENI}"
            # if self.is_prio is True:
            #     note = self.create_priority_note(config.BASE_NOTE)
            # note = note + f" {config.NOTE_BATCH}: {total_quantity} {self.product_name}"
            try:
                self.create_picking(
                    list_of_ids=list_of_ids,
                    note=note,
                    orders_count=1,
                    cart=False,
                )
                # for order_id, quantity in orders.items():
                #     if order_id not in self.processed_orders:
                #         batch_items.append(
                #             {
                #                 "product_id": product_id,
                #                 "requested_quantity": quantity,
                #                 "fulfillment_order_id": order_id,
                #             }
                #         )
                # self.picking_orders.append(
                #     {
                #         "items": batch_items,
                #         "notes": f"{config.BASE_NOTE} {config.NOTE_BATCH}: {total_quantity} {self.product_name}",
                #         "warehouse_id": config.WAREHOUSE_ID,
                #     }
                # )
                self.processed_orders.update(list_of_ids)
                self.product_stock[product_id] -= total_quantity
            except Exception as e:
                logging.error(
                    f"An error occurred when creating batch "
                    f"in PulpoBatchingManager batching_products: {e}"
                )
        else:
            logging.warning("Can not create a single batch, orders need to be splited.")
            self.split_batches(
                orders=orders,
                total_quantity=total_quantity,
                max_units_per_palette=max_units_per_palette,
            )

    def special_batching(
        self,
        max_units_per_palette: int,
        total_quantity: int,
        orders: dict,
        product_id: int,
        min_batch_size: int,
    ) -> None:
        """Special batching logic for the products that are included in
        the special SKUs list (skus_to_batch.json).
        1. Check if the orders can be batched into a single palette. Each of
        the special SKUs has a separate_batch_from value that determines
        the minimum quantity of items that can be batched into a palette.
        2. Then regular batching is applied to the remaining orders.
        """
        left_orders = {}
        total_quantity = self.special_palette_batching(
            total_quantity, orders, product_id
        )
        for order_id, quantity in orders.items():
            if order_id not in self.processed_orders:
                left_orders[order_id] = quantity
        if len(left_orders) > 0 and total_quantity > min_batch_size:
            self.regular_batching(
                max_units_per_palette, total_quantity, left_orders, product_id
            )

    def special_palette_batching(
        self, total_quantity: int, orders: dict, product_id: int
    ) -> None:
        """Create a palette for the orders that have a quantity greater than
        the separate_batch_from value. One picking order is created for each
        sales order."""
        separate_batch_from_quantity = self.find_palette_separation_value(product_id)
        for order_id, quantity in orders.items():
            if total_quantity <= 0:
                break
            if (
                quantity >= separate_batch_from_quantity
                and quantity <= total_quantity
                and order_id not in self.processed_orders
            ):
                try:
                    note = self.note_creator.create_note(
                        list_of_ids=[order_id],
                        batched_quantity=quantity,
                        batched_product=self.product_name,
                    )
                    # note = f"{config.BASE_NOTE}: {config.NOTE_PALETTE}: {quantity} {self.product_name}"
                    # if self.is_prio is True:
                    #     note = self.create_priority_note(config.BASE_NOTE)
                    #     note = f"{note} {config.NOTE_PALETTE}: {quantity} {self.product_name}"
                    self.create_picking(
                        list_of_ids=[order_id],
                        note=note,
                        orders_count=1,
                        cart=False,
                    )
                    # self.picking_orders.append({
                    #     "items": {
                    #         "product_id": product_id,
                    #         "requested_quantity": quantity,
                    #         "fulfillment_order_id": order_id,
                    #     },
                    #     "notes": f"{config.BASE_NOTE} {config.NOTE_PALETTE}: {quantity} {self.product_name}",
                    #     "warehouse_id": config.WAREHOUSE_ID,
                    # })
                    self.processed_orders.add(order_id)
                    total_quantity -= quantity
                    self.product_stock[product_id] -= quantity
                except Exception as e:
                    logging.error(
                        f"An error occurred when creating palette for order {order_id} "
                        f"in PulpoBatchingManager batching_products: {e}"
                    )
        return total_quantity

    def find_palette_separation_value(self, product_id: int) -> int:
        """Find the value that determines the minimum quantity of items that can
        be batched into a palette for the given product id."""
        for sku, value in self.skus_to_batch.items():
            if value["id"] == product_id:
                return value["separate_batch_from"]

    def is_batch_size_sufficient(
        self, total_quantity: int, orders: dict, min_batch_size: int
    ) -> int:
        """Check if the total quantity of orders is sufficient to create a batch."""
        orders_that_fit = []
        fitted_quantity = 0
        for order_id, quantity in orders.items():
            if fitted_quantity + quantity < total_quantity:
                fitted_quantity += quantity
                orders_that_fit.append(order_id)
        if len(orders_that_fit) > min_batch_size:
            return True
        return False

    def extract_quantities(self, product_id: int) -> Dict[int, int]:
        """Extract how many items are in the orders for the given product id.

        Return:
        - orders - a dictionary containing the sales order ids and their quantities.
        The dictionary is sorted by the quantity in descending order.

        Important: it is necessary to iterate through fulfillment orders, since
        only they have the correct state of the order. When an order is paused
        in Pulpo, it will not reflect in the sales/orders endpoint, only
        the fulfillment orders will have the correct state.
        """
        orders = {}
        for order in self.orders_to_include:
            if len(order.items) == 1:
                for item in order.items:
                    if item.product.id == product_id:
                        orders[order.sales_order_id] = int(float(item.quantity))

        return dict(sorted(orders.items(), key=lambda x: x[1], reverse=True))

    # def extract_quantities(self, product_id: int) -> Dict[int, int]:
    #     """Extract how many items are in the orders for the given product id.

    #     Return:
    #     - orders - a dictionary containing the sales order ids and their quantities.
    #     The dictionary is sorted by the quantity in descending order.

    #     Important: it is necessary to iterate through fulfillment orders, since
    #     only they have the correct state of the order. When an order is paused
    #     in Pulpo, it will not reflect in the sales/orders endpoint, only
    #     the fulfillment orders will have the correct state.
    #     """
    #     orders = {}
    #     for order in self.pulpo.iterator(
    #         "sales/orders/fulfillments",
    #         params={"state": "queue", "product_id": [product_id]},
    #     ):
    #         try:
    #             order = pulpoClasses.FulfillmentOrder(**order)
    #             if len(order.items) == 1 and self.check_order_suitability(order) and self.is_order_in_list(order):
    #                 orders[order.sales_order_id] = int(float(order.items[0].quantity))

    #         except PulpoError as e:
    #             logging.error(
    #                 f"An error occurred in Pulpo batchingFlow batching_products: {e}. Order: {order}"
    #             )
    #         except Exception as e:
    #             logging.error(
    #                 f"An error occurred in Pulpo batchingFlow batching_products: {e}. Order: {order}"
    #             )
    #     return dict(sorted(orders.items(), key=lambda x: x[1], reverse=True))

    def check_stock_locally(self, product_id: int) -> int:
        """Check the stock for the given product id."""
        if product_id in self.product_stock:
            return self.product_stock[product_id]
        return 0

    def extract_max_units_per_palette(self, product_id: str) -> int:
        """Extract the maximum number of items per palette for this product.
        Special SKUs are checked first, then the product in Pulpo is checked.
        If the product does not have this information, find it in WeClapp
        and update the product."""
        max_units_per_palette = 0

        product = pulpoClasses.Product.fromPulpo(
            "inventory/products", product_id, self.pulpo
        )
        self.product_name = product.name

        if product.units_per_pallet and float(product.units_per_pallet) > 0:
            return int(float(product.units_per_pallet))

        else:
            max_units_per_palette = self.find_article_info(product)
            if max_units_per_palette > 0:
                dict_to_update = {}
                dict_to_update["units_per_pallet"] = int(max_units_per_palette)
                dict_to_update["barcodes"] = product.barcodes
                self.update_product(product_id, dict_to_update)

        if max_units_per_palette == 0:
            logging.warning(f"Product {product.name} has no pallet information.")
            self.send_teams_message(product)
            max_units_per_palette = float("inf")
        return max_units_per_palette

    def find_article_info(self, product: pulpoClasses.Product) -> int:
        """Find the article info for the given product id."""
        max_units_per_palette = 0
        try:
            weclapp_id = product.attributes.weclapp_article_id
            if weclapp_id:
                article = weclappClasses.Article.fromWeclapp(weclapp_id)
            else:
                article = self.get_article_from_weclapp(product.sku)

            if (
                article.queryMetaData(self.cat.VsInfoEbene).val
                and article.queryMetaData(self.cat.VsInfoEbene).val
                != self.cat.VsInfoEbene.Keine
                and article.queryMetaData(self.cat.VsInfoPackAnz).val
                and article.queryMetaData(self.cat.VsInfoKartonAnz).val
                and article.queryMetaData(self.cat.VsInfoVersandAnz).val
            ):
                max_units_per_palette = self.calculate_max_units_per_palette(article)
        except Exception as e:
            logging.error(
                f"An error occurred in batchingFlow: def find_article_info: {e}"
            )
        return max_units_per_palette

    def calculate_max_units_per_palette(self, article: weclappClasses.Article) -> int:
        """Calculate the maximum number of items per palette for the given article."""
        all_levels = [
            float(article.queryMetaData(self.cat.VsInfoPackAnz).val),
            float(article.queryMetaData(self.cat.VsInfoKartonAnz).val),
            float(article.queryMetaData(self.cat.VsInfoVersandAnz).val),
        ]
        if (
            article.queryMetaData(self.cat.VsInfoEbene).val
            == self.cat.VsInfoEbene.Artikel
        ):
            return int(all_levels[0] * all_levels[1] * all_levels[2])
        elif (
            article.queryMetaData(self.cat.VsInfoEbene).val
            == self.cat.VsInfoEbene.Packung
        ):
            return int(all_levels[1] * all_levels[2])
        elif (
            article.queryMetaData(self.cat.VsInfoEbene).val
            == self.cat.VsInfoEbene.Karton
        ):
            return int(all_levels[2])

    def get_article_from_weclapp(self, product_sku: int) -> weclappClasses.Article:
        """Get the article information from WeClapp for the given product SKU."""
        try:
            article = weclapp.GET(
                "article",
                params={"sku": product_sku, "active": True, "articleType": "STORABLE"},
            )
            if article:
                return weclappClasses.Article(**article[0])
        except Exception as e:
            logging.error(f"An error occurred in batchingFlow: def call_weclapp: {e}")

    def split_batches(
        self, orders: dict, total_quantity: int, max_units_per_palette: int
    ) -> None:
        """
        Iterate over the sorted (descending, based on label share) orders
        and create batches of orders.

        The iteration is happening in the following way:
        - Start with the first order, if no batch can be created, move to the next
        order;
        - If a batch can be created, remove the orders from the dictionary and
        continue with the next order.
        """
        num_batches_by_articles = total_quantity // max_units_per_palette
        num_batches_by_orders = len(orders) // config.MAX_BATCH_SIZE
        num_batches = min(num_batches_by_articles, num_batches_by_orders)

        for num_batch in range(int(num_batches)):
            batched_quantity = 0
            ids_to_batch = set()

            for order_id, quantity in orders.items():
                if order_id in self.processed_orders:
                    continue
                if batched_quantity + quantity > max_units_per_palette:
                    break
                if len(ids_to_batch) >= config.MAX_BATCH_SIZE:
                    break
                batched_quantity += quantity
                ids_to_batch.add(order_id)

            if ids_to_batch:
                id_list = list(ids_to_batch)
                note = self.note_creator.create_note(
                        list_of_ids=ids_to_batch,
                        batched_quantity=batched_quantity,
                        batched_product=self.product_name,
                    )
                try:
                    self.create_picking(
                        list_of_ids=id_list,
                        note=note,
                        orders_count=1,
                        cart=False,
                    )
                    self.processed_orders.update(ids_to_batch)
                except Exception as e:
                    logging.error(
                        f"An error occurred when creating batch "
                        f"in PulpoBatchingManager split_batches: {e}"
                    )

    def find_products_to_batch(self) -> list:
        """Find products that have more than MIN_BATCH_SIZE orders in the queue.
        Return: list of product IDs to batch."""
        product_ids_to_batch = []
        orders_count = self.find_single_sku_orders()
        # logging.info(f"Orders count: {orders_count}")

        for product_id, count in orders_count.items():
            min_batch_size = self.get_batch_size(product_id)
            if count >= min_batch_size:
                product_ids_to_batch.append(product_id)

        return product_ids_to_batch

    def get_batch_size(self, product_id: int) -> int:
        """Get the batch size for the given product id."""
        min_batch_size = config.MIN_BATCH_SIZE
        if product_id in self.seni_ids:
            min_batch_size = config.MIN_BATCH_SIZE_SENI
        if self.is_running_dry:
            min_batch_size = min_batch_size * config.RUNNING_DRY_DENOMINATOR
        return round(min_batch_size)

    def find_single_sku_orders(self) -> dict:
        orders_count = {}
        for order in self.orders_to_include:
            if len(order.items) == 1:
                item = order.items[0]
                self.check_if_seni(item)
                if item.product.id in orders_count:
                    orders_count[item.product.id] += 1
                else:
                    orders_count[item.product.id] = 1
        return orders_count

    def check_if_seni(self, item: pulpoClasses.Item) -> bool:
        """Check if the product is a Seni product."""
        if item.product.product_categories:
            for category in item.product.product_categories:
                if category["id"] == config.TZMO_MANUFACTURER:  # Seni products
                    self.seni_ids.append(item.product.id)

        if config.SENI_PRODUCTS_IDENTIFIER in item.product.name:
            self.seni_ids.append(item.product.id)

    # def find_single_sku_orders(self) -> dict:
    #     """Iterate through the fulfillment orders with 1 SKU in queue and find
    #     how many orders are there for each SKU.

    #     Important: it is necessary to iterate through fulfillment orders, since
    #     only they have the correct state of the order. When an order is paused
    #     in Pulpo, it will not reflect in the sales/orders endpoint, only
    #     the fulfillment orders will have the correct state.
    #     """
    #     orders_count = {}
    #     for order in self.pulpo.iterator(
    #         "sales/orders/fulfillments",
    #         params={"state": "queue", "order_items_count": 1},
    #     ):
    #         try:
    #             order = pulpoClasses.FulfillmentOrder(**order)
    #             for item in order.items:
    #                 if (
    #                     self.check_order_suitability(order)
    #                     and self.is_order_in_list(order)
    #                 ):
    #                     self.check_if_seni(item)
    #                     if item.product.id in orders_count:
    #                         orders_count[item.product.id] += 1
    #                     else:
    #                         orders_count[item.product.id] = 1
    #         except PulpoError as e:
    #             logging.error(
    #                 f"An error occurred in find_single_sku_orders in BatchingFlow: {e}. Order: {order}"
    #             )
    #             continue
    #         except Exception as e:
    #             logging.error(
    #                 f"An error occurred in find_single_sku_orders in BatchingFlow: {e}. Order: {order}"
    #             )
    #             continue
    #     return orders_count

    # def is_order_in_list(self, order: pulpoClasses.FulfillmentOrder) -> bool:
    #     """Check if the order is in the list of orders to include."""
    #     for included_order in self.orders_to_include:
    #         if included_order.sales_order_id == order.sales_order_id:
    #             return True
    #     return False
