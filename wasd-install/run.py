#!/usr/bin/env python3
"""Open Install WASD.

The window is Qt 6 QML. This launcher is how it runs on a machine whose
qml command is not wired to Qt 6. The erase button writes a choice file.
On this preview it does not partition, format, or erase a disk.
"""

import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from disks import default_disk, live_payload, parse_disks

HERE = Path(__file__).resolve().parent
REPO = HERE.parent


def _shown(item):
    while item is not None:
        if item.property("visible") is False:
            return False
        item = item.parent()
    return True
FIXTURE = {
    "blockdevices": [
        {
            "name": "nvme0n1",
            "type": "disk",
            "size": "1.8T",
            "model": "Samsung SSD 990 PRO",
            "children": [
                {"name": "nvme0n1p1", "fstype": "vfat", "label": "EFI"},
                {"name": "nvme0n1p2", "fstype": "BitLocker"},
            ],
        },
        {
            "name": "nvme1n1",
            "type": "disk",
            "size": "931.5G",
            "model": "WD_BLACK SN850X",
            "children": [{"name": "nvme1n1p1", "fstype": "ext4", "label": "fedora"}],
        },
        {
            "name": "sda",
            "type": "disk",
            "size": "4T",
            "model": "Empty Shelf",
            "children": [],
        },
        {"name": "loop0", "type": "loop", "size": "1G"},
        {"name": "sr0", "type": "rom", "size": "2G"},
    ]
}

ICON_ORDER = [
    "knight.jpg",
    "superhero-female.jpg",
    "pilot.jpg",
    "fox.jpg",
    "wizard.jpg",
    "soldier.jpg",
    "gunslinger.jpg",
    "archer.jpg",
    "wolf-brawler.jpg",
    "superhero.jpg",
]
LOADING_ORDER = [
    "stained-glass.jpg",
    "keysketch.jpg",
    "throne.jpg",
    "space.jpg",
    "cell-shaded.jpg",
    "crystal-energy-veins.jpg",
    "ornate-golden-vine-and-leaf.jpg",
    "steampunk-glowing-green-vines.jpg",
    "torn-paper.jpg",
    "zerog.jpg",
]
LOGIN_ORDER = ["throne.jpg", "camp.png"]
WALL_ORDER = ["stained-glass.jpg"]
def ordered(folder, preferred, skip=()):
    exts = {".jpg", ".jpeg", ".png", ".webp"}
    found = []
    for path in Path(folder).iterdir():
        if path.name in skip or not path.is_file():
            continue
        if path.suffix.lower() not in exts:
            continue
        found.append(path.name)
    rank = {name: index for index, name in enumerate(preferred)}
    return sorted(found, key=lambda name: (rank.get(name, 1000), name.lower()))


def file_lists():
    return {
        "icons": ordered(REPO / "wasd-icons", ICON_ORDER, skip={"wasd-logo.png"}),
        "loading": ordered(REPO / "wasd-loading-screens", LOADING_ORDER),
        "login": ordered(REPO / "wasd-login-screens", LOGIN_ORDER),
        "wallpapers": ordered(REPO / "wasd-wallpapers", WALL_ORDER),
    }


def search_flathub(query):
    query = query.strip()
    if len(query) < 2:
        return []
    req = urllib.request.Request(
        "https://flathub.org/api/v2/search",
        data=json.dumps({"query": query}).encode(),
        method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "wasd-install"},
    )
    try:
        with urllib.request.urlopen(req, timeout=4) as res:
            data = json.load(res)
    except Exception:
        return []
    found = []
    for hit in data.get("hits") or []:
        if hit.get("type") != "desktop-application":
            continue
        app_id = hit.get("app_id") or ""
        name = hit.get("name") or app_id
        if not app_id or not name:
            continue
        found.append({"name": name, "id": app_id})
        if len(found) >= 6:
            break
    return found


def check_parser():
    disks = parse_disks(FIXTURE)
    names = [disk["name"] for disk in disks]
    if names != ["Samsung SSD 990 PRO", "WD BLACK SN850X", "Empty Shelf"]:
        raise SystemExit(f"disk names {names}")
    if [disk["device"] for disk in disks] != ["nvme0n1", "nvme1n1", "sda"]:
        raise SystemExit(f"disk devices {[disk['device'] for disk in disks]}")
    if not (disks[0]["windows"] and disks[0]["occupied"]):
        raise SystemExit("bitlocker disk was not marked Windows")
    if disks[1]["windows"] or not disks[1]["occupied"]:
        raise SystemExit("linux disk was classified wrong")
    if disks[2]["occupied"] or disks[2]["windows"]:
        raise SystemExit("empty disk was classified wrong")
    if default_disk(disks) != 2:
        raise SystemExit("default disk was not the empty one")
    if any(disk["games"] for disk in disks) or disks[0]["part"] or disks[0]["uuid"]:
        raise SystemExit(f"windows disk looked like a games drive {disks[0]}")
    if disks[1]["part"] != "nvme1n1p1" or disks[1]["fstype"] != "ext4":
        raise SystemExit(f"linux disk kept no partition {disks[1]}")
    if disks[2]["part"] or disks[2]["fstype"]:
        raise SystemExit(f"empty disk kept a partition {disks[2]}")


