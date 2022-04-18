import asyncio
import json
import os
import struct
import time

from parse_json_request import parse_endpoint, apply_end_point


async def send_init(writer, message):
    body = json.dumps(message).encode("utf8")
    await write_message(writer, 0x42, 0, body)



async def read_message(reader):
    data = await reader.read(13)
    if len(data) != 13:
        raise UnicomException("lost connection"," disconnected")
    kind, message_id, size = struct.unpack("<BQL", data)
    data = b""
    while len(data) < size:
        data += await reader.read(1024)

    return kind, message_id, data


async def write_message(writer, kind, message_id, data):
    if data is None:
        data = b""
    writer.write(struct.pack("<BQL", kind, message_id, len(data)))
    size = 0
    while len(data) > size:
        cdata = data[size:size+1024]
        writer.write(cdata)
        size += 1024
    await writer.drain()


def gen_load(size):
    ret = ""
    for i in range(0, size):
        ret += "z"
    return ret


class UnicomException(BaseException):
    def __init__(self, kind: str, description: str):
        self.kind = kind
        self.description = description
        BaseException.__init__(self, "UnicomException : "+self.kind+" - "+self.description)

    @staticmethod
    def from_message(data):
        data = json.loads(data)
        return UnicomException(data["kind"], data["description"])

    def to_message(self):
        return json.dumps({
            "kind": self.kind,
            "description": self.description
        }).encode()



class Pending:
    def __init__(self, c_id):
        self.event = asyncio.Event()
        self.id = c_id
        self.output = b""
        self.error = None

    def set_error(self, error):
        self.error = error
        self.event.set()

    def set_output(self, output):
        self.output = output
        self.event.set()

    def get(self):
        if self.error is None:
            return self.output
        raise self.error

    async def wait(self):
        await self.event.wait()


class Server:
    def __init__(self, addr, name):
        self.name = name
        self.l_end_points = []
        self.l_api = []
        self.l_template = []
        self.addr = addr
        self.id = 1
        self.pending = []
        self.reader, self.writer = None, None

    def add_folder_template(self, path, base=None):
        if base is None:
            base = self.name
        for r, d, f in os.walk(path):
            for file in f:
                template_location = os.path.join(base, r[len(path):], file)
                filename = os.path.join(r, file)
                self.add_template(filename, template_location)

    def add_template(self, file, path):
        file = os.path.abspath(file)
        self.l_template.append((file, path))

    def add_api_handler(self, handler):
        api_id = len(self.l_api)
        self.l_api.append((api_id, handler))
        return api_id

    def add_view(self, path, template, handler=None):
        api_id = None
        if handler is not None:
            api_id = self.add_api_handler(handler)
        self.l_end_points.append(("view", path, template, api_id))

    def add_api(self, path, handler):
        api_id = self.add_api_handler(handler)
        self.l_end_points.append(("api", path, api_id))

    def add_static_file(self, path, static_path):
        static_path = os.path.abspath(static_path)
        self.l_end_points.append(("static", path, static_path))

    def add_dynamic_file(self, path, handler):
        api_id = self.add_api_handler(handler)
        self.l_end_points.append(("dynamic", path, api_id))

    def config(self):
        ret = {
            "name": self.name,
            "end_points": [],
            "api": [],
            "templates": []
        }
        for end_point in self.l_end_points:
            if end_point[0] == "static":
                ret["end_points"].append({
                    "regex": end_point[1],
                    "kind": {"Static": {"path": end_point[2]}}
                })
            elif end_point[0] == "dynamic":
                ret["end_points"].append({
                    "regex": end_point[1],
                    "kind": {"DynamicFile": {"api_id": end_point[2]}}
                })
            elif end_point[0] == "view":
                ret["end_points"].append({
                    "regex": end_point[1],
                    "kind": {"View": {"api_id": end_point[3], "template": end_point[2]}}
                })
            elif end_point[0] == "api":
                ret["end_points"].append({
                    "regex": end_point[1],
                    "kind": {"Api": {"api_id": end_point[2]}}
                })

        for api in self.l_api:
            ret["api"].append(parse_endpoint(api[0], api[1]))

        for template in self.l_template:
            ret["templates"].append({"file": template[0], "path": template[1]})

        return ret

    def get_api_handler(self, s_api_id):
        for api_id, handler in self.l_api:
            if api_id == s_api_id:
                return handler

    async def serve(self):
        self.reader, self.writer = await asyncio.open_unix_connection(self.addr)
        print(self.config())
        await send_init(self.writer, self.config())
        self.id = 1
        print("connected")
        while True:

            kind, message_id, message = await read_message(self.reader)
            if kind == 0:
                self.get_pending(message_id).set_error(UnicomException.from_message(message))
            if kind == 1:
                asyncio.create_task(self.serve_request(message_id, message))
            elif kind == 2:
                self.get_pending(message_id).set_output(message)

    async def serve_forever(self):
        while True:
            try:
                await self.serve()
            except UnicomException as e:
                print(e)
                time.sleep(2)
            except ConnectionRefusedError:
                print("connection failed")
                time.sleep(10)

    async def serve_request(self, message_id, data):
        print(data)
        data = json.loads(data)
        handler = self.get_api_handler(data["id"])
        data["parameters"]["server"] = self
        try:
            response = await apply_end_point(handler, data)
            await write_message(self.writer, 2, message_id, response)
        except UnicomException as e:
            await write_message(self.writer, 0, message_id, e.to_message())
        except Exception as e:
            await write_message(self.writer, 0, message_id, UnicomException("Internal", str(e)).to_message())
            raise e

    def set_pending(self):
        pending = Pending(self.id)
        self.id += 1
        self.pending.append(pending)
        return pending

    def remove_pending(self, pending):
        self.pending.remove(pending)

    def get_pending(self, c_id):
        for pending in self.pending:
            if pending.id == c_id:
                return pending
        raise UnicomException("Internal", "message id not found")

    async def raw_request(self, data):
        pending = self.set_pending()
        message = json.dumps(data)
        await write_message(self.writer, 1, pending.id, message.encode())
        await pending.wait()
        self.remove_pending(pending)
        print(pending.error)
        return pending.get()

    async def request(self, target, method, path, parameters, input_value):
        return await self.raw_request({
            "target": target,
            "method": method,
            "path": path,
            "parameters": parameters,
            "input": input_value
        })
