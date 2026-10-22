from smdb_web_server.data.ResponseCode import ResponseCode

class Constants:
    Ok = ResponseCode(200, "Ok")
    OkNoResponse = ResponseCode(204, "No Content")
    NotFound = ResponseCode(404, "Not Found")
    Forbidden = ResponseCode(403, "Forbidden")
    BadRequest = ResponseCode(400, "Bad Request")
    TPot = ResponseCode(418, "I'm a teapot")
    InternalServerError = ResponseCode(500, "Internal Server Error")
