import asyncio
import json
import os
import toml
import janus

from torrent_manager import TorrentManager
from unicom import Server


config = toml.load("./config.toml")
loop = asyncio.get_event_loop()
s = Server(config["stream"], "torrent")


class TorrentHandler:
    @staticmethod
    async def GET(server, url, full: int = 0):
        if len(url[1]) > 0:
            info = server.torrent_manager.get_info(info_hash=url[1], full=bool(full))
        else:
            info = server.torrent_manager.get_info(full=bool(full))
        return json.dumps(info).encode()

    @staticmethod
    async def PUT(server, url, input_data: "Json"):
        if len(url[1]) == 0:
            raise Exception("no hash")
        info_hash = url[1]
        for key in input_data:
            if key == "Hooks":
                server.torrent_manager.edit_hooks(info_hash, input_data[key])
            elif key == "Pause":
                server.torrent_manager.pause(info_hash)
        return b""

    @staticmethod
    async def POST(server, input_data: "File"):
        info = server.torrent_manager.add_torrent_file(input_data['path'])
        return json.dumps(info).encode()

    @staticmethod
    async def DELETE(server, url, file: int = 1):
        if len(url[1]) == 0:
            raise Exception("no hash")
        info_hash = url[1]
        path = server.torrent_manager.path(info_hash)
        server.torrent_manager.remove(info_hash)
        if file:
            os.remove(path)


async def connector(server):
    while server.torrent_manager.run:
        info_hash = await server.queue.async_q.get()
        for hook in server.torrent_manager.get_hook(info_hash):
            try:
                server.torrent_manager.set_working(info_hash, hook["path"])
                data = await server.request("mediaserver", "POST", "/mediaserver/api/video", {"user": "torrent"}, hook)
                server.torrent_manager.callback_hook(info_hash, hook["path"])
            except Exception as e:
                server.torrent_manager.callback_hook(info_hash, hook["path"], err=str(e))


async def main():
    s.queue = janus.Queue()
    s.download_path = config["download_path"]

    s.torrent_manager = TorrentManager(download_path=s.download_path,
                                       fast_resume_config=os.path.join(s.download_path, ".fast_resume.json"),
                                       connector_queue=s.queue.sync_q)

    s.add_folder_template("./templates/")

    s.add_view(r"^/$", "torrent/index.html")
    s.add_view(r"^/modalTorrent$", "torrent/modalTorrent.html")

    s.add_api(r"^/api/torrent(?:/([0-9a-f]+))?$", TorrentHandler)

    s.add_static_file(r"^/js/(.*\.js)$", "js/")

    input_coroutines = [s.serve_forever(), connector(s)]

    await asyncio.gather(*input_coroutines, return_exceptions=True)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    finally:
        print("try to close torrent")
        s.torrent_manager.close()


