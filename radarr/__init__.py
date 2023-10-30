"""Extension to interact with a Radarr instance API.

Extension supports searching existing library of films and adding new films.

"""

import os
from pathlib import Path
from time import sleep
from typing import Dict, List
from urllib import parse

import requests
from albert import *

md_iid = "2.1"
md_version = "2.0"
md_name = "Radarr"
md_description = "Manage films via a Radarr instance"
md_license = "MIT"
md_url = "https://github.com/Pete-Hamlin/albert-python"
md_maintainers = ["@Pete-Hamlin"]
md_lib_dependencies = ["requests"]


class Plugin(PluginInstance, TriggerQueryHandler):
    iconUrls = [f"file:{Path(__file__).parent}/radarr.png"]
    user_agent = "org.albert.radarr"

    def __init__(self):
        TriggerQueryHandler.__init__(
            self,
            id=md_id,
            name=md_name,
            description=md_description,
            synopsis="<film-title>",
            defaultTrigger="radarr ",
        )
        PluginInstance.__init__(self, extensions=[self])

        self._instance_url = self.readConfig("instance_url", str) or "http://localhost:8989"
        self._api_key = self.readConfig("api_key", str) or ""

        self._root_path = self.readConfig("root_path", str) or "/movies"
        self._profile_id = self.readConfig("profile_id", int) or 1
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
                # Add new series
                if stripped[3:]:
                    data = self.movie_lookup(stripped[3:])
                    items = [item for item in self.gen_add_items(data)]
                    query.add(items)
                else:
                    query.add(
                        StandardItem(
                            id=md_id, text=md_name, subtext="Add a new movie on Radarr", iconUrls=self.iconUrls
                        )
                    )
            else:
                # Search existing series
                data = (item for item in self.refresh_series() if stripped in item["title"].lower())
                items = [item for item in self.gen_search_items(data)]
                query.add(items)
        else:
            query.add(
                StandardItem(
                    id=md_id, text=md_name, subtext="Search for an existing movie on Radarr", iconUrls=self.iconUrls
                )
            )

    def gen_add_items(self, data: list[dict]) -> List[Item]:
        for movie in data:
            print(data)
            title = "{} ({})".format(movie["title"], movie["year"])
            subtext = movie.get("overview")
            imdb_url = "https://www.imdb.com/title/{}".format(movie.get("imdbId"))
            yield StandardItem(
                id=md_id,
                iconUrls=self.iconUrls,
                text=title,
                subtext=subtext,
                actions=[
                    Action(
                        "monitor-search",
                        "Monitor + Search",
                        lambda chosen_movie=movie: self.add_movie(chosen_movie, search=True),
                    ),
                    Action(
                        "monitor",
                        "Monitor",
                        lambda chosen_movie=movie: self.add_movie(chosen_movie),
                    ),
                    Action(
                        "view",
                        "View on Radarr",
                        lambda url=f"{self._instance_url}/add/new?term={title}": openUrl(url),
                    ),
                    Action(
                        "imdb",
                        "View on IMDB",
                        lambda url=imdb_url: openUrl(url),
                    ),
                ],
            )

    def gen_search_items(self, data: list[dict]) -> List[Item]:
        for movie in data:
            title = "{} ({})".format(movie["title"], movie["year"])
            url = "{}/movie/{}".format(self._instance_url, movie["id"])
            subtext = movie["overview"]
            yield StandardItem(
                id="mvoie-{}".format(movie["id"]),
                iconUrls=self.iconUrls,
                text=title,
                subtext=subtext,
                actions=[
                    Action(
                        "open",
                        "Open movie in Radarr",
                        lambda open_url=url: openUrl(open_url),
                    ),
                    Action(
                        "rescan",
                        "Rescan Movie",
                        lambda movie_id=movie["id"]: self.rescan_movie(movie_id),
                    ),
                    Action(
                        "delete",
                        "Delete Movie",
                        lambda movie_id=movie["id"]: self.delete_movie(movie_id),
                    ),
                ],
            )

    def movie_lookup(self, query_string: str) -> List[Dict]:
        params = {"term": query_string.strip()}
        url = f"{self._instance_url}/api/v3/movie/lookup?{parse.urlencode(params)}"
        debug(f"Making GET request to {url}")
        response = requests.get(url, headers=self.headers)
        if response.ok:
            return (movie for movie in response.json())
        warning(f"Got response {response.status_code} when attempting to fetch movie data")
        return []

    def refresh_series(self):
        url = f"{self._instance_url}/api/v3/movie"
        debug(f"About to GET {url}")
        response = requests.get(url, headers=self.headers)
        if response.ok:
            return (movie for movie in response.json())
        else:
            warning(f"Got response {response.status_code} when attempting to fetch existing movie data")

    def add_movie(self, movie: Dict, search: bool = False) -> None:
        url = f"{self._instance_url}/api/v3/movie"
        seasons = []
        data = movie
        data["id"] = 0
        data["qualityProfileId"] = self._profile_id
        data["addOptions"] = {
            "searchForMovie": search,
            "ignoreEpisodesWithFiles": False,
            "ignoreEpisodesWithoutFiles": False,
        }
        data["monitored"] = self._default_monitor
        data["rootFolderPath"] = self._root_path
        debug(f"Sending data: {data}")
        response = requests.post(url=url, json=data, headers=self.headers)
        if not response.ok:
            warning(f"Got response {response.status_code} - {response.text}")
        debug(f"Got response {response.status_code} from Radarr")

    def rescan_movie(self, movie_id: str) -> None:
        url = f"{self._instance_url}/api/v3/command/"
        data = {"name": "RefreshMovie", "movieIds": movie_id}
        requests.post(url, json=data, headers=self.headers)

    def delete_movie(self, movie_id: str) -> None:
        url = f"{self._instance_url}/api/v3/movie/{movie_id}"
        data = {"id": movie_id, "deleteFiles": self._delete_remove_files}
        requests.delete(url, json=data, headers=self.headers)
