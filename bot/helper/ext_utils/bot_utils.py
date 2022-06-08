from re import match as re_match, findall as re_findall
from threading import Thread, Event
from time import time
from math import ceil
from html import escape
from psutil import virtual_memory, cpu_percent, disk_usage
from requests import head as rhead
from urllib.request import urlopen
from telegram import InlineKeyboardMarkup

from bot.helper.telegram_helper.bot_commands import BotCommands
from bot import download_dict, download_dict_lock, STATUS_LIMIT, botStartTime, DOWNLOAD_DIR
from bot.helper.telegram_helper.button_build import ButtonMaker

MAGNET_REGEX = r"magnet:\?xt=urn:btih:[a-zA-Z0-9]*"

URL_REGEX = r"(?:(?:https?|ftp):\/\/)?[\w/\-?=%.]+\.[\w/\-?=%.]+"

COUNT = 0
PAGE_NO = 1


class MirrorStatus:
    STATUS_UPLOADING = "𝐔𝐩𝐥𝐨𝐚𝐝𝐢𝐧𝐠...📤"
    STATUS_DOWNLOADING = "𝐃𝐨𝐰𝐧𝐥𝐨𝐚𝐝𝐢𝐧𝐠...📥"
    STATUS_CLONING = "𝐂𝐥𝐨𝐧𝐢𝐧𝐠...♻️"
    STATUS_WAITING = "𝐐𝐮𝐞𝐮𝐞𝐝...💤"
    STATUS_FAILED = "𝐅𝐚𝐢𝐥𝐞𝐝 🚫. 𝐂𝐥𝐞𝐚𝐧𝐢𝐧𝐠 𝐃𝐨𝐰𝐧𝐥𝐨𝐚𝐝..."
    STATUS_PAUSE = "𝐏𝐚𝐮𝐬𝐞𝐝...⛔️"
    STATUS_ARCHIVING = "𝐀𝐫𝐜𝐡𝐢𝐯𝐢𝐧𝐠...🔐"
    STATUS_EXTRACTING = "𝐄𝐱𝐭𝐫𝐚𝐜𝐭𝐢𝐧𝐠...📂"
    STATUS_SPLITTING = "𝐒𝐩𝐥𝐢𝐭𝐭𝐢𝐧𝐠...✂️"
    STATUS_CHECKING = "𝐂𝐡𝐞𝐜𝐤𝐢𝐧𝐠𝐔𝐩...📝"
    STATUS_SEEDING = "𝐒𝐞𝐞𝐝𝐢𝐧𝐠...🌧"

SIZE_UNITS = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']


class setInterval:
    def __init__(self, interval, action):
        self.interval = interval
        self.action = action
        self.stopEvent = Event()
        thread = Thread(target=self.__setInterval)
        thread.start()

    def __setInterval(self):
        nextTime = time() + self.interval
        while not self.stopEvent.wait(nextTime - time()):
            nextTime += self.interval
            self.action()

    def cancel(self):
        self.stopEvent.set()

def get_readable_file_size(size_in_bytes) -> str:
    if size_in_bytes is None:
        return '0B'
    index = 0
    while size_in_bytes >= 1024:
        size_in_bytes /= 1024
        index += 1
    try:
        return f'{round(size_in_bytes, 2)}{SIZE_UNITS[index]}'
    except IndexError:
        return 'File too large'

def getDownloadByGid(gid):
    with download_dict_lock:
        for dl in list(download_dict.values()):
            status = dl.status()
            if (
                status
                not in [
                    MirrorStatus.STATUS_ARCHIVING,
                    MirrorStatus.STATUS_EXTRACTING,
                    MirrorStatus.STATUS_SPLITTING,
                ]
                and dl.gid() == gid
            ):
                return dl
    return None

def getAllDownload(req_status: str):
    with download_dict_lock:
        for dl in list(download_dict.values()):
            status = dl.status()
            if status not in [MirrorStatus.STATUS_ARCHIVING, MirrorStatus.STATUS_EXTRACTING, MirrorStatus.STATUS_SPLITTING] and dl:
                if req_status == 'down' and (status not in [MirrorStatus.STATUS_SEEDING,
                                                            MirrorStatus.STATUS_UPLOADING,
                                                            MirrorStatus.STATUS_CLONING]):
                    return dl
                elif req_status == 'up' and status == MirrorStatus.STATUS_UPLOADING:
                    return dl
                elif req_status == 'clone' and status == MirrorStatus.STATUS_CLONING:
                    return dl
                elif req_status == 'seed' and status == MirrorStatus.STATUS_SEEDING:
                    return dl
                elif req_status == 'all':
                    return dl
    return None

def get_progress_bar_string(status):
    completed = status.processed_bytes() / 8
    total = status.size_raw() / 8
    p = 0 if total == 0 else round(completed * 100 / total)
    p = min(max(p, 0), 100)
    cFull = p // 8
    p_str = '●' * cFull
    p_str += '○' * (12 - cFull)
    p_str = f"〔{p_str}〕"
    return p_str

