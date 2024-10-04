# ---------------- Configurations for the pulpoManager ----------------
from collections import namedtuple
from enum import Enum

# ----------------- General -----------------
# shipping methods
ALTRUAN_LIEFERDIENST = 807
ABHOLUNG = 665
PALETTENVERSAND = 604
DB_SCHENKER = 605
DB_SCHENKER_EUROPALETTE = 1097
SPECIAL_SHIPPING_METHODS = [
    ALTRUAN_LIEFERDIENST,
    ABHOLUNG,
    PALETTENVERSAND,
    DB_SCHENKER,
    DB_SCHENKER_EUROPALETTE,
]

# defaults
WAREHOUSE_ID = "221"
WECLAPP_ARTICLE_URL = "https://altruan.weclapp.com/webapp/view/products/articles/ArticleDetail.page?entityId="
TAG_IDENTIFIER_LABEL_SHARE = "LA_"
SKUS_TO_BATCH = "pulpoManager/skus_to_batch.json"
QUEUE_STATE = "queue"
NIGHT_CLEANING_HOURS = [2, 3]
PICKERS_UPDATE_HOURS = [4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17]
SWEEPING_HOURS = [5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17]
RUNNING_DRY_NUM_ORDERS = 100  # orders - example value
RUNNING_DRY_DENOMINATOR = 0.1  # example value

# Azure blob storage
BLOB_CONTAINER = "blob-container-name"
BLOB_NAME = "pickers.json"

# ----------------- Shelves Index -----------------

H1_ZONE_CODE = "H1"
H1_ZONE_ID = 1419
H2_ZONE_CODE = "H2"
H2_ZONE_ID = 1423
H3_ZONE_CODE = "H3"
H3_ZONE_ID = 1472
CROSSDOCKING_ZONE_CODE = "CrossdockingArea"
CROSSDOCKING_ZONE_ID = 1417
WAREHOUSE_ZONES_ALLOWED_FOR_PICKING = [H1_ZONE_ID, H2_ZONE_ID, H3_ZONE_ID, CROSSDOCKING_ZONE_ID]
SHELF_NAME_LENGTH = 6
SHELVES_INDEX_PAGE_LENGTH = 3000

# ----------------- Notes -----------------
BASE_NOTE = "Bot:"
NOTE_BATCH = "Batch"
NOTE_PLZ_FAR_RANGE = "PLZ 1-4"
NOTE_YESTERDAY = "Vortag"
NOTE_SWEEPER = "Rest"
NOTE_SENI = "Seni"

NOTE_S = "S (bis 0.25)"
NOTE_M1 = "M1 (bis 0.5)"
NOTE_M2 = "M2 (bis 1)"
NOTE_L = "L (bis 3)"
NOTE_XL = "XL (ab 3)"
NOTE_PRIO = "PRIO"

NOTE_ALTRUAN_LIEFERDIENST = "Altruan Lieferdienst"
NOTE_ABHOLUNG = "Abholung"
NOTE_DB_SCHENKER = "Palette"
NOTE_PALETTE = "Palette"
NOTE_PARTNERKUNDE = "Partnerkunde (Bitte Lieferschein ausdrucken)"

# ----------------- Picks Assignment -----------------
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
PICKERS_SHEET_ID = "google_sheet_id"
PICKERS_SHEET_NAME = "sheet_name"
PICKERS = {"Palettenversand": [], "Partnerkunden": []}
PICKERS_SHEET_RANGES = {"Palettenversand": "B2:B", "Partnerkunden": "C2:C"}


# ----------------- Separation -----------------
TIME_FORMAT = "%Y-%m-%dT%H:%M:%S"
TIME_FORMAT_SHORT = "%d-%m-%Y"
CORRECTION_HOURS = 2  # correction for the timezone
MAX_WAIT_TIME = 12  # in hours - example value
NORMAL_PRIORITY_VALUE = 1
PRIO_SALES_CHANNELS = [""]
GERMANY_COUNTRY_CODE = "276"
PLZ_FAR_RANGE = ["1", "2", "3", "4"]
YESTERDAY_ORDERS_START_TIME = 0  # example value
YESTERDAY_ORDERS_END_TIME = 24  # example value
WORKING_DAYS = [0, 1, 2, 3, 4]  # Monday to Friday
LABEL_SHARE_DIVIDERS = {0.25: NOTE_S, 0.5: NOTE_M1, 1: NOTE_M2, 3: NOTE_L, 9: NOTE_XL}
PALETTE_LABEL_SHARE = 9
TZMO_MANUFACTURER = 6468  # Seni
SENI_PRODUCTS_IDENTIFIER = "Seni"

# ----------------- Batch Flow -----------------
MIN_BATCH_SIZE = 5  # >= 5 orders - example value
MAX_BATCH_SIZE = 100  # <= 100 orders - example value
MIN_BATCH_SIZE_SENI = 3  # >= 3 orders - example value

# ----------------- Cart Flow -----------------
PRIO_THRESHOLD = float("inf")
NON_PRIO_THRESHOLD = 10

PICKING_STATES = {"queue", "taken"}
DEFAULT_PAGE_SIZE = 600
SWEEPING_MIN_ORDERS = 1

PackageSizeEntity = namedtuple("PackageSizeEntity", ["min", "max", "note"])


class PackageSizes(Enum):
    SIZE_S = PackageSizeEntity(
        min=1, max=10, note=NOTE_S
    )  # min and max orders per picking - example values
    SIZE_M1 = PackageSizeEntity(min=1, max=10, note=NOTE_M1)
    SIZE_M2 = PackageSizeEntity(min=1, max=10, note=NOTE_M2)
    SIZE_L = PackageSizeEntity(min=1, max=10, note=NOTE_L)
    SIZE_XL = PackageSizeEntity(min=1, max=1, note=NOTE_XL)
    SIZE_XXL = PackageSizeEntity(min=1, max=1, note=NOTE_PALETTE)


# ----------------- Single Picks Creation -----------------
PARTNERKUNDE_SALES_CHANNELS = ["Partnerkunde (netto)"]
