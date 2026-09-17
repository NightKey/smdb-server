from smdb_web_server.data.ResponseCode import ResponseCode

class Constants:
    NotFound = ResponseCode(404, "Not Found")
    Forbidden = ResponseCode(403, "Forbidden")
    Ok = ResponseCode(200, "Ok")
    InternalServerError = ResponseCode(500, "Internal Server Error")
    BadRequest = ResponseCode(400, "Bad Request")
    TPot = ResponseCode(418, "I'm a teapot")
