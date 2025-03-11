import re
import subprocess
from collections import namedtuple
from pathlib import Path

from albert import *

md_iid = "3.0"
md_version = "2.3"
md_name = "Mullvad"
md_description = "Manage mullvad VPN connections"
md_license = "MIT"
md_url = "https://github.com/albertlauncher/python"
md_authors = ["@Pete-Hamlin"]
md_credits = ["@janeklb", "@Bierchermuesli"]
md_bin_dependencies = ["mullvad"]


class Plugin(PluginInstance, GlobalQueryHandler):
    VPNConnection = namedtuple("VPNConnection", ["name", "connected"])
    iconUrls = ["xdg:network-wired"]
    blockedIcon = ["file:{}".format(Path(__file__).parent / "lock-10.png")]
    connectIcon = ["file:{}".format(Path(__file__).parent / "lock-9.png")]
    disconnectIcon = ["file:{}".format(Path(__file__).parent / "lock-1.png")]

    def __init__(self):
        PluginInstance.__init__(self)
        GlobalQueryHandler.__init__(self)

        self.connection_regex = re.compile(r"[a-z]{2}-[a-z]*-[a-z]{2,4}-[\d]{2,3}")

    def defaultTrigger(self) -> str:
        return "mullvad "

    def getRelays(self):
        relayStr = subprocess.check_output(
            "mullvad relay list", shell=True, encoding="UTF-8"
        )
        for relayStr in relayStr.splitlines():
            relay = relayStr.split()
            if relay and self.connection_regex.match(relay[0]):
                yield (relay[0], relayStr)

    def getIcon(self, status_string: str):
        match status_string:
            case "Blocked":
                return self.blockedIcon
            case "Disconnected":
                return self.disconnectIcon
            case "Connected":
                return self.connectIcon
            case _:
                return self.iconUrls

    def defaultItems(self) -> list[StandardItem]:
        statusStr = subprocess.check_output(
            "mullvad status", shell=True, encoding="UTF-8"
        ).strip()
        return [
            StandardItem(
                id="status",
                text="Status",
                subtext=statusStr,
                iconUrls=self.getIcon(statusStr),
                actions=[
                    Action(
                        "reconnect",
                        "Reconnect",
                        lambda: runDetachedProcess(["mullvad", "reconnect"]),
                    ),
                    Action(
                        "connect",
                        "Connect",
                        lambda: runDetachedProcess(["mullvad", "connect"]),
                    ),
                    Action(
                        "disconnect",
                        "Disconnect",
                        lambda: runDetachedProcess(["mullvad", "disconnect"]),
                    ),
                ],
            ),
        ]

    def actions(self) -> list[StandardItem]:
        return [
            StandardItem(
                id="connect",
                text="Connect",
                subtext="Connect to default server",
                iconUrls=self.connectIcon,
                actions=[
                    Action(
                        "connect",
                        "Connect",
                        lambda: runDetachedProcess(["mullvad", "connect"]),
                    )
                ],
            ),
            StandardItem(
                id="disconnect",
                text="Disconnect",
                subtext="Disconnect from VPN",
                iconUrls=self.disconnectIcon,
                actions=[
                    Action(
                        "disconnect",
                        "Disconnect",
                        lambda: runDetachedProcess(["mullvad", "disconnect"]),
                    )
                ],
            ),
            StandardItem(
                id="reconnect",
                text="Reconnect",
                subtext="Reconnect to current server",
                iconUrls=self.blockedIcon,
                actions=[
                    Action(
                        "reconnect",
                        "Reconnect",
                        lambda: runDetachedProcess(["mullvad", "reconnect"]),
                    )
                ],
            ),
        ]

    def buildItem(self, relay):
        name = relay[0]
        command = ["mullvad", "relay", "set", "location", name]
        subtext = relay[1]
        return StandardItem(
            id=f"vpn-{name}",
            text=name,
            subtext=subtext,
            iconUrls=self.iconUrls,
            actions=[
                Action(
                    "connect",
                    text="Connect",
                    callable=lambda: runDetachedProcess(command),
                ),
                Action("copy", "Copy to Clipboard", lambda t=name: setClipboardText(t)),
            ],
        )

    def handleTriggerQuery(self, query):
        if query.isValid:
            if query.string.strip():
                relays = self.getRelays()
                query.add(
                    [
                        item
                        for item in self.actions()
                        if query.string.lower() in item.text.lower()
                    ]
                )
                query.add(
                    [
                        self.buildItem(relay)
                        for relay in relays
                        if all(
                            q in relay[0].lower() for q in query.string.lower().split()
                        )
                    ]
                )
            else:
                query.add(self.defaultItems())

    def handleGlobalQuery(self, query):
        if query.string.strip():
            return [
                RankItem(item=item, score=0)
                for item in self.actions()
                if query.string.lower() in item.text.lower()
            ]
        else:
            return []
