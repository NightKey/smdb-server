from smdb_web_server.data.ResponseCode import ResponseCode

class Constants:
    NotFound = ResponseCode(404, "Not Found")
    Ok = ResponseCode(200, "Ok")
    InternalServerError = ResponseCode(500, "Internal Server Error")
    TPot = ResponseCode(418, "I'm a teapot")
