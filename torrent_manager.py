import base64
import json
import random
import threading
import os
import libtorrent as lt



def gen_state(h, state):
    state_str = ['queued', 'checking', 'downloading metadata',
                 'downloading', 'finished', 'seeding', 'allocating',
                 'checking fastresume']
    if h.is_paused():
        return "paused"
    return state_str[state]


def gen_hooks_state(hooks, info_hash):
    ret = "waiting"
    if not info_hash in hooks:
        return "none"
    for hook in hooks[info_hash]:
        if hook["state"] == "working":
            return "working"
        elif hook["state"] == "error":
            return "error"
        elif hook["state"] == "completed":
            ret = "completed"
        elif hook["state"] == "pending":
            ret = "pending"
    return ret



def torrent_to_dict(h, hooks, full=False):
    s = h.status()
    info_hash = str(h.info_hash())
    ret = {"Name": h.name(),
           "InfoHash": info_hash,
           "Peers": s.num_peers,
           "Seeds": s.num_seeds,
           "Progress": s.progress,
           "DownRate": s.download_rate,
           "UpRate": s.upload_rate,
           "Size": s.total_wanted,
           "SizeDown": s.total_wanted_done,
           "SizeUp": s.all_time_upload,
           "State": gen_state(h, s.state),
           "HookState": gen_hooks_state(hooks, info_hash),
           "Position": s.queue_position}

    if not full:
        return ret

    ret["Path"] = h.save_path() + h.name()
    ret["Files"] = []
    files = h.get_torrent_info().files()
    for i in range(0, files.num_files()):
        ret["Files"].append({"ID": i, "Path": files.file_path(i), "Priority": h.file_priority(i)})

    return ret


def torrent_save_resume(h):
    flags = lt.save_resume_flags_t.flush_disk_cache | lt.save_resume_flags_t.save_info_dict
    h.save_resume_data(flags)


class FastResume:
    def __init__(self, file_path):
        self.file_path = file_path
        try:
            with open(self.file_path, "r") as f:
                self.data = json.load(f)
        except (json.decoder.JSONDecodeError, FileNotFoundError):
            print("error while charging fast resume ", file_path)
            self.data = []
            self.save()

    def get(self, torrent_hash):
        for el in self.data:
            if el["hash"] == torrent_hash:
                return el

    def add(self, data):
        previous = self.get(data["hash"])
        if previous:
            self.data.remove(previous)
        self.data.append(data)

    def remove(self, h):
        current = self.get(str(h.info_hash()))
        self.data.remove(current)

    def add_resume_data(self, h, data, hooks):
        new_data = {"name": h.get_torrent_info().name(),
                    "data": base64.b64encode(lt.bencode(data)).decode(),
                    "path": h.save_path(),
                    "hash": str(h.info_hash())}
        if hooks:
            new_data["hooks"] = hooks
        self.add(new_data)

    def save(self):
        with open(self.file_path, "w") as f:
            json.dump(self.data, f)

    def get_all(self):
        for el in self.data:
            yield el


