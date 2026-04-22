from smdb_web_server.data.ResponseCode import ResponseCode


class KnownError(Exception):
    def __init__(self, reason: str, response_code: int) -> None:
        self.response = ResponseCode(response_code, reason)

    def __str__(self) -> str:
        return f"Reason: {self.response.name}, Code: {self.response.value}"