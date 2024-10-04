import requests
import json


class PulpoError(Exception):
    def __init__(self, errorResponse: requests.Response):
        self.response = errorResponse
        self.fullLog = False
        self.delay = None
        try:
            self.errorResponse = self.response.json()
            self.isJson = True

        except json.JSONDecodeError:
            self.detail = errorResponse.text
            self.isJson = False

    def __str__(self) -> str:
        errorLines = []
        if self.isJson and "errors" in self.errorResponse:
            if type(self.errorResponse["errors"]) is dict:
                message = self.errorResponse["errors"].get("message", None)
                code = self.response.status_code
                if code and message:
                    s = f"›{code}: {message}"
                    errorLines.append(s)
                else:
                    s = f'›{code}: {self.errorResponse["errors"]}'
                    errorLines.append(s)
            elif type(self.errorResponse["errors"]) is list:
                for el in self.errorResponse["errors"]:
                    errorLines.append(json.dumps(el))
        elif self.isJson and type(self.errorResponse) is str:
            errorLines.append(self.errorResponse)

        return "\n".join(errorLines)

    def is_api_rate_limit_error(self) -> bool:
        if self.isJson and "message" in self.errorResponse:
            message = self.errorResponse.get("message", None)
            if message == "api_rate_limit_reached":
                self.delay = self.errorResponse.get("retry_after_seconds", None)
                return True
        return False