class TorrentManager:
    def __init__(self, download_path="downloads", fast_resume_config="fast_resume.json", server=None):
        self.ses = lt.session()
        r = random.randrange(10000, 50000)+5
        self.ses.listen_on(r, r + 10)
        self.download_path = download_path
        self.torrents = []
        self.hooks = {}
        self.run = True
        self.server = server

        self.fast_resume = FastResume(fast_resume_config)

        for info in self.fast_resume.get_all():
            h = self.ses.add_torrent({'resume_data': base64.b64decode(info["data"]),
                                      'save_path': info["path"]})
            if h.is_valid():
                self.torrents.append(h)
                if "hooks" in info:
                    self.hooks[info["hash"]] = info["hooks"]
            else:
                print(f"error add torrent for fast_resume info {info}")

        settings = lt.default_settings()
        settings["alert_mask"] = settings["alert_mask"] | lt.alert.category_t.status_notification
        settings["listen_interfaces"] = "0.0.0.0:5550,[::]:5550"
        self.ses.apply_settings(settings)

        self.alert_thread = threading.Thread(target=self.alert_handler)
        self.alert_thread.start()

    def alert_handler(self):
        while True:
            if self.ses.wait_for_alert(1000):
                for a in self.ses.pop_alerts():
                    print(f"libtorrent::{a}")
                    if type(a) == lt.save_resume_data_alert:
                        self.fast_resume.add_resume_data(a.handle,
                                                         a.resume_data,
                                                         self.hooks.get(str(a.handle.info_hash())))

                    elif type(a) == lt.torrent_added_alert:
                        torrent_save_resume(a.handle)

                    elif type(a) == lt.torrent_finished_alert:
                        torrent_save_resume(a.handle)
                        info_hash = str(a.handle.info_hash())
                        if info_hash in self.hooks and gen_hooks_state(self.hooks, info_hash) == "waiting":
                            self.execute_hooks(info_hash)

                self.fast_resume.save()

            elif not self.run:
                break

    def add_torrent_file(self, path):
        info = lt.torrent_info(path)
        try:
            h = self.ses.add_torrent({'ti': info,
                                      'save_path': self.download_path,
                                      'storage_mode': lt.storage_mode_t(2)})

            if h.is_valid():
                self.torrents.append(h)

            return torrent_to_dict(h, self.hooks, full=True)
        except RuntimeError:
            h = self.get(str(info.info_hash()))
            if h:
                return torrent_to_dict(h, self.hooks, full=True)

    def get(self, info_hash):
        for h in self.torrents:
            if info_hash == str(h.info_hash()):
                return h

    def get_info(self, info_hash=None, full=False):
        ret = []
        for h in self.torrents:
            if not info_hash or info_hash == str(h.info_hash()):
                ret.append(torrent_to_dict(h, self.hooks, full=full))
        return ret

    def pause(self, info_hash=None):
        for h in self.torrents:
            if not info_hash or info_hash == str(h.info_hash()):
                if h.is_paused():
                    h.resume()
                else:
                    h.pause()

    def files(self, info_hash):
        ret = []
        h = self.get(info_hash)
        files = h.get_torrent_info().files()
        for i in range(0, files.num_files()):
            ret.append(files.file_path(i))
        return ret

    def path(self, info_hash):
        h = self.get(info_hash)
        return h.save_path()+"/"+h.name()

    def remove(self, info_hash):
        h = self.get(info_hash)
        self.ses.remove_torrent(h)
        if info_hash in self.hooks:
            del self.hooks[info_hash]
        self.torrents.remove(h)
        self.fast_resume.remove(h)

    def edit_hooks(self, info_hash, hooks):
        h = self.get(info_hash)
        base_path = h.save_path()
        for i in range(0, len(hooks)):
            hooks[i]["state"] = "waiting"
            hooks[i]["path"] = os.path.join(base_path, hooks[i]["path"])
        self.hooks[info_hash] = hooks
        h.save_resume_data(lt.save_resume_flags_t.flush_disk_cache | lt.save_resume_flags_t.save_info_dict)

        if h.status().progress == 1.0:
            self.execute_hooks(info_hash)

    def execute_hooks(self, info_hash):
        for i in range(0, len(self.hooks[info_hash])):
            self.hooks[info_hash][i]["state"] = "pending"
        self.server.send_bg_worker("send_worker", info_hash)

    def set_working(self, info_hash, path):
        hook = self.get_hook(info_hash, path)
        if hook is None:
            print(f"hookError::not found {info_hash}")
            return
        hook["state"] = "working"

    def get_hook(self, info_hash, path=None):
        if path is None:
            return self.hooks[info_hash]
        else:
            for hook in self.hooks[info_hash]:
                if hook["path"] == path:
                    return hook

    def callback_hook(self, info_hash, path, err=None):
        hook = self.get_hook(info_hash, path)
        if hook is None:
            print(f"hookError::not found {info_hash}")
            return
        elif err is not None:
            print(f"hookError::{err} {info_hash}")
            hook["state"] = "error"
        else:
            hook["state"] = "completed"

        self.get(info_hash).save_resume_data(
           lt.save_resume_flags_t.flush_disk_cache | lt.save_resume_flags_t.save_info_dict)

    def close(self):
        self.ses.pause()

        for torrent in self.torrents:
            torrent.save_resume_data(lt.save_resume_flags_t.flush_disk_cache | lt.save_resume_flags_t.save_info_dict)

        self.run = False
        self.alert_thread.join(timeout=10)

