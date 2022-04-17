import inspect


class TestHandler:
    exposed = ["GET", "POST"]

    @staticmethod
    def GET(needed: int, not_needed: float = None) -> "HtmlPart":
        print(needed)
        print(not_needed)
        return "testing"

    @staticmethod
    def POST(input_data: "Json", not_needed: float = None) -> None:
        print(not_needed)
        print("input :"+str(input_data))


def parse_parameters_kind(annotation):
    if annotation == int:
        return "Integer"
    elif annotation == float:
        return "Float"
    elif annotation == str:
        return "String"
    else:
        raise Exception(f"error parameters kind unknown {annotation}")


def parse_input(annotation):
    if annotation == "Json":
        return "Json"
    elif annotation == "File":
        return "File"
    elif annotation is None:
        return "None"
    else:
        raise Exception(f"error input kind unknown {annotation}")


def parse_action(method, fct):
    ret = {"method": method, "parameters": [], "input": "None"}
    s = inspect.signature(fct)
    for key in s.parameters.keys():
        if key == "input_data":
            ret["input"] = parse_input(s.parameters[key].annotation)
        elif key == "server":
            pass
        elif key == "url":
            pass
        else:
            ret["parameters"].append({
                "name": key,
                "kind": parse_parameters_kind(s.parameters[key].annotation),
                "mandatory": s.parameters[key].default == s.parameters[key].empty
            })
    return ret


def parse_endpoint(api_id, handler):
    ret = {"id": api_id, "methods": []}
    methods = ["GET", "POST", "PUT", "DELETE", "PATCH"]
    for method in methods:
        try:
            fct = getattr(handler, method)
            ret["methods"].append(parse_action(method, fct))
        except AttributeError:
            pass
    return ret


async def apply_fct(fct, parameters, input_value):
    s = inspect.signature(fct)
    b = s.bind_partial()
    b.apply_defaults()
    for key in parameters.keys():
        if key in s.parameters.keys():
            b.arguments[key] = parameters[key]
    if "input_data" in s.parameters.keys():
        b.arguments["input_data"] = input_value
    return await fct(*b.args, **b.kwargs)


async def apply_end_point(handler, data):
    methods = ["GET", "POST", "PUT", "DELETE", "PATCH"]
    if data["method"] not in methods:
        raise Exception("methode unknown")
    fct = getattr(handler, data["method"])
    return await apply_fct(fct, data["parameters"], data["input"])