def get_readable_message():
    with download_dict_lock:
        msg = ""
        if STATUS_LIMIT is not None:
            tasks = len(download_dict)
            global pages
            pages = ceil(tasks/STATUS_LIMIT)
            if PAGE_NO > pages and pages != 0:
                globals()['COUNT'] -= STATUS_LIMIT
                globals()['PAGE_NO'] -= 1
        for index, download in enumerate(list(download_dict.values())[COUNT:], start=1):
            msg += f"<b>⋖ SσυʅLαɳԃ Lҽҽƈԋҽɾ ⋗</b>"
            msg += f"\n<b>┏ ⊹𝐍𝐚𝐦𝐞:</b> <code>{escape(str(download.name()))}</code>"
            msg += f"\n<b>┣ ⊹𝐒𝐭𝐚𝐭𝐮𝐬:</b> <i>{download.status()}</i>"
            if download.status() not in [
                MirrorStatus.STATUS_ARCHIVING,
                MirrorStatus.STATUS_EXTRACTING,
                MirrorStatus.STATUS_SPLITTING,
                MirrorStatus.STATUS_SEEDING,
            ]:
                msg += f"\n<b>┣</b> ⊹{get_progress_bar_string(download)} {download.progress()}"
                if download.status() == MirrorStatus.STATUS_CLONING:
                    msg += f"\n<b>┣ ⊹𝐂𝐥𝐨𝐧𝐞𝐝:</b> {get_readable_file_size(download.processed_bytes())} 𝐨𝐟 {download.size()}"
                elif download.status() == MirrorStatus.STATUS_UPLOADING:
                    msg += f"\n<b>┣ ⊹𝐔𝐩𝐥𝐨𝐚𝐝𝐞𝐝:</b> {get_readable_file_size(download.processed_bytes())} 𝐨𝐟 {download.size()}"
                else:
                    msg += f"\n<b>┣ ⊹𝐃𝐨𝐰𝐧𝐥𝐨𝐚𝐝𝐞𝐝:</b> {get_readable_file_size(download.processed_bytes())} 𝐨𝐟 {download.size()}"
                msg += f"\n<b>┣ ⊹𝐒𝐩𝐞𝐞𝐝:</b> {download.speed()} | <b>⊹𝐄𝐓𝐀:</b> {download.eta()}"
                try:
                    msg += f"\n<b>┣ ⊹𝐒𝐞𝐞𝐝𝐞𝐫𝐬:</b> {download.aria_download().num_seeders}" \
                           f" | <b>⊹𝐏𝐞𝐞𝐫𝐬:</b> {download.aria_download().connections}"
                    msg += f"\n<b>┣ ⊹𝐄𝐧𝐠𝐢𝐧𝐞:</b> <code>𝐀𝐫𝐢𝐚𝟐𝐜 𝐯𝟏.𝟑𝟓.𝟎</code>"
                except:
                    pass
                try:
                    msg += f"\n<b>┣ ⊹𝐒𝐞𝐞𝐝𝐞𝐫𝐬:</b> {download.torrent_info().num_seeds}" \
                           f" | <b>⊹𝐋𝐞𝐞𝐜𝐡𝐞𝐫𝐬:</b> {download.torrent_info().num_leechs}"
                    msg += f"\n<b>┣ ⊹𝐄𝐧𝐠𝐢𝐧𝐞:</b> <code>𝐪𝐁𝐢𝐭𝐭𝐨𝐫𝐫𝐞𝐧𝐭 𝐯𝟒.𝟒.𝟐</code>"
                except:
                    pass
                msg += f"\n<b>┣ ⊹𝐔𝐬𝐞𝐫:</b> ️<a href='tg://user?id={download.message.from_user.id}'>{download.message.from_user.first_name}</a>"
                msg += f"\n<b>┣ ⊹𝐄𝐥𝐚𝐩𝐬𝐞𝐝: </b>{get_readable_time(time() - download.message.date.timestamp())}"
                msg += f"\n<b>┗ ⊹𝐂𝐚𝐧𝐜𝐞𝐥:</b> <code>/{BotCommands.CancelMirror} {download.gid()}</code>"
            elif download.status() == MirrorStatus.STATUS_SEEDING:
                msg += f"\n<b>┣ ⊹𝐒𝐢𝐳𝐞: </b>{download.size()}"
                msg += f"\n<b>┣ ⊹𝐒𝐩𝐞𝐞𝐝: </b>{get_readable_file_size(download.torrent_info().upspeed)}/s"
                msg += f" | <b>┣ ⊹𝐔𝐩𝐥𝐨𝐚𝐝𝐞𝐝: </b>{get_readable_file_size(download.torrent_info().uploaded)}"
                msg += f"\n<b>┣ ⊹𝐑𝐚𝐭𝐢𝐨: </b>{round(download.torrent_info().ratio, 3)}"
                msg += f" | <b>┣ ⊹𝐓𝐢𝐦𝐞: </b>{get_readable_time(download.torrent_info().seeding_time)}"
                msg += f"\n<b>┣ ⊹𝐔𝐬𝐞𝐫:</b> ️<a href='tg://user?id={download.message.from_user.id}'>{download.message.from_user.first_name}</a>"
                msg += f"\n<b>┣ ⊹𝐄𝐥𝐚𝐩𝐬𝐞𝐝: </b>{get_readable_time(time() - download.message.date.timestamp())}"
                msg += f"\n<b>┗ ⊹𝐂𝐚𝐧𝐜𝐞𝐥:</b> <code>/{BotCommands.CancelMirror} {download.gid()}</code>"
            else:
                msg += f"\n<b>┣ ⊹𝐒𝐢𝐳𝐞: </b>{download.size()}"
            msg += "\n\n"
            if STATUS_LIMIT is not None and index == STATUS_LIMIT:
                break
        bmsg = f"<b>┏ ▫️𝐂𝐏𝐔:</b> {cpu_percent()}% | <b>▫️𝐅𝐑𝐄𝐄:</b> {get_readable_file_size(disk_usage(DOWNLOAD_DIR).free)}"
        bmsg += f"\n<b>┣ ▪️𝐑𝐀𝐌:</b> {virtual_memory().percent}% | <b>⏱️𝐔𝐏𝐓𝐈𝐌𝐄:</b> {get_readable_time(time() - botStartTime)}"
        dlspeed_bytes = 0
        upspeed_bytes = 0
        for download in list(download_dict.values()):
            spd = download.speed()
            if download.status() == MirrorStatus.STATUS_DOWNLOADING:
                if 'K' in spd:
                    dlspeed_bytes += float(spd.split('K')[0]) * 1024
                elif 'M' in spd:
                    dlspeed_bytes += float(spd.split('M')[0]) * 1048576
            elif download.status() == MirrorStatus.STATUS_UPLOADING:
                if 'KB/s' in spd:
                    upspeed_bytes += float(spd.split('K')[0]) * 1024
                elif 'MB/s' in spd:
                    upspeed_bytes += float(spd.split('M')[0]) * 1048576
        bmsg += f"\n<b>┗ 📥𝐃𝐋:</b> {get_readable_file_size(dlspeed_bytes)}/s | <b>📤𝐔𝐋:</b> {get_readable_file_size(upspeed_bytes)}/s"
        if STATUS_LIMIT is not None and tasks > STATUS_LIMIT:
            msg += f"<b>🔹𝐏𝐚𝐠𝐞:</b> {PAGE_NO}/{pages} | <b>🔸𝐓𝐚𝐬𝐤𝐬:</b> {tasks}\n"
            buttons = ButtonMaker()
            buttons.sbutton("⬅️Previous", "status pre")
            buttons.sbutton("Next➡️", "status nex")
            button = InlineKeyboardMarkup(buttons.build_menu(2))
            return msg + bmsg, button
        return msg + bmsg, ""

