"""Extension to interact with a Sonarr instance API.

Extension supports searching existing library of series and adding new series.

"""

import os
from pathlib import Path
from time import sleep
from typing import Dict, List
from urllib import parse

import requests
from albert import *

md_iid = "2.2"
md_version = "2.1"
md_name = "Sonarr"
md_description = "Manage TV series via a Sonarr instance"
md_license = "MIT"
md_url = "https://github.com/Pete-Hamlin/albert-python"
md_authors = ["@Pete-Hamlin"]
md_lib_dependencies = ["requests"]


class Plugin(PluginInstance, TriggerQueryHandler):
    iconUrls = [f"file:{Path(__file__).parent}/sonarr.png"]
    user_agent = "org.albert.sonarr"

    def __init__(self):
        TriggerQueryHandler.__init__(
            self,
            id=md_id,
            name=md_name,
            description=md_description,
            synopsis="<series-title>",
            defaultTrigger="sonarr ",
        )
        PluginInstance.__init__(self, extensions=[self])

        self._instance_url = self.readConfig("instance_url", str) or "http://localhost:8989"
        self._api_key = self.readConfig("api_key", str) or ""

        self._root_path = self.readConfig("root_path", str) or "/tv"
        self._profile_id = self.readConfig("profile_id", int) or 3
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
                query_str = stripped[3:]
                if query_str:
                    data = self.series_lookup(query_str)
                    items = [item for item in self.gen_add_items(data)]
                    if items:   
                        query.add(items)
                    else:
                        query.add(
                            StandardItem(
                                id=md_id,
                                iconUrls=self.iconUrls,
                                text=f"Search {query_str}",
                                subtext="Search for series on Sonarr",
                                actions=[
                                    Action(
                                        "search",
                                        "Search on Sonarr",
                                        lambda url=f"{self._instance_url}/add/new?term={query_str}": openUrl(url),
                                    ),
                                ]
                            )
                        )
                else:
                    query.add(
                        StandardItem(
                            id=md_id, text=md_name, subtext="Add a new series on Sonarr", iconUrls=self.iconUrls
                        )
                    )
            else:
                # Search existing series
                data = (item for item in self.refresh_series() if stripped in item["title"].lower())
                items = [item for item in self.gen_search_items(data)]
                if items:
                    query.add(items)
                else:
                    query.add(
                        StandardItem(
                            id=md_id, text="Series not found", subtext=stripped, iconUrls=self.iconUrls
                        )
                    )
        else:
            query.add(
                StandardItem(
                    id=md_id, text=md_name, subtext="Search for an existing series on Sonarr", iconUrls=self.iconUrls
                )
            )

    def gen_add_items(self, data: list[dict]) -> List[Item]:
        for series in data:
            title = "{} ({})".format(series["title"], series["year"])
            subtext = "{}: {}".format(series.get("network"), series.get("overview"))
            imdb_url = "https://www.imdb.com/title/{}".format(series.get("imdbId"))
            yield StandardItem(
                id=md_id,
                iconUrls=self.iconUrls,
                text=title,
                subtext=subtext,
                actions=[
                    Action(
                        "monitor-search",
                        "Monitor + Search",
                        lambda chosen_series=series: self.add_series(chosen_series, search_missing=True),
                    ),
                    Action(
                        "monitor",
                        "Monitor",
                        lambda chosen_series=series: self.add_series(chosen_series),
                    ),
                    Action(
                        "imdb",
                        "View on IMDB",
                        lambda url=imdb_url: openUrl(url),
                    ),
                ],
            )

    def gen_search_items(self, data: list[dict]) -> List[Item]:
        for series in data:
            title = "{} ({})".format(series["title"], series["year"])
            url = "{}/series/{}".format(self._instance_url, series["id"])
            seasons = len(series["seasons"])
            episodes = series["episodeFileCount"]
            total_episodes = series["episodeCount"]
            missing = total_episodes - episodes
            subtext = f"{seasons} Seasons: {episodes} Episodes"
            if missing:
                subtext += f" - {missing} Missing"
            yield StandardItem(
                id="series-{}".format(series["id"]),
                iconUrls=self.iconUrls,
                text=title,
                subtext=subtext,
                actions=[
                    Action(
                        "open",
                        "Open Series in Sonarr",
                        lambda open_url=url: openUrl(open_url),
                    ),
                    Action(
                        "rescan",
                        "Rescan Series",
                        lambda series_id=series["id"]: self.rescan_series(series_id),
                    ),
                    Action(
                        "delete",
                        "Delete Series",
                        lambda series_id=series["id"]: self.delete_series(series_id),
                    ),
                ],
            )

    def series_lookup(self, query_string: str) -> List[Dict]:
        params = {"term": query_string.strip()}
        url = f"{self._instance_url}/api/series/lookup/?{parse.urlencode(params)}"
        debug(f"Making GET request to {url}")
        response = requests.get(url, headers=self.headers)
        if response.ok:
            return (series for series in response.json())
        warning(f"Got response {response.status_code} when attempting to fetch series data")
        return []

    def refresh_series(self):
        url = f"{self._instance_url}/api/series"
        response = requests.get(url, headers=self.headers)
        if response.ok:
            return (series for series in response.json())
        else:
            warning(f"Got response {response.status_code} when attempting to fetch series data")

    def add_series(self, series: Dict, search_missing: bool = False) -> None:
        url = f"{self._instance_url}/api/series"
        seasons = []
        for season in series["seasons"]:
            seasons.append(
                {
                    "seasonNumber": season["seasonNumber"],
                    "monitored": self.default_monitor,
                    "statistics": None,
                }
            )
        data = {
            "tvdbId": series["tvdbId"],
            "title": series["title"],
            "qualityProfileId": self._profile_id,
            "titleSlug": series["titleSlug"],
            "images": series["images"],
            "seasons": seasons,
            "rootFolderPath": self._root_path,
            "addOptions": {
                "ignoreEpisodesWithFiles": True,
                "ignoreEpisodesWithoutFiles": not self._default_monitor,
                "searchForMissingEpisodes": search_missing,
            },
        }
        debug(f"Sending data: {data}")
        response = requests.post(url=url, json=data, headers=self.headers)
        debug(f"Got response {response.status_code} from Sonarr")

    def rescan_series(self, series_id: str) -> None:
        url = f"{self._instance_url}/api/command/"
        data = {"name": "RescanSeries", "seriesId": series_id}
        requests.post(url, json=data, headers=self.headers)

    def delete_series(self, series_id: str) -> None:
        url = f"{self._instance_url}/api/series/{series_id}"
        data = {"id": series_id, "deleteFiles": self._delete_remove_files}
        requests.delete(url, json=data, headers=self.headers)
