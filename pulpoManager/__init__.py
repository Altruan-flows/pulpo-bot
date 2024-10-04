import logging
import pytz
import json
import os
from azure.storage.blob import BlobServiceClient
from azure.core.exceptions import (
    ResourceNotFoundError,
    HttpResponseError,
    ClientAuthenticationError,
)
from typing import List
from datetime import datetime

from pulpoFunctions import Pulpo, pulpoClasses
from pulpoFunctions.pulpoError import PulpoError
from .batching_flow import PulpoBatchingManager
from .separation import PulpoSeparator
from .shelves_index import PulpoShelvesIndexCreator
from .carts import PulpoCartsManager
from .shared_functions import PulpoUtils
from .config import PackageSizes
from . import config


class PulpoManager:
    """Main class that executes the batching and carting flows in Pulpo.

    Class attributes:
    - pulpo: initialising the Pulpo class, which is used for all Pulpo API calls,
    all the other classes are using the same instance of Pulpo, so the session
    is shared between all classes. It was done to avoid multiple sessions
    with multiple tokens. Session is closed at the end of the main function.
    - current_time: current time in Berlin timezone.
    - is_sweeping_time: boolean value that indicates if it is the time to sweep
    the orders (process all orders that are in queue). The sweeping time is
    chosen based on the time the shipping LKV is going out of the warehouse.
    - is_running_dry: boolean value that indicates if the warehouse is running
    dry (number of picking orders is below the set value).
    - pickers: dictionary that contains the pickers information. It is retrieved
    from the Blob Storage.

    """

    def __init__(self):
        self.pulpo = Pulpo(testing=False)
        berlin_tz = pytz.timezone("Europe/Berlin")
        # self.current_time = datetime.now(berlin_tz)
        self.current_time = datetime(2024, 10, 2, 6, 0, 0, tzinfo=berlin_tz)
        self.is_sweeping_time = self.check_sweeping_time()
        self.is_running_dry = False
        self.pickers = self.get_pickers_from_blob()
        logging.warning(f"Is sweeping time: {self.is_sweeping_time}")

    def main(self):
        """Main function that executes the batching and carting flows."""
        try:
            self.scheduled_maintenance_tasks()
            self.preprocessing_orders()
            self.index_creation()
            # Orders separation by priority
            self.separate_orders_by_priority()

            # Picking creation
            self.batching_manager = PulpoBatchingManager(
                pulpo=self.pulpo,
                current_time=self.current_time,
                is_running_dry=self.is_running_dry
            )
            self.carts_manager = PulpoCartsManager(
                pulpo=self.pulpo,
                shelves_index=self.shelves_index_creator.shelves_index,
                current_time=self.current_time,
                is_running_dry=self.is_running_dry,
            )

            logging.warning("--------Processing priority orders---------")
            self.picking_creation_manager(
                is_prio=True,
                batch_list=self.pulpo_separator.prio_orders_for_batches,
                cart_seni_list=self.pulpo_separator.seni_prio_orders,
                cart_list=self.pulpo_separator.prio_orders_without_seni,
            )

            logging.warning("-------Processing non-priority orders--------")
            self.picking_creation_manager(
                is_prio=False,
                batch_list=self.pulpo_separator.orders_for_batches,
                cart_seni_list=self.pulpo_separator.seni_orders,
                cart_list=self.pulpo_separator.orders_without_seni,
            )

        except Exception as e:
            logging.error(f"An error occurred in PulpoManager main: {e}")
        self.pulpo.close_session()
        return {"status": "finished"}, 200

    def picking_creation_manager(
        self,
        is_prio: bool,
        batch_list: List[pulpoClasses.FulfillmentOrder],
        cart_seni_list: List[pulpoClasses.FulfillmentOrder],
        cart_list: List[pulpoClasses.FulfillmentOrder],
    ) -> None:
        """Execute the picking creation flow. This process has the following steps:
        - Palette orders processing: XXL size
        - Batching (all orders with 1 SKU)
        - Carts creation: all sizes except XXL (only orders containin Seni products)
        - Carts creation: all sizes except XXL (orders without Seni products)
        """

        # Batch creation
        self.picking_creation_batches(batch_list, is_prio=is_prio)

        # Carts creation - Seni
        logging.warning(f"Processing Seni carts: {len(cart_seni_list)}")
        self.picking_creation_carts(cart_seni_list, is_prio=is_prio)

        # Carts creation
        self.picking_creation_carts(cart_list, is_prio=is_prio)

    # def picking_creation_palette(
    #     self, orders: List[pulpoClasses.FulfillmentOrder], is_prio: bool = False
    # ) -> None:
    #     """Create the palette orders."""
    #     self.carts_manager.main(
    #         size=PackageSizes.SIZE_XXL,
    #         orders=orders,
    #         is_prio=is_prio,
    #         is_sweeping_time=False,  # always False for palette, since it is either way 1 pick = 1 order
    #     )

    def index_creation(self) -> None:
        """Create the shelves index and product availability."""
        self.shelves_index_creator = PulpoShelvesIndexCreator(pulpo=self.pulpo)
        self.shelves_index_creator.main()

    def picking_creation_batches(
        self, orders: List[pulpoClasses.FulfillmentOrder], is_prio: bool = False
    ) -> None:
        """Create the batch orders."""
        self.batching_manager.main(
            orders_to_include=orders,
            is_prio=is_prio,
            product_stock=self.shelves_index_creator.product_availability,
        )
        # Add the processed orders to the carts manager
        self.carts_manager.processed_orders.extend(
            self.batching_manager.processed_orders
        )

    def picking_creation_carts(
        self, orders: List[pulpoClasses.FulfillmentOrder], is_prio: bool = False
    ) -> None:
        """Create the cart orders. This process is executed for all sizes except XXL."""
        for size in PackageSizes:
            if size == PackageSizes.SIZE_XXL:
                continue
            if self.carts_manager.no_space_left is True and self.is_sweeping_time is False:
                logging.warning("No space left in the warehouse. Skipping cart creation.")
                return
            self.carts_manager.main(
                size=size,
                orders=orders,
                is_prio=is_prio,
                is_sweeping_time=self.is_sweeping_time,
                product_stock=self.batching_manager.product_stock,
            )

    def scheduled_maintenance_tasks(self):
        """Execute the scheduled maintenance tasks."""
        logging.warning(f"Current time: {self.current_time.hour}")
        # Night cleaning: deleting all picks without an owner (ohne Zuweisung)
        if self.current_time.hour in config.NIGHT_CLEANING_HOURS:
            PulpoUtils(pulpo=self.pulpo).cleaner()
        # Update pickers information: update the pickers information in the Blob Storage
        if self.current_time.hour in config.PICKERS_UPDATE_HOURS:
            self.update_pickers_info()

    def check_sweeping_time(self) -> bool:
        """Check if it is the time to sweep orders."""
        return self.current_time.hour in config.SWEEPING_HOURS

    def preprocessing_orders(self) -> None:
        """Preprocess the orders. This step should be executed before creation
        of any picks."""
        for order in self.pulpo.iterator(
            "sales/orders/fulfillments", params={"state": "queue"}
        ):
            try:
                self.order = pulpoClasses.FulfillmentOrder(**order)
                # If shipping method is Altruan Lieferdienst, pause the order,
                # exclude it from the flow and create no picks!
                if self.order.shipping_method_id == config.ALTRUAN_LIEFERDIENST:
                    self.pause_order(self.order.sales_order_id)
            except Exception as e:
                logging.error(f"An error occurred in PulpoManager main: {e}")
                continue

    def pause_order(self, sales_order_id: int) -> None:
        """Pause the order in Pulpo.
        Important: only sales order id can be used!"""
        try:
            self.pulpo.askPulpo(f"sales/orders/{sales_order_id}/pause", method="POST")
            logging.warning(f"Order {sales_order_id} paused")
        except PulpoError as e:
            logging.error(
                f"An error occurred in Pulpo shared_functions pause_order: {e}"
            )
        except Exception as e:
            logging.error(
                f"An error occurred in Pulpo shared_functions pause_order: {e}"
            )

    def separate_orders_by_priority(self) -> None:
        """Run the orders separation process"""
        self.pulpo_separator = PulpoSeparator(
            pulpo=self.pulpo,
            is_sweeping_time=self.is_sweeping_time,
            pickers=self.pickers,
            current_time=self.current_time,
            product_stock=self.shelves_index_creator.product_availability
        )
        self.pulpo_separator.main()
        logging.warning(
            "Orders separated: "
            f"prio_orders_for_batches: {len(self.pulpo_separator.prio_orders_for_batches)} "
            f"seni_prio_orders: {len(self.pulpo_separator.seni_prio_orders)} "
            f"prio_orders_without_seni: {len(self.pulpo_separator.prio_orders_without_seni)} "
            f"orders_for_batches: {len(self.pulpo_separator.orders_for_batches)} "
            f"seni_orders: {len(self.pulpo_separator.seni_orders)} "
            f"orders_without_seni: {len(self.pulpo_separator.orders_without_seni)} "
        )
        self.is_running_dry = self.check_orders_count(self.pulpo_separator.orders_count)
        logging.warning(f"Warehouse is running dry: {self.is_running_dry}")

    def check_orders_count(self, orders_count: int) -> bool:
        """Check if the orders count is less than the running dry value. Return
        True if it is below the value, False otherwise."""
        logging.info(f"Orders count: {orders_count}")
        return orders_count < config.RUNNING_DRY_NUM_ORDERS

    def get_pickers_from_blob(self) -> dict:
        """Get the pickers information from the Blob Storage."""
        pickers = config.PICKERS
        try:
            blob_client = self.connect_to_blob()
            if not blob_client:
                return pickers

            # Download the blob's content as a string
            blob_content = blob_client.download_blob().content_as_text()

            # Parse the content to a JSON object
            pickers = json.loads(blob_content)

        except json.JSONDecodeError as e:
            logging.error(
                f"JSON decoding failed: The blob content could not be parsed as JSON: {e}"
            )
        except Exception as e:
            logging.error(f"An unexpected error occurred: {str(e)}", exc_info=True)
        return pickers

    def update_pickers_info(self) -> None:
        """Update the pickers information in the Blob Storage."""
        try:
            # Get the pickers information
            pickers = self.get_pickers_from_google_sheet()
            blob_client = self.connect_to_blob()
            if not blob_client:
                return
            # Upload the pickers information to the Blob Storage
            data = json.dumps(pickers)
            blob_client.upload_blob(data, overwrite=True)
        except Exception as e:
            logging.error(
                f"An unexpected error occurred in PulpoManager update_pickers_info: {str(e)}",
                exc_info=True,
            )

    def connect_to_blob(self) -> BlobServiceClient:
        """Connect to the Azure Blob Storage."""
        try:
            connect_str = os.environ["azureBlobStorageChannable_ConStr"]
            # Create a BlobServiceClient object and Get a blob client using the container and blob name
            blob_service_client = BlobServiceClient.from_connection_string(connect_str)
            blob_client = blob_service_client.get_blob_client(
                container=config.BLOB_CONTAINER, blob=config.BLOB_NAME
            )
            return blob_client

        except ResourceNotFoundError as e:
            logging.error(
                f"Resource not found: The specified blob or container does not exist: {e}"
            )
        except ClientAuthenticationError as e:
            logging.error(
                f"Authentication failed: Please check your connection string and credentials: {e}"
            )
        except HttpResponseError as e:
            logging.error(
                f"HTTP error occurred when trying to access blob: {e.message}",
                exc_info=True,
            )
        except KeyError:
            logging.error(
                "Key error: Azure Blob connection string does not exist.", exc_info=True
            )
        except Exception as e:
            logging.error(
                f"An unexpected error occurred in PulpoManager connect_to_blob: {str(e)}",
                exc_info=True,
            )
        return None

    def get_pickers_from_google_sheet(self) -> dict:
        """Get the pickers information from the Google Sheet Document and save
        them to a dictionary. The dictionary is structured as follows:
        {"Palettenversand": [picker1_id, picker2_id, ...],
         "Partnerkunden": [picker1_id, picker2_id, ...],
         "Abholungen": [picker1_id, picker2_id, ...]}
        """
        from googleapiclient.discovery import build
        from util.google.serviceAccount import ServiceAccount  # custom module, does not exist in the repository

        pickers = config.PICKERS
        try:
            service = ServiceAccount(scopes=config.SCOPES)
            service = build("sheets", "v4", credentials=service.credentials)

            for key in pickers:
                result = (
                    service.spreadsheets()
                    .values()
                    .get(
                        spreadsheetId=config.PICKERS_SHEET_ID,
                        range=f"'{config.PICKERS_SHEET_NAME}'!{config.PICKERS_SHEET_RANGES[key]}",
                    )
                    .execute()
                )
                values = result.get("values", [])
                if values:
                    for row in values:
                        user_search = self.pulpo.askPulpo(
                            "iam/users", params={"username": row[0]}
                        )
                        if user_search:
                            user = user_search[0]
                            pickers[key].append(user.get("id"))
        except Exception as e:
            logging.error(
                f"An unexpected error occurred in PulpoManager get_pickers_from_google_sheet: {str(e)}",
                exc_info=True,
            )
        return pickers
