import os
import toml
from torrent_manager import TorrentManager

class TorrentHandler:
    @staticmethod
    async def GET(server, info_hash: "url_1" = None, full: "int" = 0):
        torrent_manager = server.get_user_data("torrent_manager")
        if info_hash:
            info = torrent_manager.get_info(info_hash=info_hash, full=bool(full))
        else:
            info = torrent_manager.get_info(full=bool(full))
        return info

    @staticmethod
    async def PUT(server, input_data: "ipt", info_hash: "url_1"):
        torrent_manager = server.get_user_data("torrent_manager")
        for key in input_data:
            if key == "Hooks":
                torrent_manager.edit_hooks(info_hash, input_data[key])
            elif key == "Pause":
                torrent_manager.pause(info_hash)
        return b""

    @staticmethod
    async def POST(server, input_data: "ipt"):
        torrent_manager = server.get_user_data("torrent_manager")
        info = torrent_manager.add_torrent_file(input_data['path'])
        return info

    @staticmethod
    async def DELETE(server, info_hash: "url_1", file: "int" = 1):
        torrent_manager = server.get_user_data("torrent_manager")
        path = torrent_manager.path(info_hash)
        torrent_manager.remove(info_hash)
        if file:
            os.remove(path)


async def config(server):
    torrent_config = toml.load("./torrent_config.toml")

    server.create_user_data("torrent_manager", TorrentManager(download_path=torrent_config["download_path"],
                                       fast_resume_config=os.path.join(torrent_config["download_path"], ".fast_resume.json"),
                                       server=server))
    server.create_bg_worker("send_worker", send_worker)
    
    s = server.config
    s.add_api("TorrentHandler", TorrentHandler)
    return s


async def send_worker(server, info_hash):
    torrent_manager = server.get_user_data("torrent_manager")
    for hook in torrent_manager.get_hook(info_hash):
        try:
            torrent_manager.set_working(info_hash, hook["path"])
            print(hook)
            await server.request("MediaServer", "VideoHandler", "POST", user="torrent", input_data=hook)
            torrent_manager.callback_hook(info_hash, hook["path"])
        except Exception as e:
            print(e)
            torrent_manager.callback_hook(info_hash, hook["path"], err=str(e))


async def close(server):
    server.get_user_data("torrent_manager").close()
    print("torrent stored")