def qml_app(save_path, shot_dir, live):
    if shot_dir:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        os.environ.setdefault("QT_QUICK_BACKEND", "software")
        os.environ.setdefault("QSG_RHI_BACKEND", "sw")
    from PySide6.QtCore import QEventLoop, QMetaObject, QObject, Qt, QTimer, QUrl, Q_ARG, Signal, Slot
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuick import QQuickItem, QQuickWindow
    import shiboken6

    class Bridge(QObject):
        found = Signal(str)

        def __init__(self, path):
            super().__init__()
            self.path = Path(path)

        @Slot(str)
        def save(self, text):
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(text)
            os.chmod(self.path, 0o600)

        @Slot(str)
        def search(self, query):
            self.found.emit(json.dumps(search_flathub(query)))

    app = QGuiApplication(sys.argv)
    bridge = Bridge(save_path)
    engine = QQmlApplicationEngine()
    engine.warnings.connect(lambda warning: print("\n".join(item.toString() for item in warning) if isinstance(warning, list) else warning, file=sys.stderr))
    context = engine.rootContext()
    context.setContextProperty("WasdRepo", str(REPO))
    context.setContextProperty("WasdFilesJson", json.dumps(file_lists()))
    context.setContextProperty("WasdBridge", bridge)
    engine.load(QUrl.fromLocalFile(str(HERE / "Main.qml")))
    if not engine.rootObjects():
        raise SystemExit("Install WASD failed to open")
    window = engine.rootObjects()[0]
    quick = shiboken6.wrapInstance(shiboken6.getCppPointer(window)[0], QQuickWindow)

    def pump(ms):
        loop = QEventLoop()
        QTimer.singleShot(ms, loop.quit)
        loop.exec()

    def grab(path):
        app.processEvents()
        pump(400)
        image = quick.grabWindow()
        if image.isNull() or image.width() < 100:
            raise SystemExit(f"could not capture {path}")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        if not image.save(str(path)):
            raise SystemExit(f"could not write {path}")

    if live:
        window.applyLive(json.dumps(live_payload()))
    window.show()
    pump(300)

    if shot_dir:
        shot = Path(shot_dir)
        quick.requestActivate()
        app.processEvents()
        opened_name = quick.findChild(QQuickItem, "userNameField")
        if opened_name is None or opened_name.property("activeFocus") is not True:
            focused = None if opened_name is None else opened_name.property("activeFocus")
            raise SystemExit(f"username field did not take focus: {focused}")
        if window.property("hostname") != "wasd":
            raise SystemExit("hostname did not start as wasd")
        if window.property("userName") not in ("", None):
            raise SystemExit("username did not start empty")
        if window.property("setPassword"):
            raise SystemExit("password checkbox did not start off")
        pages = [
            ("user", {"page": 0}),
            ("look", {"page": 1, "lookOpen": ""}),
            ("look-open", {"page": 1, "lookOpen": "loading"}),
            ("apps", {"page": 2, "appsOpen": "general"}),
            ("launchers", {"page": 2, "appsOpen": "launchers"}),
            ("agents", {"page": 2, "appsOpen": "agents"}),
            ("system", {"page": 3, "networkOpen": False}),
            ("disk", {"page": 4}),
        ]
        for name, props in pages:
            for key, value in props.items():
                window.setProperty(key, value)
            if name == "user":
                window.setProperty("userName", "rowge")
                name_field = quick.findChild(QQuickItem, "userNameField")
                if name_field is None:
                    raise SystemExit("username field is missing")
                name_field.setProperty("text", "rowge")
                expected_lines = {
                    "passwordCheckedLine": "CHECKING this means you will have to type your password sometimes.",
                    "passwordOpenLine": "NOT checking this means hitting enter instead of typing a password AND",
                    "passwordAccessLine": "anyone with physical access to this computer is YOU",
                }
                for object_name, expected in expected_lines.items():
                    item = quick.findChild(QQuickItem, object_name)
                    if item is None or item.property("text") != expected:
                        actual = None if item is None else item.property("text")
                        raise SystemExit(f"{object_name} was {actual}")
                grab(shot / f"{name}.png")
                window.setProperty("userName", "alex")
                continue
            grab(shot / f"{name}.png")
        window.setProperty("page", 4)
        window.setProperty("gamesOpen", False)
        pump(50)
        games_head = quick.findChild(QQuickItem, "gamesDrive")
        if games_head is None or games_head.property("text") != "/games":
            raise SystemExit(f"/games is missing from Disk: {None if games_head is None else games_head.property('text')}")
        if quick.findChild(QQuickItem, "gamesPartition") is not None:
            raise SystemExit("the /games checkbox is still on the page")
        fork = quick.findChild(QQuickItem, "chooseGamesButton")
        label = quick.findChild(QQuickItem, "chooseGamesLabel")
        if fork is None or not _shown(fork) or label is None or label.property("text") != "Set up /games":
            raise SystemExit("the /games button is missing")
        slider = quick.findChild(QQuickItem, "osGbBox")
        if slider is not None and _shown(slider):
            raise SystemExit("the slider showed before Set up /games")
        if not QMetaObject.invokeMethod(window, "openGamesSection"):
            raise SystemExit("openGamesSection did not run")
        pump(50)
        if window.property("gamesOpen") is not True:
            raise SystemExit("/games stayed closed")
        if window.property("gamesMode") != "off":
            raise SystemExit("Set up /games split a second drive before a drive was chosen")
        if window.property("showEraseButton") is not False:
            raise SystemExit("the whole-disk button stayed up before a games choice")
        early_erase = quick.findChild(QQuickItem, "eraseButtonLabel")
        if early_erase is not None and _shown(early_erase):
            raise SystemExit("the whole-disk button was still visible")
        if label.property("text") != "I changed my mind. Use the whole drive.":
            raise SystemExit(f"the games button was {label.property('text')}")
        if not QMetaObject.invokeMethod(window, "pickGamesDrive", Qt.ConnectionType.DirectConnection, Q_ARG("QVariant", 0)):
            raise SystemExit("pickGamesDrive did not run for the install drive")
        pump(50)
        if window.property("gamesMode") != "split" or int(window.property("gamesDiskIndex")) != -1:
            raise SystemExit(f"the install drive did not open the slider: {window.property('gamesMode')}")
        if slider is None or not _shown(slider):
            raise SystemExit("the slider stayed hidden on the install drive")
        disk_scroll = quick.findChild(QQuickItem, "diskScroll")
        if disk_scroll is None:
            raise SystemExit("the disk page does not scroll")
        disk_scroll.setProperty("contentY", max(0, games_head.property("y") - 12))
        grab(shot / "disk-games-split.png")
        if not QMetaObject.invokeMethod(window, "clearGames"):
            raise SystemExit("clearGames did not run before the other drive")
        pump(50)
        if window.property("gamesMode") != "off":
            raise SystemExit("the install-drive split stayed on")
        disk_scroll.setProperty("contentY", max(0, games_head.property("y") - 12))
        grab(shot / "disk-games.png")
        if not QMetaObject.invokeMethod(window, "pickGamesDrive", Qt.ConnectionType.DirectConnection, Q_ARG("QVariant", 1)):
            raise SystemExit("pickGamesDrive did not run")
        pump(50)
        if int(window.property("confirmStep") or 0) != 0 or window.property("gamesMode") != "off":
            raise SystemExit("a locked Windows drive opened a choice")
        if not QMetaObject.invokeMethod(window, "clearGames"):
            raise SystemExit("clearGames did not run")
        pump(50)
        if window.property("gamesMode") != "off":
            raise SystemExit("games choice stayed on")
        if not QMetaObject.invokeMethod(
            window,
            "beginConfirm",
            Qt.ConnectionType.DirectConnection,
            Q_ARG("QVariant", "gamesWipe"),
            Q_ARG("QVariant", 1),
            Q_ARG("QVariant", False),
        ):
            raise SystemExit("beginConfirm did not run")
        pump(50)
        if int(window.property("confirmStep") or 0) != 1:
            raise SystemExit("the wipe question did not open")
        if "Windows is on this drive." not in str(window.confirmTitle()):
            raise SystemExit(f"windows question was {window.confirmTitle()}")
        if not QMetaObject.invokeMethod(window, "confirmNo"):
            raise SystemExit("confirmNo did not run")
        pump(50)
        if int(window.property("confirmStep") or 0) != 0 or window.property("gamesMode") != "off":
            raise SystemExit("no did not cancel the wipe")
        if not QMetaObject.invokeMethod(window, "pickGamesDrive", Qt.ConnectionType.DirectConnection, Q_ARG("QVariant", 0)):
            raise SystemExit("pickGamesDrive did not split the install drive again")
        pump(50)
        if window.property("gamesMode") != "split":
            raise SystemExit("the install drive did not split before the other drive was chosen")
        if not QMetaObject.invokeMethod(
            window,
            "beginConfirm",
            Qt.ConnectionType.DirectConnection,
            Q_ARG("QVariant", "gamesWipe"),
            Q_ARG("QVariant", 1),
            Q_ARG("QVariant", False),
        ):
            raise SystemExit("beginConfirm did not run again")
        if not QMetaObject.invokeMethod(window, "confirmYes"):
            raise SystemExit("the yes click did not run")
        pump(50)
        if window.property("gamesMode") != "format" or int(window.property("gamesDiskIndex") or -1) != 1:
            raise SystemExit(f"windows drive was not accepted for games: {window.property('gamesMode')}")
        if window.property("gamesConfirmed") is not True:
            raise SystemExit("the games wipe was not confirmed")
        if int(window.property("diskIndex")) != 0:
            raise SystemExit(f"choosing /games cleared the WASD drive: {window.property('diskIndex')}")
        if not QMetaObject.invokeMethod(window, "clearGames"):
            raise SystemExit("clearGames did not run after the questions")
        window.setProperty("diskIndex", 0)
        window.setProperty("gamesOpen", False)
        disk_scroll.setProperty("contentY", 0)
        window.setProperty("page", 2)
        window.setProperty("appsOpen", "agents")
        pump(50)
        scroll = quick.findChild(QQuickItem, "pageScroll")
        if scroll is not None:
            height = scroll.property("height") or 0
            content = scroll.property("contentHeight") or 0
            scroll.setProperty("contentY", max(0, content - height))
            grab(shot / "agents-end.png")
        window.saveChoices()
        pump(100)
        text = Path(save_path).read_text()
        data = json.loads(text)
        if data["hostname"] != "wasd" or data["user"] != "alex" or data["password"] is not False:
            raise SystemExit(f"unexpected choices {data}")
        saved_ids = [app.get("id") for app in data.get("apps") or []]
        if "com.brave.Browser" in saved_ids or len(saved_ids) != 23:
            raise SystemExit(f"the app list was {saved_ids}")
        if data.get("login") != "throne.jpg":
            raise SystemExit(f"login default was {data.get('login')}")
        if data.get("avatar") != "knight.jpg":
            raise SystemExit(f"avatar default was {data.get('avatar')}")
        if data.get("theme") != "We10XOS-dark":
            raise SystemExit(f"theme was {data.get('theme')}")
        if data.get("device") != "":
            raise SystemExit(f"sample disk stored a device {data.get('device')}")
        if "not-stored" in text or "passwordAgain" in text or "passphrase" in text or "wpakey" in text:
            raise SystemExit("choice file kept a secret")
        if not str(window.property("networkStatus") or "").startswith("Connected."):
            raise SystemExit(f"network status was {window.property('networkStatus')}")
        window.setProperty("setPassword", True)
        window.setProperty("password", "not-stored")
        window.setProperty("passwordAgain", "not-stored")
        window.setProperty("page", 4)
        window.saveChoices()
        pump(100)
        secret_text = Path(save_path).read_text()
        if "not-stored" in secret_text:
            raise SystemExit("password was written to the choice file")
        secret = json.loads(secret_text)
        if secret["password"] is not True:
            raise SystemExit("password flag was not recorded")
        window.setProperty("page", 0)
        grab(shot / "user-checked.png")
        if not QMetaObject.invokeMethod(window, "encodeChoices"):
            raise SystemExit("encodeChoices did not run")
        pump(50)
        import base64

        encoded = window.property("encodedChoices") or ""
        try:
            raw = base64.b64decode(encoded, validate=True)
        except Exception as exc:
            raise SystemExit(f"choices were not encoded: {exc}") from exc
        if b"not-stored" in raw:
            raise SystemExit("encoded choices kept a secret")
        coded = json.loads(raw)
        if coded.get("password") is not True or coded.get("device") != "":
            raise SystemExit(f"encoded choices {coded}")
        window.applyLive(json.dumps({
            "warnings": [],
            "blocked": False,
            "disks": [{
                "name": "Samsung 990",
                "size": "2 TB",
                "windows": False,
                "occupied": False,
                "device": "",
                "bytes": 2000000000000,
                "games": False,
            }],
        }))
        window.setProperty("gamesOpen", False)
        window.setProperty("page", 4)
        pump(50)
        if quick.findChild(QQuickItem, "gamesPartition") is not None:
            raise SystemExit("the /games checkbox showed on the only drive")
        if not _shown(quick.findChild(QQuickItem, "chooseGamesButton")):
            raise SystemExit("the /games button was missing on the only drive")
        one_slider = quick.findChild(QQuickItem, "osGbBox")
        if one_slider is not None and _shown(one_slider):
            raise SystemExit("the slider showed before Set up /games on the only drive")
        if not QMetaObject.invokeMethod(window, "openGamesSection"):
            raise SystemExit("openGamesSection did not run for the only drive")
        pump(50)
        if window.property("gamesMode") != "split" or window.property("gamesOpen") is not True:
            raise SystemExit(f"the only drive did not open the slider: {window.property('gamesMode')}")
        if one_slider is None or not _shown(one_slider):
            raise SystemExit("the slider stayed hidden on the only drive")
        os_gb = int(window.property("osGb") or 0)
        games_gb = int(window.property("gamesGb") or 0)
        if os_gb < 64 or games_gb < 32:
            raise SystemExit(f"split sizes {os_gb} {games_gb}")
        if not QMetaObject.invokeMethod(window, "setOsGb", Qt.ConnectionType.DirectConnection, Q_ARG("QVariant", 200)):
            raise SystemExit("setOsGb did not run")
        pump(50)
        if int(window.property("osGb") or 0) != 200:
            raise SystemExit(f"the WASD size did not move: {window.property('osGb')}")
        if int(window.property("gamesGb") or 0) >= games_gb:
            raise SystemExit(f"the games size did not shrink: {window.property('gamesGb')}")
        if not QMetaObject.invokeMethod(window, "encodeChoices"):
            raise SystemExit("encodeChoices did not run for games")
        pump(50)
        games_raw = base64.b64decode(window.property("encodedChoices") or "", validate=True)
        games_data = json.loads(games_raw)
        if games_data.get("games", {}).get("mode") != "split" or games_data["games"].get("osGb") != 200:
            raise SystemExit(f"games choice {games_data.get('games')}")
        if b"passphrase" in games_raw or b"wpakey" in games_raw:
            raise SystemExit("the games choice kept a secret")
        erase_label = quick.findChild(QQuickItem, "eraseButtonLabel")
        whole_drive = quick.findChild(QQuickItem, "chooseGamesLabel")
        if erase_label is None or not _shown(erase_label) or erase_label.property("text") != "Erase the disk and install with the games partition":
            actual = None if erase_label is None else erase_label.property("text")
            raise SystemExit(f"the games install button was {actual}")
        if whole_drive is None or not _shown(whole_drive) or whole_drive.property("text") != "I changed my mind. Use the whole drive.":
            actual = None if whole_drive is None else whole_drive.property("text")
            raise SystemExit(f"the whole-drive button was {actual}")
        grab(shot / "disk-one.png")
        if not QMetaObject.invokeMethod(window, "openGamesSection"):
            raise SystemExit("the second Set up /games did not run")
        pump(50)
        if window.property("gamesMode") != "split" or window.property("gamesOpen") is not True:
            raise SystemExit("Set up /games cleared the games partition")
        if not QMetaObject.invokeMethod(window, "useWholeDrive"):
            raise SystemExit("useWholeDrive did not run")
        pump(50)
        if window.property("gamesMode") != "off" or window.property("gamesOpen") is not False:
            raise SystemExit("the whole-drive button did not clear games")
        if window.property("eraseLabel") != "Erase the selected disk and install WASD":
            raise SystemExit(f"the whole-disk button was {window.property('eraseLabel')}")
        if not _shown(erase_label) or erase_label.property("text") != "Erase the selected disk and install WASD":
            raise SystemExit(f"the whole-disk button text was {erase_label.property('text')}")
        if whole_drive.property("text") != "Set up /games":
            raise SystemExit(f"Set up /games did not return: {whole_drive.property('text')}")
        window.applyLive(json.dumps({"warnings": [], "blocked": False, "disks": parse_disks(FIXTURE)}))
        pump(50)
        snap = json.loads(window.diskSnapshot())
        if snap["index"] != 2 or snap["rows"][0]["windows"] is not True:
            raise SystemExit(f"live disk apply failed {snap}")
        if snap["rows"][0]["device"] != "nvme0n1" or snap["rows"][2]["device"] != "sda":
            raise SystemExit(f"live disk devices were not kept {snap}")
        if snap["rows"][0].get("games") or snap["rows"][1].get("games"):
            raise SystemExit(f"a fixture disk was marked for games {snap}")
        window.setProperty("page", 2)
        window.setProperty("appsOpen", "general")
        pump(50)
        if quick.findChild(QQuickItem, "selectAllApps") is None:
            raise SystemExit("Select All is missing from Apps")
        if quick.findChild(QQuickItem, "selectNoneApps") is None:
            raise SystemExit("Select None is missing from Apps")
        if not QMetaObject.invokeMethod(window, "selectNoneApps"):
            raise SystemExit("selectNoneApps did not run")
        pump(50)
        if window.property("appSummary") != "0 selected":
            raise SystemExit(f"apps were not cleared: {window.property('appSummary')}")
        grab(shot / "apps-none.png")
        if not QMetaObject.invokeMethod(window, "selectAllApps"):
            raise SystemExit("selectAllApps did not run")
        pump(50)
        if window.property("appSummary") != "23 selected":
            raise SystemExit(f"apps were not all selected: {window.property('appSummary')}")
        if window.property("launcherSummary") != "None selected":
            raise SystemExit(f"apps selected a launcher: {window.property('launcherSummary')}")
        grab(shot / "apps-all.png")
        window.setProperty("appsOpen", "launchers")
        pump(50)
        if quick.findChild(QQuickItem, "selectAllLaunchers") is None:
            raise SystemExit("Select All is missing from Launchers")
        if quick.findChild(QQuickItem, "selectNoneLaunchers") is None:
            raise SystemExit("Select None is missing from Launchers")
        if not QMetaObject.invokeMethod(window, "selectNoneLaunchers"):
            raise SystemExit("selectNoneLaunchers did not run")
        pump(50)
        if not QMetaObject.invokeMethod(window, "toggleLauncher", Q_ARG("QVariant", "Battle.net")):
            raise SystemExit("toggleLauncher did not run")
        pump(50)
        if window.property("battleNetWarn") is not True:
            raise SystemExit("Battle.net did not open the warning")
        warn_body = quick.findChild(QQuickItem, "battleNetWarnBody")
        expected_warn = "Do not log in at the end of the Battle.net installation. Just close the window."
        if warn_body is None or warn_body.property("text") != expected_warn:
            raise SystemExit(f"Battle.net warning was {None if warn_body is None else warn_body.property('text')}")
        if quick.findChild(QQuickItem, "battleNetWarnOk") is None:
            raise SystemExit("the Battle.net warning has no OK")
        if not QMetaObject.invokeMethod(window, "dismissBattleNetWarn"):
            raise SystemExit("the Battle.net warning did not close")
        pump(50)
        if window.property("battleNetWarn") is not False:
            raise SystemExit("the Battle.net warning stayed open")
        if "Battle.net" not in (window.property("launcherSummary") or ""):
            raise SystemExit("closing the warning unchecked Battle.net")
        if not QMetaObject.invokeMethod(window, "toggleLauncher", Q_ARG("QVariant", "Battle.net")):
            raise SystemExit("toggleLauncher did not turn Battle.net off")
        pump(50)
        if window.property("battleNetWarn") is not False:
            raise SystemExit("turning Battle.net off opened the warning")
        if not QMetaObject.invokeMethod(window, "toggleLauncher", Q_ARG("QVariant", "EA App")):
            raise SystemExit("toggleLauncher did not run for EA App")
        pump(50)
        if window.property("battleNetWarn") is not False:
            raise SystemExit("EA App opened the Battle.net warning")
        if not QMetaObject.invokeMethod(window, "selectAllLaunchers"):
            raise SystemExit("selectAllLaunchers did not run")
        pump(50)
        if window.property("battleNetWarn") is not True:
            raise SystemExit("Select All did not warn about Battle.net")
        if not QMetaObject.invokeMethod(window, "dismissBattleNetWarn"):
            raise SystemExit("the Battle.net warning did not close")
        pump(50)
        launcher_summary = window.property("launcherSummary") or ""
        if "Battle.net" not in launcher_summary or "Rockstar Launcher" not in launcher_summary:
            raise SystemExit(f"launchers were not all selected: {launcher_summary}")
        if window.property("appSummary") != "23 selected":
            raise SystemExit("selecting launchers changed the apps")
        grab(shot / "launchers-all.png")
        if not QMetaObject.invokeMethod(window, "selectNoneLaunchers"):
            raise SystemExit("selectNoneLaunchers did not run")
        pump(50)
        if window.property("launcherSummary") != "None selected":
            raise SystemExit(f"launchers were not cleared: {window.property('launcherSummary')}")
        if window.property("appSummary") != "23 selected":
            raise SystemExit("clearing launchers changed the apps")
        grab(shot / "launchers-none.png")
        window.setProperty("appsOpen", "agents")
        pump(50)
        if quick.findChild(QQuickItem, "selectAllAgents") is None:
            raise SystemExit("Select All is missing from Agents")
        if quick.findChild(QQuickItem, "selectNoneAgents") is None:
            raise SystemExit("Select None is missing from Agents")
        if not QMetaObject.invokeMethod(window, "selectNoneAgents"):
            raise SystemExit("selectNoneAgents did not run")
        pump(50)
        if window.property("agentSummary") != "None selected":
            raise SystemExit(f"agents were not cleared: {window.property('agentSummary')}")
        grab(shot / "agents-none.png")
        if not QMetaObject.invokeMethod(window, "selectAllAgents"):
            raise SystemExit("selectAllAgents did not run")
        pump(50)
        agent_summary = window.property("agentSummary") or ""
        if "Grok Build" not in agent_summary or agent_summary == "None selected":
            raise SystemExit(f"agents were not all selected: {agent_summary}")
        grab(shot / "agents-all.png")
        window.setProperty("page", 3)
        window.setProperty("networkConnected", False)
        window.setProperty("networkOpen", True)
        pump(50)
        if window.property("networkStatus") != "No connection detected, expand to configure.":
            raise SystemExit(f"offline status was {window.property('networkStatus')}")
        grab(shot / "system-network.png")
        system_scroll = quick.findChild(QQuickItem, "systemScroll")
        if system_scroll is None:
            raise SystemExit("the network page does not scroll")
        window.setProperty("tcpMode", "manual")
        pump(50)
        system_height = system_scroll.property("height") or 0
        system_content = system_scroll.property("contentHeight") or 0
        system_scroll.setProperty("contentY", max(0, system_content - system_height))
        grab(shot / "system-network-tcp.png")
        window.setProperty("tcpMode", "auto")
        system_scroll.setProperty("contentY", 0)
        window.setProperty("wifiSsid", "Home")
        pump(50)
        if window.property("wifiNote") != "Saved. The first boot asks for the passphrase.":
            raise SystemExit(f"saved network note was {window.property('wifiNote')}")
        if not QMetaObject.invokeMethod(window, "chooseWifi", Q_ARG("QVariant", "Home")):
            raise SystemExit("chooseWifi did not run")
        pump(50)
        if window.property("wifiSsid"):
            raise SystemExit("choosing the saved network again did not clear it")
        if not QMetaObject.invokeMethod(window, "chooseWifi", Q_ARG("QVariant", "Home")):
            raise SystemExit("chooseWifi did not save the network")
        pump(50)
        if window.property("wifiSsid") != "Home":
            raise SystemExit(f"the network was not saved: {window.property('wifiSsid')}")
        if not QMetaObject.invokeMethod(window, "encodeChoices"):
            raise SystemExit("encodeChoices did not run after the network")
        pump(50)
        import base64 as network_base64
        network_raw = network_base64.b64decode(window.property("encodedChoices") or "", validate=True)
        if b"not-stored-secret" in network_raw or b"passphrase" in network_raw or b"wpakey" in network_raw:
            raise SystemExit("the passphrase was written into the choices")
        saved_wifi = json.loads(network_raw).get("wifi") or {}
        if saved_wifi.get("ssid") != "Home" or saved_wifi.get("security") != "WPA2" or saved_wifi.get("hidden") is not False:
            raise SystemExit(f"saved wifi was {saved_wifi}")
        window.setProperty("wifiSsid", "Cabin")
        if not QMetaObject.invokeMethod(window, "encodeChoices"):
            raise SystemExit("encodeChoices did not run for a typed network")
        pump(50)
        typed = json.loads(network_base64.b64decode(window.property("encodedChoices") or "", validate=True))
        typed_wifi = typed.get("wifi") or {}
        if typed_wifi.get("ssid") != "Cabin" or typed_wifi.get("hidden") is not True or typed_wifi.get("security") != "":
            raise SystemExit(f"a typed network was {typed_wifi}")
        window.setProperty("wifiSsid", "H" * 40)
        pump(50)
        if window.property("wifiNote") != "That network name cannot be used.":
            raise SystemExit(f"a long network name was {window.property('wifiNote')}")
        if not QMetaObject.invokeMethod(window, "encodeChoices"):
            raise SystemExit("encodeChoices did not run for a long network name")
        pump(50)
        refused = json.loads(network_base64.b64decode(window.property("encodedChoices") or "", validate=True))
        if "wifi" in refused:
            raise SystemExit(f"a long network name was saved: {refused.get('wifi')}")
        raw_devices = window.property("tcpDevices")
        if hasattr(raw_devices, "toVariant"):
            raw_devices = raw_devices.toVariant()
        found = {}
        for row in raw_devices or []:
            found[row["device"]] = row["kind"]
        if found.get("wlp3s0") != "wifi" or found.get("enp4s0") != "ethernet":
            raise SystemExit(f"adapters were {found}")
        window.setProperty("tcpMode", "manual")
        window.setProperty("tcpAddress", "192.168.1.20")
        window.setProperty("tcpNetmask", "255.255.255.0")
        window.setProperty("tcpGateway", "192.168.1.1")
        window.setProperty("tcpDns", "1.1.1.1")
        pump(50)
        if "not saved" not in (window.property("tcpNote") or ""):
            raise SystemExit(f"manual address without an adapter was saved: {window.property('tcpNote')}")
        if not QMetaObject.invokeMethod(window, "encodeChoices"):
            raise SystemExit("encodeChoices did not run for an unfinished address")
        pump(50)
        unfinished = json.loads(network_base64.b64decode(window.property("encodedChoices") or "", validate=True))
        if "tcp" in unfinished:
            raise SystemExit(f"an unfinished address was saved: {unfinished.get('tcp')}")
        if not QMetaObject.invokeMethod(window, "chooseAdapter", Q_ARG("QVariant", "enp4s0")):
            raise SystemExit("chooseAdapter did not run")
        pump(50)
        if window.property("tcpInterface") != "enp4s0" or window.property("tcpKind") != "ethernet":
            raise SystemExit(f"adapter was {window.property('tcpInterface')} {window.property('tcpKind')}")
        if not str(window.property("tcpNote") or "").startswith("Saved for the installed system."):
            raise SystemExit(f"saved address note was {window.property('tcpNote')}")
        if not QMetaObject.invokeMethod(window, "applyTcp"):
            raise SystemExit("applyTcp did not run")
        pump(50)
        if "This computer was not changed." not in (window.property("networkLine") or ""):
            raise SystemExit(f"preview address changed the computer: {window.property('networkLine')}")
        if not QMetaObject.invokeMethod(window, "encodeChoices"):
            raise SystemExit("encodeChoices did not run for a manual address")
        pump(50)
        saved_tcp = json.loads(network_base64.b64decode(window.property("encodedChoices") or "", validate=True)).get("tcp") or {}
        if (
            saved_tcp.get("mode") != "manual"
            or saved_tcp.get("interface") != "enp4s0"
            or saved_tcp.get("kind") != "ethernet"
            or saved_tcp.get("address") != "192.168.1.20"
            or saved_tcp.get("netmask") != "255.255.255.0"
            or saved_tcp.get("gateway") != "192.168.1.1"
            or saved_tcp.get("dns") != "1.1.1.1"
        ):
            raise SystemExit(f"saved tcp was {saved_tcp}")
        if not QMetaObject.invokeMethod(window, "chooseAdapter", Q_ARG("QVariant", "enp4s0")):
            raise SystemExit("chooseAdapter did not clear the adapter")
        pump(50)
        if window.property("tcpInterface"):
            raise SystemExit("choosing the adapter again did not clear it")
        if not QMetaObject.invokeMethod(window, "chooseAdapter", Q_ARG("QVariant", "enp4s0")):
            raise SystemExit("chooseAdapter did not select the adapter again")
        pump(50)
        window.setProperty("tcpAddress", "192.168.1.999")
        pump(50)
        if not QMetaObject.invokeMethod(window, "encodeChoices"):
            raise SystemExit("encodeChoices did not run for a bad address")
        pump(50)
        bad_address = json.loads(network_base64.b64decode(window.property("encodedChoices") or "", validate=True))
        if "tcp" in bad_address:
            raise SystemExit(f"a bad address was saved: {bad_address.get('tcp')}")
        window.setProperty("tcpAddress", "192.168.1.20")
        if not QMetaObject.invokeMethod(window, "chooseAdapter", Q_ARG("QVariant", "wlp3s0")):
            raise SystemExit("chooseAdapter did not select Wi-Fi")
        pump(50)
        if window.property("tcpKind") != "wifi":
            raise SystemExit(f"wifi adapter kind was {window.property('tcpKind')}")
        if "Choose a Wi-Fi network" not in (window.property("tcpNote") or ""):
            raise SystemExit(f"wifi address without a network was {window.property('tcpNote')}")
        window.setProperty("wifiSsid", "Home")
        pump(50)
        if "when that network connects" not in (window.property("tcpNote") or ""):
            raise SystemExit(f"wifi address note was {window.property('tcpNote')}")
        if not QMetaObject.invokeMethod(window, "encodeChoices"):
            raise SystemExit("encodeChoices did not run for a wifi address")
        pump(50)
        wifi_tcp = json.loads(network_base64.b64decode(window.property("encodedChoices") or "", validate=True)).get("tcp") or {}
        if wifi_tcp.get("interface") != "wlp3s0" or wifi_tcp.get("kind") != "wifi":
            raise SystemExit(f"wifi tcp was {wifi_tcp}")
        if b"passphrase" in network_base64.b64decode(window.property("encodedChoices") or "", validate=True):
            raise SystemExit("the passphrase was written beside the address")
        window.setProperty("tcpMode", "auto")
        pump(50)
        if window.property("tcpNote"):
            raise SystemExit(f"automatic still showed an address: {window.property('tcpNote')}")
        if not QMetaObject.invokeMethod(window, "encodeChoices"):
            raise SystemExit("encodeChoices did not run for automatic")
        pump(50)
        automatic = json.loads(network_base64.b64decode(window.property("encodedChoices") or "", validate=True))
        if "tcp" in automatic:
            raise SystemExit(f"automatic saved an address: {automatic.get('tcp')}")
        window.setProperty("wifiSsid", "")
        window.setProperty("page", 0)
        window.setProperty("avatar", "")
        pump(50)
        if window.property("avatar") != "":
            raise SystemExit("the account picture stayed selected")
        grab(shot / "user-no-avatar.png")
        window.setProperty("avatar", "knight.jpg")
        if window.property("installStage"):
            raise SystemExit(f"install status started early: {window.property('installStage')}")
        if not QMetaObject.invokeMethod(window, "noteInstall", Q_ARG("QVariant", "Copying WASD.")):
            raise SystemExit("noteInstall did not run")
        pump(50)
        if window.property("installStage") != "copy" or window.installLine() != "Copying WASD.":
            raise SystemExit(f"copy status was {window.property('installStage')} {window.installLine()}")
        if window.stageSeen("account"):
            raise SystemExit("the account step was marked during the copy")
        if window.property("erasing") is not True:
            raise SystemExit("the steps stayed clickable during the copy")
        held_page = int(window.property("page") or 0)
        if not QMetaObject.invokeMethod(window, "showPage", Q_ARG("QVariant", 0)):
            raise SystemExit("showPage did not run during the copy")
        pump(50)
        if int(window.property("page") or 0) != held_page:
            raise SystemExit("a step click left the status")
        if not QMetaObject.invokeMethod(window, "noteInstall", Q_ARG("QVariant", "Preparing the disk.")):
            raise SystemExit("noteInstall did not run for the earlier stage")
        pump(50)
        if window.property("installStage") != "copy":
            raise SystemExit("the status moved backward")
        if not QMetaObject.invokeMethod(window, "restartNow"):
            raise SystemExit("restartNow did not run during the copy")
        pump(50)
        if window.property("restartAsked") is True:
            raise SystemExit("Enter restarted before the copy finished")
        spinner = quick.findChild(QQuickItem, "copySpinner")
        bar = quick.findChild(QQuickItem, "copyBar")
        track = quick.findChild(QQuickItem, "copyTrack")
        fill = quick.findChild(QQuickItem, "copyFill")
        percent = quick.findChild(QQuickItem, "copyPercent")
        if spinner is None or not _shown(spinner):
            raise SystemExit("the copy spinner is missing")
        if bar is None or track is None or fill is None or percent is None or not _shown(bar):
            raise SystemExit("the copy bar is missing")
        if int(window.property("copyPercent")) != -1 or percent.property("text") not in ("", None):
            raise SystemExit(f"the copy invented a percent: {window.property('copyPercent')} {percent.property('text')}")
        if float(fill.property("width") or 0) > 1:
            raise SystemExit(f"the empty bar was already filled: {fill.property('width')}")
        if not QMetaObject.invokeMethod(window, "noteInstall", Q_ARG("QVariant", "Copying WASD. 0")):
            raise SystemExit("noteInstall did not run for 0")
        pump(50)
        if window.property("installStage") != "copy" or window.installLine() != "Copying WASD.":
            raise SystemExit(f"zero percent left the copy: {window.property('installStage')} {window.installLine()}")
        if int(window.property("copyPercent")) != 0 or percent.property("text") != "0%":
            raise SystemExit(f"zero percent was {window.property('copyPercent')} {percent.property('text')}")
        if not QMetaObject.invokeMethod(window, "noteInstall", Q_ARG("QVariant", "Copying WASD. 42")):
            raise SystemExit("noteInstall did not run for the percent")
        pump(50)
        if window.installLine() != "Copying WASD." or int(window.property("copyPercent")) != 42 or percent.property("text") != "42%":
            raise SystemExit(f"the percent was {window.property('copyPercent')} {percent.property('text')} {window.installLine()}")
        track_w = float(track.property("width") or 0)
        fill_w = float(fill.property("width") or 0)
        if track_w < 40 or abs(fill_w - track_w * 0.42) > 4:
            raise SystemExit(f"the bar was {fill_w} of {track_w}")
        if not QMetaObject.invokeMethod(window, "noteInstall", Q_ARG("QVariant", "Copying WASD. 7")):
            raise SystemExit("noteInstall did not run for a lower percent")
        pump(50)
        if int(window.property("copyPercent")) != 42:
            raise SystemExit(f"the percent moved backward to {window.property('copyPercent')}")
        if not QMetaObject.invokeMethod(window, "noteInstall", Q_ARG("QVariant", "Copying WASD. 101")):
            raise SystemExit("noteInstall did not run for a bad percent")
        pump(50)
        if int(window.property("copyPercent")) != 42 or window.installLine() != "Copying WASD.":
            raise SystemExit(f"a bad percent was accepted: {window.property('copyPercent')} {window.installLine()}")
        grab(shot / "install-status.png")
        for sentence, stage in (
            ("Setting up your account.", "account"),
            ("Installing the bootloader.", "boot"),
            ("Click Restart to continue.", "done"),
        ):
            if not QMetaObject.invokeMethod(window, "noteInstall", Q_ARG("QVariant", sentence)):
                raise SystemExit(f"noteInstall did not run for {sentence}")
            pump(50)
            if window.property("installStage") != stage or window.installLine() != sentence:
                raise SystemExit(f"status {sentence} was {window.property('installStage')} {window.installLine()}")
            if not window.stageSeen(stage):
                raise SystemExit(f"the {stage} step was not recorded")
            if stage == "done" and _shown(spinner):
                raise SystemExit("the spinner stayed after the install")
            if stage != "done" and not _shown(spinner):
                raise SystemExit("the spinner stopped before the install finished")
            if _shown(bar):
                raise SystemExit("the copy bar stayed after the copy")
            if stage == "account":
                if not QMetaObject.invokeMethod(window, "noteInstall", Q_ARG("QVariant", "Copying WASD. 90")):
                    raise SystemExit("noteInstall did not run after the copy")
                pump(50)
                if window.property("installStage") != "account" or int(window.property("copyPercent")) != 42:
                    raise SystemExit(f"a late percent moved the copy: {window.property('installStage')} {window.property('copyPercent')}")
        if window.property("erasing") is not True:
            raise SystemExit("the steps unlocked before restart")
        if not QMetaObject.invokeMethod(window, "showPage", Q_ARG("QVariant", 4)):
            raise SystemExit("showPage did not run on the last line")
        pump(50)
        if int(window.property("page") or 0) != held_page:
            raise SystemExit("a step click left the last line")
        grab(shot / "install-done.png")
        restart = quick.findChild(QQuickItem, "restartButtonLabel")
        if restart is None or not _shown(restart) or restart.property("text") != "Restart":
            raise SystemExit("the Restart button is missing from the last line")
        done_note = quick.findChild(QQuickItem, "restartNote")
        if done_note is not None and _shown(done_note):
            raise SystemExit("the last line repeated the restart note")
        if "USB" in (window.installLine() or ""):
            raise SystemExit("the last line told them to remove the USB")
        if not QMetaObject.invokeMethod(window, "restartNow"):
            raise SystemExit("restartNow did not run on the last line")
        pump(50)
        if window.property("restartAsked") is not True or window.property("restartSent") is not True:
            raise SystemExit("Restart did not restart")
        if window.installLine() != "Click Restart to continue.":
            raise SystemExit(f"the last line changed: {window.installLine()}")
        if "USB" in (window.installLine() or ""):
            raise SystemExit("the last line told them to remove the USB")
        if _shown(spinner):
            raise SystemExit("the spinner came back after restart")
        if done_note is not None and _shown(done_note):
            raise SystemExit("the last line repeated the restart note")
        if window.property("liveSession") is True:
            raise SystemExit("the check restarted a live session")
        if not QMetaObject.invokeMethod(window, "failInstall", Q_ARG("QVariant", "Nothing was erased.")):
            raise SystemExit("failInstall did not run after the last line")
        pump(50)
        if window.property("installStage") != "done":
            raise SystemExit("a failure replaced the last line")
        window.setProperty("installStage", "")
        window.setProperty("erasing", False)
        window.setProperty("restartAsked", False)
        window.setProperty("restartSent", False)
        if not QMetaObject.invokeMethod(window, "failInstall", Q_ARG("QVariant", 'Traceback (most recent call last):\n  File "erase.py"')):
            raise SystemExit("failInstall did not run")
        pump(50)
        if window.property("installStage") != "failed" or window.installLine() != "Nothing was erased.":
            raise SystemExit(f"failure status was {window.property('installStage')} {window.installLine()}")
        early_restart = quick.findChild(QQuickItem, "restartButtonLabel")
        if early_restart is not None and _shown(early_restart):
            raise SystemExit("Restart was offered before the copy")
        if not QMetaObject.invokeMethod(window, "restartNow"):
            raise SystemExit("restartNow did not run before the copy")
        pump(50)
        if window.property("restartAsked") is True:
            raise SystemExit("Enter restarted after a failure")
        if not QMetaObject.invokeMethod(
            window,
            "failInstall",
            Q_ARG("QVariant", "The disk was erased. The install did not finish."),
        ):
            raise SystemExit("failInstall did not run for a wiped disk")
        pump(50)
        if window.property("installStage") != "failed" or window.installLine() != "The disk was erased. The install did not finish.":
            raise SystemExit(f"wiped status was {window.property('installStage')} {window.installLine()}")
        if window.property("restartAsked") is True:
            raise SystemExit("Enter restarted after the disk was erased")
        wiped_restart = quick.findChild(QQuickItem, "restartButtonLabel")
        if wiped_restart is not None and _shown(wiped_restart):
            raise SystemExit("Restart was offered when the install did not finish")
        grab(shot / "install-failed.png")
        window.setProperty("restartAsked", False)
        window.setProperty("restartSent", False)
        if not QMetaObject.invokeMethod(
            window,
            "failInstall",
            Q_ARG("QVariant", "WASD was copied. Later updates were not pointed at WASD."),
        ):
            raise SystemExit("failInstall did not run after the copy")
        pump(50)
        if window.installLine() != "WASD was copied. Later updates were not pointed at WASD.":
            raise SystemExit(f"update status was {window.installLine()}")
        copied_note = quick.findChild(QQuickItem, "restartNote")
        copied_restart = quick.findChild(QQuickItem, "restartButtonLabel")
        if copied_note is None or not _shown(copied_note) or copied_note.property("text") != "Click Restart to continue.":
            raise SystemExit("the copied failure did not say to click Restart")
        if "USB" in (copied_note.property("text") or ""):
            raise SystemExit("the copied failure told them to remove the USB")
        if copied_restart is None or not _shown(copied_restart):
            raise SystemExit("Restart was missing after the copy")
        grab(shot / "install-copied.png")
        if not QMetaObject.invokeMethod(window, "restartNow"):
            raise SystemExit("restartNow did not run after the copy")
        pump(50)
        if window.property("restartAsked") is not True or window.property("restartSent") is not True:
            raise SystemExit("Restart did nothing after the copy")
        if copied_note.property("text") != "Click Restart to continue.":
            raise SystemExit(f"the copied restart line was {copied_note.property('text')}")
        if "USB" in (copied_note.property("text") or ""):
            raise SystemExit("the copied failure told them to remove the USB")
        if window.property("liveSession") is True:
            raise SystemExit("the check restarted a live session")
        if not QMetaObject.invokeMethod(window, "showPage", Q_ARG("QVariant", 4)):
            raise SystemExit("showPage did not leave the failure")
        pump(50)
        if window.property("installStage") or int(window.property("page") or 0) != 4:
            raise SystemExit(f"the failure stayed up: {window.property('installStage')} page {window.property('page')}")
        print(f"saved {save_path}")
        return

    raise SystemExit(app.exec())


