"""Extension to interact with a Lidarr instance API.

Extension supports searching existing library of artists and adding new artists.
"""

from collections.abc import Iterator
from pathlib import Path
from time import sleep
from typing import Dict
from urllib import parse

import requests
from albert import *

md_iid = "2.3"
md_version = "2.3"
md_name = "Lidarr"
md_description = "Manage music artists via a Lidarr instance"
md_license = "MIT"
md_url = "https://github.com/Pete-Hamlin/albert-python"
md_authors = ["@Pete-Hamlin"]
md_lib_dependencies = ["requests"]


class Plugin(PluginInstance, TriggerQueryHandler):
    iconUrls = [f"file:{Path(__file__).parent}/lidarr.png"]
    user_agent = "org.albert.lidarr"

    def __init__(self):
        PluginInstance.__init__(self)
        TriggerQueryHandler.__init__(
            self,
            id=self.id,
            name=self.name,
            description=self.description,
            synopsis="<artist>",
            defaultTrigger="lidarr ",
        )

        self._instance_url = self.readConfig("instance_url", str) or "http://localhost:8686"
        self._api_key = self.readConfig("api_key", str) or ""

        self._root_path = self.readConfig("root_path", str) or "/music"
        self._profile_id = self.readConfig("profile_id", int) or 1
        self._metadata_id = self.readConfig("metadata_id", int) or 1
        self._default_monitor = self.readConfig("default_monitor", bool) or True
        self._delete_remove_files = self.readConfig("delete_remove_files", bool) or False

        self.headers = {
            "User_Agent": self.user_agent,
            "X-Api-Key": self.api_key,
            "accept": "application/json",
        }

    @property
    def instance_url(self):
        return self._instance_url

    @instance_url.setter
    def instance_url(self, value):
        self._instance_url = value
        self.writeConfig("instance_url", value)

    @property
    def api_key(self):
        return self._api_key

    @api_key.setter
    def api_key(self, value):
        self._api_key = value
        self.writeConfig("api_key", value)

    @property
    def root_path(self):
        return self._root_path

    @root_path.setter
    def root_path(self, value):
        self._root_path = value
        self.writeConfig("root_path", value)

    @property
    def profile_id(self):
        return self._profile_id

    @profile_id.setter
    def profile_id(self, value):
        self._profile_id = value
        self.writeConfig("profile_id", value)

    @property
    def metadata_id(self):
        return self._metadata_id

    @metadata_id.setter
    def metadata_id(self, value):
        self._metadata_id = value
        self.writeConfig("metadata_id", value)

    @property
    def default_monitor(self):
        return self._default_monitor

    @default_monitor.setter
    def default_monitor(self, value):
        self._default_monitor = value
        self.writeConfig("default_monitor", value)

    @property
    def delete_remove_files(self):
        return self._delete_remove_files

    @delete_remove_files.setter
    def delete_remove_files(self, value):
        self._delete_remove_files = value
        self.writeConfig("delete_remove_files", value)

    def configWidget(self):
        return [
            {"type": "lineedit", "property": "instance_url", "label": "URL"},
            {
                "type": "lineedit",
                "property": "api_key",
                "label": "API key",
                "widget_properties": {"echoMode": "Password"},
            },
            {"type": "lineedit", "property": "root_path", "label": "Root Path"},
            {"type": "spinbox", "property": "profile_id", "label": "Profile ID"},
            {"type": "spinbox", "property": "metadata_id", "label": "Metadata ID"},
            {"type": "checkbox", "property": "default_monitor", "label": "Monitor by default"},
            {"type": "checkbox", "property": "delete_remove_files", "label": "Delete removes files"},
        ]

    def handleTriggerQuery(self, query):
        stripped = query.string.strip()
        if stripped:
            # avoid spamming server
            for _ in range(50):
                sleep(0.01)
                if not query.isValid:
                    return

            if stripped.startswith("add"):
                # Add new artist
                query_str = stripped[3:]
                if query_str:
                    data = self.artist_lookup(query_str)
                    items = [item for item in self.gen_add_items(data)] if data else []
                    if items:   
                        query.add(items)
                    else:
                        query.add(
                            StandardItem(
                                id=self.id,
                                iconUrls=self.iconUrls,
                                text=f"Search {query_str}",
                                subtext="Search for artist on Lidarr",
                                actions=[
                                    Action(
                                        "search",
                                        "Search on Lidarr",
                                        lambda url=f"{self._instance_url}/add/search?term={query_str}": openUrl(url),
                                    ),
                                ]
                            )
                        )
                else:
                    query.add(
                        StandardItem(
                            id=self.id, text=self.name, subtext="Add a new artist on Lidarr", iconUrls=self.iconUrls
                        )
                    )
            else:
                # Search existing artists
                data = (item for item in self.refresh_artist() or [] if stripped in item["artistName"].lower())
                items = [item for item in self.gen_search_items(data)] if data else []
                if items:
                    query.add(items)
                else:
                    query.add(
                        StandardItem(
                            id=self.id, text="Artist not found", subtext=stripped, iconUrls=self.iconUrls
                        )
                    )
        else:
            query.add(
                StandardItem(
                    id=self.id, text=self.name, subtext="Search for an existing artist on Lidarr", iconUrls=self.iconUrls
                )
            )

    def gen_add_items(self, data: Iterator[dict]) -> Iterator[Item]:
        for artist in data:
            title = artist["artistName"]
            status = artist.get("status")
            subtext = "{} - {}".format(artist.get("artistType"), status.capitalize() if status else "")
            actions = [
                Action(
                    "monitor",
                    "Monitor",
                    lambda chosen_artist=artist: self.add_artist(chosen_artist),
                ),
                Action(
                    "monitor-search",
                    "Monitor + Search",
                    lambda chosen_artist=artist: self.add_artist(chosen_artist, search_missing=True),
                ),
                Action(
                    "open",
                    "View on Lidarr",
                    lambda url=f"{self._instance_url}/add/new?term={title}": openUrl(url),
                ),
            ]
            for link in artist["links"]:
                if link["name"] == "musicmoz":
                    actions.append(
                        Action(
                            "musicmoz",
                            "View on MusicMoz",
                            lambda url=link["url"]: openUrl(url),
                        ),
                    )
                if link["name"] == "discogs":
                    actions.append(
                        Action(
                            "discogs",
                            "View on Discogs",
                            lambda url=link["url"]: openUrl(url),
                        ),
                    )
            yield StandardItem(id=self.id, iconUrls=self.iconUrls, text=title, subtext=subtext, actions=actions)

    def gen_search_items(self, data: Iterator[dict]) -> Iterator[Item]:
        for artist in data:
            title = artist["artistName"]
            artist_url = "{}/api/v1/artist/{}".format(self._instance_url, artist["id"])
            albums = artist["statistics"]["albumCount"]
            tracks = artist["statistics"]["trackFileCount"]
            total_tracks = artist["statistics"]["trackCount"]
            missing = total_tracks - tracks
            subtext = f"{albums} Albums: {tracks} Tracks"
            if missing:
                subtext += f" - {missing} Missing"
            yield StandardItem(
                id="artist-{}".format(artist["id"]),
                iconUrls=self.iconUrls,
                text=title,
                subtext=subtext,
                actions=[
                    Action(
                        "open",
                        "Open Artist in Lidarr",
                        lambda open_url=artist_url: openUrl(open_url),
                    ),
                    Action(
                        "rescan",
                        "Rescan Artist",
                        lambda artist_id=artist["id"]: self.rescan_artist(artist_id),
                    ),
                    Action(
                        "delete",
                        "Delete Artist",
                        lambda artist_id=artist["id"]: self.delete_artist(artist_id),
                    ),
                ],
            )

    def artist_lookup(self, query_string: str) -> Iterator[Dict] | None:
        params = {"term": query_string.strip()}
        url = f"{self._instance_url}/api/v1/artist/lookup/?{parse.urlencode(params)}"
        debug(f"Making GET request to {url}")
        response = requests.get(url, headers=self.headers)
        if response.ok:
            return (artist for artist in response.json())
        warning(f"Got response {response.status_code} when attempting to fetch artist data")

    def refresh_artist(self) -> Iterator[dict] | None:
        url = f"{self._instance_url}/api/v1/artist"
        response = requests.get(url, headers=self.headers)
        if response.ok:
            return (series for series in response.json())
        else:
            warning(f"Got response {response.status_code} when attempting to fetch artist data")

    def add_artist(self, artist: Dict, search_missing: bool = False) -> None:
        url = f"{self._instance_url}/api/v1/artist"
        data = {
            "artistName": artist["artistName"],
            "artistType": artist["artistType"],
            "foreignArtistId": artist["foreignArtistId"],
            "qualityProfileId": self._profile_id,
            "metadataProfileId": self._metadata_id,
            "images": artist["images"],
            "links": artist["links"],
            "rootFolderPath": self._root_path,
            "addOptions": {
                "monitored": self._default_monitor,
                "ignoreEpisodesWithoutFiles": not self._default_monitor,
                "searchForMissingAlbums": search_missing,
            },
        }
        debug(f"Sending data: {data}")
        response = requests.post(url=url, json=data, headers=self.headers)
        debug(f"Got response {response.status_code} from Lidarr")

    def rescan_artist(self, artist_id: str) -> None:
        url = f"{self._instance_url}/api/v1/command/"
        data = {"name": "RescanArtist", "artistId": artist_id}
        requests.post(url, json=data, headers=self.headers)

    def delete_artist(self, artist_id: str) -> None:
        url = f"{self._instance_url}/api/v1/artist/{artist_id}"
        data = {"id": artist_id, "deleteFiles": self._delete_remove_files}
        requests.delete(url, json=data, headers=self.headers)
