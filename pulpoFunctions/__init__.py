import requests
import logging
import os
import time
from requests.exceptions import HTTPError
from typing import Generator
from .pulpoError import PulpoError
from . import config


class Pulpo:
    def __init__(self, token: str = None, testing: bool = False):
        self.session = requests.Session()  # Use a session for connection pooling
        self.api_call_timestamps = []
        if not token:
            token = self.get_token()
        self.token = token
        self.testing = testing
        self.time_window = config.TIME_WINDOW
        self.api_limit = config.MAX_CALLS

    def _throttle_api_calls(self):
        """
        Check and throttle API calls if exceeding the rate limit.
        """
        current_time = time.time()
        # Remove old timestamps outside the current time window
        self.api_call_timestamps = [t for t in self.api_call_timestamps if t > current_time - self.time_window]

        if len(self.api_call_timestamps) >= self.api_limit:
            time_to_wait = self.time_window - (current_time - self.api_call_timestamps[0])
            if time_to_wait > 0:
                logging.warning(f"API rate limit reached, waiting for {time_to_wait} seconds")
                time.sleep(time_to_wait)

    def get_token(self) -> str:
        current_time = time.time()
        # Since token is generated only once, it is assumed that no timestamps
        # are present in the list
        self.api_call_timestamps.append(current_time)
        url = f"{config.BASE_URL}auth"
        headers = {"Content-Type": "application/json"}
        body = {
            "grant_type": "password",
            "password": os.environ["pulpo_password"],
            "scope": "default",
            "username": config.LOGIN,
        }
        response = requests.post(url=url, headers=headers, json=body)
        with self.session.request(
            method="POST", url=url, headers=headers, json=body
        ) as response:
            response.raise_for_status()
            response_text = response.json()
            if "access_token" in response_text:
                logging.warning(
                    f"new token has been generated \n {response_text['access_token']}"
                )
                return response_text["access_token"]
            # print(response_text)
            raise (PulpoError(response))

    def askPulpo(
        self,
        endpoint: str,
        method: str = "GET",
        params: dict = {},
        body: dict = {},
        retries: int = 3,
        delay: int = 30,
    ) -> dict:
        if not self.testing:
            url = f"{config.BASE_URL}{endpoint}"
        else:
            url = f"{config.SANDBOX_URL}{endpoint}"

        headers = {
            "Content-Type": "application/json",
            "authorization": f"bearer {self.token}",
        }
        for attempt in range(retries):
            try:
                # Throttle API calls if exceeding the rate limit
                self._throttle_api_calls()
                # logging.info(f"Requesting {url} with {params=} and {body=}")
                with self.session.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=params if method == "GET" else None,
                    json=body if method in ["POST", "PUT"] else None
                ) as response:
                    response.raise_for_status()  # Raise an HTTPError for bad responses
                    response_text = response.json()

                    self.api_call_timestamps.append(time.time())

                    if isinstance(response_text, dict) and "total_results" in response_text:
                        for key in response_text:
                            if key != "total_results":
                                return response_text[key]
                    if isinstance(response_text, dict) and "created" in response_text:
                        return response_text
                    if (
                        "errors" in response_text
                        or "message" in response_text
                        or isinstance(response_text, str)
                    ):
                        logging.warning(f"Got error response: {response_text}")
                        pulpo_error_handler = PulpoError(response)
                        pulpo_error_handler.is_api_rate_limit_error()
                        raise pulpo_error_handler
                    return response_text

            except PulpoError as e:
                if e.is_api_rate_limit_error() and attempt < retries - 1:
                    if e.delay:
                        delay = e.delay
                    logging.warning(
                        f"API rate limit reached, waiting for {delay} seconds. Attempt {attempt+1}/{retries}"
                    )
                    time.sleep(delay)
                    continue
                raise e
            except HTTPError as http_err:
                if response.status_code == 429:
                    logging.warning(
                        f"API rate limit reached, waiting for {delay} seconds. Attempt {attempt+1}/{retries}"
                    )
                    time.sleep(delay)
                    continue
                raise http_err
            except Exception as err:
                logging.error(f"Unexpected error occurred: {err}")
                raise err

    def iterator(
        self,
        endpoint: str,
        params: dict = {},
        stop_after_n_items: int = None,
        log: bool = True,
        start_page: int = 0,
        page_size: int = 600,
    ) -> Generator[dict, None, None]:
        if log:
            logging.info(f"---starting iterating over {endpoint}---")

        # init Cariables
        offset = start_page
        items = 1

        while items > 0:
            # prepare Querys
            query = {
                # "responsibleUserFixed": "true", -> wird über query params upgedatet
                "limit": page_size,
                "offset": offset,
            }
            query.update(params)

            # get Object
            weclappObjList = self.askPulpo(
                method="GET", endpoint=endpoint, params=query
            )

            # check Result
            assert isinstance(
                weclappObjList, list
            ), f"The endpoint needs to be one that returns a list => {endpoint} is invalid"
            items = len(weclappObjList)
            if log:
                logging.warning(f"--------OFFSET {offset}--------- {items=}")

            # yield all purchases of customer
            for obj in weclappObjList:
                yield obj

            offset += items

            # check if stop is requested
            if stop_after_n_items:
                if stop_after_n_items < offset:
                    break
            if items < page_size:
                break
        if log:
            logging.info(f"---finished iterating over {endpoint}---")

    def close_session(self):
        self.session.close()  # Close the session when done