def open_complete(shot_dir=None):
    if shot_dir:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        os.environ.setdefault("QT_QUICK_BACKEND", "software")
        os.environ.setdefault("QSG_RHI_BACKEND", "sw")
    from PySide6.QtCore import QEventLoop, QMetaObject, QTimer, QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuick import QQuickItem, QQuickWindow
    import shiboken6

    app = QGuiApplication(sys.argv)
    engine = QQmlApplicationEngine()
    engine.warnings.connect(lambda warning: print("\n".join(item.toString() for item in warning) if isinstance(warning, list) else warning, file=sys.stderr))
    context = engine.rootContext()
    context.setContextProperty("WasdRepo", str(REPO))
    context.setContextProperty("WasdHold", shot_dir is not None)
    context.setContextProperty("WasdPreview", shot_dir is not None)
    context.setContextProperty("WasdWantPassword", shot_dir is not None)
    context.setContextProperty("WasdWantWifi", shot_dir is not None)
    context.setContextProperty("WasdWifiSsid", "Home" if shot_dir else "")
    context.setContextProperty("WasdWifiSecurity", "WPA2" if shot_dir else "")
    engine.load(QUrl.fromLocalFile(str(HERE / "Complete.qml")))
    if not engine.rootObjects():
        raise SystemExit("Completing the install failed to open")
    window = engine.rootObjects()[0]
    quick = shiboken6.wrapInstance(shiboken6.getCppPointer(window)[0], QQuickWindow)
    window.show()

    def pump(ms):
        loop = QEventLoop()
        QTimer.singleShot(ms, loop.quit)
        loop.exec()

    def grab(path):
        pump(250)
        image = quick.grabWindow()
        if image.isNull():
            raise SystemExit(f"could not capture {path}")
        if not image.save(str(path)):
            raise SystemExit(f"could not write {path}")

    pump(400)
    if not shot_dir:
        raise SystemExit(app.exec())

    shot = Path(shot_dir)
    shot.mkdir(parents=True, exist_ok=True)
    if window.property("phase") != "password":
        raise SystemExit(f"password window did not open: {window.property('phase')}")
    grab(shot / "password.png")
    window.setProperty("passwordDraft", "alpha")
    window.setProperty("passwordAgainDraft", "beta")
    if not QMetaObject.invokeMethod(window, "confirmPassword"):
        raise SystemExit("confirmPassword did not run")
    pump(50)
    if window.property("phase") != "password":
        raise SystemExit("a mismatched password was accepted")
    if window.property("passwordError") != "Type the same password in both boxes.":
        raise SystemExit(f"mismatch text was {window.property('passwordError')}")
    grab(shot / "password-error.png")
    secret = "not-stored-secret"
    window.setProperty("passwordDraft", secret)
    window.setProperty("passwordAgainDraft", secret)
    if not QMetaObject.invokeMethod(window, "confirmPassword"):
        raise SystemExit("confirmPassword did not accept a match")
    pump(50)
    if window.property("phase") != "wifi":
        raise SystemExit("a matching password did not ask for the wifi passphrase")
    if window.property("passwordDraft") or window.property("passwordAgainDraft"):
        raise SystemExit("the password stayed on the window")
    if window.property("wifiName") != "Home":
        raise SystemExit(f"wifi name was {window.property('wifiName')}")
    if window.property("wifiLead") != "Connect to Home.":
        raise SystemExit(f"wifi lead was {window.property('wifiLead')}")
    grab(shot / "wifi.png")
    if not QMetaObject.invokeMethod(window, "cancelWifi"):
        raise SystemExit("cancelWifi did not run")
    pump(50)
    if not window.property("wifiWarn"):
        raise SystemExit("cancel did not open the warning")
    if window.property("wifiWarnBody") != "If you are not connected, you will not be able to install the applications you selected during installation.":
        raise SystemExit(f"wifi warning was {window.property('wifiWarnBody')}")
    grab(shot / "wifi-cancel.png")
    if not QMetaObject.invokeMethod(window, "dismissWifiWarn"):
        raise SystemExit("dismissWifiWarn did not run")
    pump(50)
    if window.property("wifiWarn") or window.property("phase") != "wifi":
        raise SystemExit("go back did not return to the passphrase")
    if not QMetaObject.invokeMethod(window, "confirmWifi"):
        raise SystemExit("confirmWifi did not run")
    pump(50)
    if window.property("phase") != "wifi":
        raise SystemExit("an empty passphrase was accepted")
    if window.property("wifiError") != "Type the passphrase.":
        raise SystemExit(f"empty passphrase text was {window.property('wifiError')}")
    window.setProperty("wifiDraft", "short")
    if not QMetaObject.invokeMethod(window, "confirmWifi"):
        raise SystemExit("confirmWifi did not run for a short passphrase")
    pump(50)
    if window.property("phase") != "wifi":
        raise SystemExit("a short passphrase was accepted")
    if window.property("wifiError") != "A passphrase is 8 to 63 characters, or empty for an open network.":
        raise SystemExit(f"short passphrase text was {window.property('wifiError')}")
    window.setProperty("wifiDraft", secret)
    if not QMetaObject.invokeMethod(window, "confirmWifi"):
        raise SystemExit("confirmWifi did not accept a passphrase")
    pump(50)
    if window.property("phase") != "work":
        raise SystemExit("a passphrase did not continue")
    if window.property("wifiDraft"):
        raise SystemExit("the passphrase stayed on the window")
    window.setProperty("phase", "wifi")
    window.setProperty("wantWifi", True)
    if not QMetaObject.invokeMethod(window, "continueWithoutWifi"):
        raise SystemExit("continueWithoutWifi did not run")
    pump(50)
    if window.property("phase") != "work" or window.property("wantWifi") or window.property("wifiWarn"):
        raise SystemExit("continue without wifi did not leave the passphrase")
    if window.property("workNote"):
        raise SystemExit(f"work note was {window.property('workNote')}")
    for path in shot.iterdir():
        if secret.encode() in path.read_bytes():
            raise SystemExit(f"the password was written to {path}")
    names = ["setting", "installing", "finishing"]
    for index, name in enumerate(names):
        window.setProperty("stepIndex", index)
        if name == "installing":
            window.setProperty("appOutput", "org.kde.kcalc\nInstalling…                         45%")
        else:
            window.setProperty("appOutput", "")
        pump(50)
        spinner = quick.findChild(QQuickItem, "workSpinner")
        term = quick.findChild(QQuickItem, "appTerm")
        term_text = quick.findChild(QQuickItem, "appTermText")
        if name == "installing":
            if spinner is not None and _shown(spinner):
                raise SystemExit("the spinner stayed on the install output")
            if term is None or not _shown(term):
                raise SystemExit("the install output was hidden")
            if term_text is None or "45%" not in (term_text.property("text") or ""):
                raise SystemExit(f"the install output was {None if term_text is None else term_text.property('text')}")
        else:
            if spinner is None or not _shown(spinner):
                raise SystemExit(f"the spinner was missing on {name}")
            if term is not None and _shown(term):
                raise SystemExit(f"the install output showed on {name}")
        grab(shot / f"{name}.png")
    window.setProperty("phase", "work")
    window.setProperty("failKind", "look")
    window.setProperty("failedApp", "The wallpaper did not change.")
    pump(50)
    if window.property("appsFailTitle") != "The wallpaper did not change.":
        raise SystemExit(f"look failure title was {window.property('appsFailTitle')}")
    if window.property("appsFailBody") != "Retry tries again.":
        raise SystemExit(f"look failure body was {window.property('appsFailBody')}")
    retry = quick.findChild(QQuickItem, "retryAppButton")
    carry_on = quick.findChild(QQuickItem, "continueAppButton")
    if retry is None or not _shown(retry):
        raise SystemExit("Retry was missing when the desktop was not set")
    if carry_on is not None and _shown(carry_on):
        raise SystemExit("Continue was offered when the desktop was not set")
    print(f"complete {shot}")


