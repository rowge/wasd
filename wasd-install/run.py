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


def qml_app(save_path, shot_dir, live):
    if shot_dir:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        os.environ.setdefault("QT_QUICK_BACKEND", "software")
        os.environ.setdefault("QSG_RHI_BACKEND", "sw")
    from PySide6.QtCore import QEventLoop, QMetaObject, QObject, QTimer, QUrl, Signal, Slot
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
        if window.property("hostname") != "wasd":
            raise SystemExit("hostname did not start as wasd")
        if window.property("userName") not in ("", None):
            raise SystemExit("username did not start empty")
        if window.property("setPassword"):
            raise SystemExit("password checkbox did not start off")
        window.setProperty("userName", "alex")
        pages = [
            ("user", {"page": 0}),
            ("look", {"page": 1, "lookOpen": ""}),
            ("look-open", {"page": 1, "lookOpen": "loading"}),
            ("apps", {"page": 2, "appsOpen": "apps"}),
            ("agents", {"page": 2, "appsOpen": "agents"}),
            ("system", {"page": 3, "networkOpen": False}),
            ("disk", {"page": 4}),
        ]
        for name, props in pages:
            for key, value in props.items():
                window.setProperty(key, value)
            grab(shot / f"{name}.png")
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
        if data.get("login") != "throne.jpg":
            raise SystemExit(f"login default was {data.get('login')}")
        if data.get("avatar") != "knight.jpg":
            raise SystemExit(f"avatar default was {data.get('avatar')}")
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
        window.applyLive(json.dumps({"warnings": [], "blocked": False, "disks": parse_disks(FIXTURE)}))
        pump(50)
        snap = json.loads(window.diskSnapshot())
        if snap["index"] != 2 or snap["rows"][0]["windows"] is not True:
            raise SystemExit(f"live disk apply failed {snap}")
        if snap["rows"][0]["device"] != "nvme0n1" or snap["rows"][2]["device"] != "sda":
            raise SystemExit(f"live disk devices were not kept {snap}")
        window.setProperty("page", 2)
        window.setProperty("appsOpen", "apps")
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
        if window.property("appSummary") != "24 selected":
            raise SystemExit(f"apps were not all selected: {window.property('appSummary')}")
        grab(shot / "apps-all.png")
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
        window.setProperty("wifiPass", "not-stored-secret")
        if not QMetaObject.invokeMethod(window, "connectWifi"):
            raise SystemExit("connectWifi did not run")
        pump(50)
        if window.property("wifiPass"):
            raise SystemExit("the passphrase stayed on the window")
        if window.property("networkDetail") != "Home":
            raise SystemExit(f"preview network was {window.property('networkDetail')}")
        if "not changed" not in (window.property("networkLine") or ""):
            raise SystemExit(f"preview network changed the computer: {window.property('networkLine')}")
        if not QMetaObject.invokeMethod(window, "encodeChoices"):
            raise SystemExit("encodeChoices did not run after the network")
        pump(50)
        import base64 as network_base64
        network_raw = network_base64.b64decode(window.property("encodedChoices") or "", validate=True)
        if b"not-stored-secret" in network_raw or b"passphrase" in network_raw:
            raise SystemExit("the passphrase was written into the choices")
        window.setProperty("page", 0)
        window.setProperty("avatar", "")
        pump(50)
        if window.property("avatar") != "":
            raise SystemExit("the account picture stayed selected")
        grab(shot / "user-no-avatar.png")
        window.setProperty("avatar", "knight.jpg")
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
    from PySide6.QtQuick import QQuickWindow
    import shiboken6

    app = QGuiApplication(sys.argv)
    engine = QQmlApplicationEngine()
    engine.warnings.connect(lambda warning: print("\n".join(item.toString() for item in warning) if isinstance(warning, list) else warning, file=sys.stderr))
    context = engine.rootContext()
    context.setContextProperty("WasdRepo", str(REPO))
    context.setContextProperty("WasdHold", shot_dir is not None)
    context.setContextProperty("WasdPreview", shot_dir is not None)
    context.setContextProperty("WasdWantPassword", shot_dir is not None)
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
    if window.property("phase") != "work":
        raise SystemExit("a matching password did not continue")
    if window.property("passwordDraft") or window.property("passwordAgainDraft"):
        raise SystemExit("the password stayed on the window")
    for path in shot.iterdir():
        if secret.encode() in path.read_bytes():
            raise SystemExit(f"the password was written to {path}")
    names = ["setting", "installing", "finishing"]
    for index, name in enumerate(names):
        window.setProperty("stepIndex", index)
        grab(shot / f"{name}.png")
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
