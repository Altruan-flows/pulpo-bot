import logging
from pulpoFunctions import Pulpo, pulpoClasses
from . import config


class PulpoShelvesIndexCreator:
    """
    This class is responsible for getting information about shelves in the
    warehouse from Pulpo.

    Attributes:
    - pulpo: Pulpo class object.

    - shelves_index: dict - contains the index of shelves. It has the following
    structure: {shelf_code: {product_id1, product_id2, ...}}.

    - product_availability: dict - contains the availability of products in the
    warehouse. It has the following structure: {product_id: quantity}.
    """

    def __init__(self, pulpo: Pulpo) -> None:
        self.pulpo = pulpo
        self.shelves_index = {}
        self.product_availability = {}

    def main(self) -> None:
        """
        Main function that iterates over all stocks in the warehouse and
        updates the shelves index and product availability.
        """
        for stock_dict in self.pulpo.iterator(
            "inventory/stocks", page_size=config.SHELVES_INDEX_PAGE_LENGTH
        ):
            try:
                stock = pulpoClasses.Stock(**stock_dict)
                # Include only Standardpositionen (H1, H2, H3) and Crossdockingpositionen
                if stock.location.zone_id in config.WAREHOUSE_ZONES_ALLOWED_FOR_PICKING:
                    self.add_product_on_shelf(stock)
                    self.add_product_availability(stock)

            except Exception as e:
                logging.error(
                    f"An error occurred in PulpoShelvesIndexCreator collect_all_products: {e}"
                )

    def add_product_on_shelf(self, stock: pulpoClasses.Stock) -> None:
        """
        Update the index of shelves. It has the following structure:
        {shelf_code: {product_id1, product_id2, ...}}.

        Shelves entries are the first 6 characters of the location code.
        Example: H1-111-1-2-1-1 -> H1-111.
        """
        shelf_code = stock.location.code[: config.SHELF_NAME_LENGTH]
        if shelf_code in self.shelves_index:
            self.shelves_index[shelf_code].add(stock.product.id)
        else:
            self.shelves_index[shelf_code] = {stock.product.id}

    def add_product_availability(self, stock: pulpoClasses.Stock) -> None:
        """
        Add product availability to the product_availability dictionary.
        """
        if stock.product.id in self.product_availability:
            self.product_availability[stock.product.id] += float(stock.quantity)
        else:
            self.product_availability[stock.product.id] = float(stock.quantity)