def open_look(save_path, shot_dir):
    if shot_dir:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        os.environ.setdefault("QT_QUICK_BACKEND", "software")
        os.environ.setdefault("QSG_RHI_BACKEND", "sw")
    from PySide6.QtCore import QEventLoop, QMetaObject, QObject, QTimer, QUrl, Slot
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuick import QQuickWindow
    import shiboken6

    class Bridge(QObject):
        def __init__(self, path):
            super().__init__()
            self.path = Path(path)

        @Slot(str)
        def applyLook(self, text):
            data = json.loads(text)
            for key in ("loading", "login", "wallpaper"):
                name = data.get(key) or ""
                if not re.fullmatch(r"[A-Za-z0-9._-]+", name):
                    raise ValueError(name)
            if "avatar" in data:
                avatar = data.get("avatar") or ""
                if avatar and (not re.fullmatch(r"[A-Za-z0-9._-]+", avatar) or avatar == "wasd-logo.png"):
                    raise ValueError(avatar)
            out = {
                "loading": data["loading"],
                "login": data["login"],
                "wallpaper": data["wallpaper"],
                "changed": False,
            }
            if "avatar" in data:
                out["avatar"] = data.get("avatar") or ""
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(out, indent=2) + "\n")
            os.chmod(self.path, 0o600)

    app = QGuiApplication(sys.argv)
    bridge = Bridge(Path(save_path))
    engine = QQmlApplicationEngine()
    engine.warnings.connect(lambda warning: print("\n".join(item.toString() for item in warning) if isinstance(warning, list) else warning, file=sys.stderr))
    context = engine.rootContext()
    context.setContextProperty("WasdRepo", str(REPO))
    context.setContextProperty("WasdFilesJson", json.dumps(file_lists()))
    context.setContextProperty("WasdBridge", bridge)
    engine.load(QUrl.fromLocalFile(str(HERE / "Look.qml")))
    if not engine.rootObjects():
        raise SystemExit("WASD Look failed to open")
    window = engine.rootObjects()[0]
    quick = shiboken6.wrapInstance(shiboken6.getCppPointer(window)[0], QQuickWindow)
    window.show()

    def pump(ms):
        loop = QEventLoop()
        QTimer.singleShot(ms, loop.quit)
        loop.exec()

    def grab(path):
        app.processEvents()
        pump(400)
        image = quick.grabWindow()
        if image.isNull() or image.width() < 100:
            raise SystemExit(f"could not capture {path}")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        if not image.save(str(path)):
            raise SystemExit(f"could not write {path}")

    pump(300)
    if not shot_dir:
        raise SystemExit(app.exec())

    shot = Path(shot_dir)
    if window.property("title") != "WASD Look":
        raise SystemExit("window title was not WASD Look")
    if not window.property("tool"):
        raise SystemExit("WASD Look did not open as the tool")
    grab(shot / "wasd-look.png")
    window.setProperty("lookOpen", "loading")
    grab(shot / "wasd-look-loading.png")
    if not QMetaObject.invokeMethod(window, "applyLook"):
        raise SystemExit("applyLook did not run")
    pump(100)
    data = json.loads(Path(save_path).read_text())
    if data.get("changed") is not False:
        raise SystemExit(f"preview changed the computer: {data}")
    if data.get("loading") != "stained-glass.jpg" or data.get("login") != "throne.jpg":
        raise SystemExit(f"unexpected look choices {data}")
    if data.get("wallpaper") != "stained-glass.jpg":
        raise SystemExit(f"unexpected wallpaper {data}")
    if "avatar" in data:
        raise SystemExit(f"an untouched account picture was saved: {data}")
    if window.property("avatarChoice") != "knight.jpg":
        raise SystemExit(f"look avatar did not start as knight.jpg: {window.property('avatarChoice')}")
    window.setProperty("lookOpen", "avatar")
    grab(shot / "wasd-look-avatar.png")
    window.setProperty("avatarTouched", True)
    window.setProperty("avatarChoice", "")
    grab(shot / "wasd-look-avatar-none.png")
    if not QMetaObject.invokeMethod(window, "applyLook"):
        raise SystemExit("applyLook did not keep an empty account picture")
    pump(100)
    cleared = json.loads(Path(save_path).read_text())
    if cleared.get("avatar") != "":
        raise SystemExit(f"empty account picture was not saved: {cleared}")
    if cleared.get("changed") is not False:
        raise SystemExit("clearing the account picture changed the computer")
    line = window.property("savedLine") or ""
    if "This computer was not changed." not in line:
        raise SystemExit(f"preview did not stay local: {line}")
    print(f"look {shot}")


