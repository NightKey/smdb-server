# SMDB Web Server
An easy to use, not secured web server, because I don't like the other options, and I like to create my own solutions most of the time.

## Table of content
|        Section Name         |
|:---------------------------:|
| [Usage](#usage)             |
| [Get handler](#get-handler) |
| [Put Handler](#put-handler) |
| [Data](#data)               |

## Usage

To start using this HTTP Server, import the `HTMLServer` class, and initialize it.

```python
from smdb_web_server import HTMLServer, UrlData
server = HTMLServer("127.0.0.1", 8080, title="Example server")
```

An `smdb_logger` can be used, if desired, but not neccesery.

To add a new url path, use the `add_url_rule` command.

```python
def index_handler(url_data: UrlData) -> str:
    ...

server.add_url_rule("/", index_handler)
```

This method will be called with a `GET` request by default. This can be set as an optional parameter called `protocol`. For now, only `GET` and `PUT` are supported.

Url handlers can be assigned with a decorator as well:

```python
@server.as_url_rule("/help")
def help_handler(url_data: UrlData) -> str:
    ...
```

To start the server, use either the `serve_forever` or the `serve_forever_threaded` function. The first will be a blocking call, the second will create a new thread.

```python
server.serve_forever_threaded(template_dictionary, static_dictionary, "Example Thread")
```

Both handlers can fail with [KnownError](#knownerror) exception, whitch will result in a user controlled return code and reason.

## GET handler

This handler can return any string, but it's usefull, if it returns an HTML file as string. This can be a hardcoded HTML code, or a static or dynamic file. For rendering HTML template files, the server has a helper function called `render_template_file`. This can render an HTML file from a pre setup dictionary.

```python
def index_handler(url_data: UrlData) -> str:
    example_list = ["value1", "value2|False", "value3|True"]
    return server.render_template("index", page_title="Example Title", example_selector=example_list, button_1="Button 1 name", button_2="Button 2 name")
```

If you need to just create a list to update an already rendered HTML page's selector, you can use it the following way:

```python
def update(url_data: UrlData):
    return server.render_template_list("example_selector", ["value1|True", "value2|False", "value3|False"])

server.add_url_rule("/update", update)
```

This will result in the following list, if we use the `option` tag as shown in the [template_dictionary](#template-dictionary) in the [data](#data) paragraph:

```HTML
<option disabled></option>
<option value="value1" selected>value1</option>
<option value="value2">value2</option>
<option value="value3">value3</option>
```

This list will be sent as a `plaintext` response.

## Put Handler

This handler can return a simple string. The incoming data will be a bytearray of the body of the request.
```python
from smdb_web_server import Protocol

def put_handler(url_data: UrlData) -> str:
    # Do stuff here.
    # Either return with string, or fail with KnownError
    ...

server.add_url_rule("/put", put_handler, Protocol.Put)
```

## Data

### Template dictionary
 - Keys: The "file name" without extention
 - Value: The file's content, or a path in the following format: "PATH|{Relative path to file}"

This dictionary will be used to generate HTML response from the template. Theese templates can have replaceable values with the following format.
```HTML
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ page_title }}</title>
    <link rel="stylesheet" href="/static/style.css">
</head>
<body>
    <div class="container">
        <h2>Example Header</h2>
        <div class="grid-container">
                <label for="ExampleSelector">Example Selector:</label>
                <select id="ExampleSelector" class="fixed-width">
                    {{[ example_selector ]}}
                </select>
            <div class="button-group">
                <button id="ExampleButton1">{{ button_1 }}</button>
                <button id="ExampleButton2">{{ button_2 }}</button>
            </div>
        </div>
    </div>
    <script src="/static/script.js"></script>
</body>
</html>
```

In this page the `{{ page_title }}`, the `{{ button_1 }}` and the `{{ button_2 }}` will be replaced with one value, and the `{{[ ExampleSelector ]}}` will be generated using a list.

This dictionary should contain a key-value pair with the value being a repeateable value to fill the `{{[ ExampleSelector ]}}` place.

```python
selector_values = """<option value="{{VALUE}}"{{SELECTED}}>{{VALUE}}</option>"""
```

Here, the `{{VALUE}}` will be replaced by the list's content, and the `{{SELECTED}}` will be replaced by either the value `selected` or with an emty string, if the list's value is formatted in the following manner: `{value}|True`. If the value following the `|` character is not "True", it will be treated as if it was not present.

You can return a list by calling the `render_template_list` function by itself, or by rendering a full HTML page by calling `render_template`, with a list as an argument.

### Static dictionary
 - Keys: The "file name" without extention
 - Value: Either the file's content, or a path in the following format: "PATH|{Relative path to file}"

Static files will be sent automatically, if the correct URL is called. In the [Template Dictionary](#template-dictionary) example, the javascript and the css files are loaded from the path `/static/{file_name}`. This will result in the `{file_name}` file being served from the dictionary.

### KnownError

This error is used to send a usercontrolled response code to the requester. This exception can be used the following way:

```python
from smdb_web_server import KnownError
def fail(_):
    raise KnownError("Reason", 405)
```

### Protocol

This is a simple enum class to use with `add_url_rule` to determine the protocol to be used

Values: `Get`, `Put`

### UrlData

This dataclass contains the following fields, either filled or containing `None`:

 - fragment: `String` object (Data following the `#` in the URL)
 - query: `Dictionary` with string keys and values (Data following the `?` in the URL)
 - data: `Bytes` object (Payload of the request, if available)