def turn(data):
    try:
        with download_dict_lock:
            global COUNT, PAGE_NO
            if data[1] == "nex":
                if PAGE_NO == pages:
                    COUNT = 0
                    PAGE_NO = 1
                else:
                    COUNT += STATUS_LIMIT
                    PAGE_NO += 1
            elif data[1] == "pre":
                if PAGE_NO == 1:
                    COUNT = STATUS_LIMIT * (pages - 1)
                    PAGE_NO = pages
                else:
                    COUNT -= STATUS_LIMIT
                    PAGE_NO -= 1
        return True
    except:
        return False

def get_readable_time(seconds: int) -> str:
    result = ''
    (days, remainder) = divmod(seconds, 86400)
    days = int(days)
    if days != 0:
        result += f'{days}d'
    (hours, remainder) = divmod(remainder, 3600)
    hours = int(hours)
    if hours != 0:
        result += f'{hours}h'
    (minutes, seconds) = divmod(remainder, 60)
    minutes = int(minutes)
    if minutes != 0:
        result += f'{minutes}m'
    seconds = int(seconds)
    result += f'{seconds}s'
    return result

def is_url(url: str):
    url = re_findall(URL_REGEX, url)
    return bool(url)

def is_gdrive_link(url: str):
    return "drive.google.com" in url

def is_gdtot_link(url: str):
    url = re_match(r'https?://.+\.gdtot\.\S+', url)
    return bool(url)

def is_mega_link(url: str):
    return "mega.nz" in url or "mega.co.nz" in url

def get_mega_link_type(url: str):
    if "folder" in url:
        return "folder"
    elif "file" in url:
        return "file"
    elif "/#F!" in url:
        return "folder"
    return "file"

def is_magnet(url: str):
    magnet = re_findall(MAGNET_REGEX, url)
    return bool(magnet)

def new_thread(fn):
    """To use as decorator to make a function call threaded.
    Needs import
    from threading import Thread"""

    def wrapper(*args, **kwargs):
        thread = Thread(target=fn, args=args, kwargs=kwargs)
        thread.start()
        return thread

    return wrapper

def get_content_type(link: str) -> str:
    try:
        res = rhead(link, allow_redirects=True, timeout=5, headers = {'user-agent': 'Wget/1.12'})
        content_type = res.headers.get('content-type')
    except:
        try:
            res = urlopen(link, timeout=5)
            info = res.info()
            content_type = info.get_content_type()
        except:
            content_type = None
    return content_type