def main():
    try:
        import PySide6  # noqa: F401
    except ImportError:
        venv_python = Path("/tmp/wasd-qt-venv/bin/python")
        if venv_python.exists() and Path(sys.executable) != venv_python.resolve():
            os.execv(venv_python, [str(venv_python), *sys.argv])
        raise SystemExit("This preview needs PySide6. The window itself is the QML in this folder.")

    parser = argparse.ArgumentParser(description="Open the Install WASD window")
    parser.add_argument("--shot", help="Write page pictures to this directory and exit")
    parser.add_argument("--save", help="Choice file written by the erase button")
    parser.add_argument("--live", action="store_true", help="Read this machine's disks and firmware")
    parser.add_argument("--check", action="store_true", help="Check the window without erasing anything")
    parser.add_argument("--complete", action="store_true", help="Open the first-boot window")
    parser.add_argument("--look", action="store_true", help="Open WASD Look")
    args = parser.parse_args()
    if args.complete:
        open_complete(args.shot)
        return
    if args.look:
        if args.live:
            raise SystemExit("WASD Look does not read this machine")
        save = args.save or "/tmp/wasd-look-choices.json"
        open_look(save, args.shot)
        return
    check_parser()
    if args.check:
        shot = args.shot or "/tmp/wasd-install-check"
        save = args.save or str(Path(shot) / "choices.json")
        qml_app(save, shot, live=False)
        found = search_flathub("vlc")
        if not any(row["id"] == "org.videolan.VLC" for row in found):
            print("flathub search skipped or missed VLC", file=sys.stderr)
        else:
            print("flathub search ok")
        return
    if args.shot or args.live:
        save = args.save or "/tmp/wasd-install-choices.json"
        qml_app(save, args.shot, live=args.live)
        return
    # Interactive open. Sample disks unless --live was passed above.
    os.environ.pop("QT_QPA_PLATFORM", None)
    save = args.save or "/tmp/wasd-install-choices.json"
    # qml_app forces offscreen. Interactive needs its own path.
    from PySide6.QtCore import QObject, QUrl, Signal, Slot
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine

    class Bridge(QObject):
        found = Signal(str)

        def __init__(self, path):
            super().__init__()
            self.path = Path(path)

        @Slot(str)
        def save(self, text):
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(text)
            os.chmod(self.path, 0o600)
            print(self.path)

        @Slot(str)
        def search(self, query):
            self.found.emit(json.dumps(search_flathub(query)))

    app = QGuiApplication(sys.argv)
    bridge = Bridge(save)
    engine = QQmlApplicationEngine()
    context = engine.rootContext()
    context.setContextProperty("WasdRepo", str(REPO))
    context.setContextProperty("WasdFilesJson", json.dumps(file_lists()))
    context.setContextProperty("WasdBridge", bridge)
    engine.load(QUrl.fromLocalFile(str(HERE / "Main.qml")))
    if not engine.rootObjects():
        raise SystemExit("Install WASD failed to open")
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
