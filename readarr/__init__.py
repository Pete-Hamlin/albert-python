"""Extension to interact with a readarr instance API.

Extension supports searching existing library of authors and adding new authors.

"""

from pathlib import Path
from time import sleep
from typing import Dict, Iterator
from urllib import parse

import requests
from albert import *

md_iid = "2.3"
md_version = "1.3"
md_name = "Readarr"
md_description = "Manage books/authors via a readarr instance"
md_license = "MIT"
md_url = "https://github.com/Pete-Hamlin/albert-python"
md_authors = ["@Pete-Hamlin"]
md_lib_dependencies = ["requests"]


class Plugin(PluginInstance, TriggerQueryHandler):
    iconUrls = [f"file:{Path(__file__).parent}/readarr.png"]
    user_agent = "org.albert.readarr"

    def __init__(self):
        PluginInstance.__init__(self)
        TriggerQueryHandler.__init__(
            self,
            id=self.id,
            name=self.name,
            description=self.description,
            synopsis="<author or book>",
            defaultTrigger="readarr ",
        )

        self._instance_url = self.readConfig("instance_url", str) or "http://localhost:8787"
        self._api_key = self.readConfig("api_key", str) or ""

        self._root_path = self.readConfig("root_path", str) or "/books"
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
                # Add new author
                query_str = stripped[3:]
                if query_str:
                    data = self.author_lookup(query_str)
                    items = [item for item in self.gen_add_items(data)] if data else []
                    if items:   
                        query.add(items)
                    else:
                        query.add(
                            StandardItem(
                                id=self.id,
                                iconUrls=self.iconUrls,
                                text=f"Search {query_str}",
                                subtext="Search for authors/books on Readarr",
                                actions=[
                                    Action(
                                        "search",
                                        "Search on Readarr",
                                        lambda url=f"{self._instance_url}/add/search?term={query_str}": openUrl(url),
                                    ),
                                ]
                            )
                        )
                else:
                    query.add(
                        StandardItem(
                            id=self.id, text=self.name, subtext="Add a new author on readarr", iconUrls=self.iconUrls
                        )
                    )
            else:
                # Search existing series
                data = (item for item in self.refresh_authors() or [] if stripped in item["authorName"].lower())
                items = [item for item in self.gen_search_items(data)] if data else []
                if items:
                    query.add(items)
                else:
                    query.add(
                        StandardItem(
                            id=self.id, text="Author not found", subtext=stripped, iconUrls=self.iconUrls
                        )
                    )
        else:
            query.add(
                StandardItem(
                    id=self.id, text=self.name, subtext="Search for an existing author on readarr", iconUrls=self.iconUrls
                )
            )

    def gen_add_items(self, data: Iterator[dict]) -> Iterator[Item]:
        for author in data:
            title = author["authorName"]
            status = author.get("status")
            subtext = "{} - {}".format(status.capitalize() if status else "", author.get("overview"))
            actions = [
                Action(
                    "monitor-search",
                    "Monitor + Search",
                    lambda chosen_author=author: self.add_author(chosen_author, search=True),
                ),
                Action(
                    "monitor",
                    "Monitor",
                    lambda chosen_author=author: self.add_author(chosen_author),
                ),
            ]

            for link in author.get("Links") or []:
                if link["name"] == "Goodreads":
                    actions.append(
                        Action(
                            "goodreads",
                            "View on Goodreads",
                            lambda url=link["url"]: openUrl(url),
                        ),
                    )

            yield StandardItem(id=self.id, iconUrls=self.iconUrls, text=title, subtext=subtext, actions=actions)

    def gen_search_items(self, data: Iterator[dict]) -> Iterator[Item]:
        for author in data:
            title = author["authorName"]
            status = author.get("status")
            subtext = "{} - {}/{} books owned".format(
                status.capitalize() if status else "",
                author["statistics"]["bookFileCount"],
                author["statistics"]["availableBookCount"],
            )
            url = "{}/author/{}".format(self._instance_url, author["id"])
            yield StandardItem(
                id="mvoie-{}".format(author["id"]),
                iconUrls=self.iconUrls,
                text=title,
                subtext=subtext,
                actions=[
                    Action(
                        "open",
                        "Open author in readarr",
                        lambda open_url=url: openUrl(open_url),
                    ),
                    Action(
                        "rescan",
                        "Rescan author",
                        lambda author_id=author["id"]: self.rescan_author(author_id),
                    ),
                    Action(
                        "delete",
                        "Delete author",
                        lambda author_id=author["id"]: self.delete_author(author_id),
                    ),
                ],
            )

    def author_lookup(self, query_string: str) -> Iterator[Dict] | None:
        params = {"term": query_string.strip()}
        url = f"{self._instance_url}/api/v1/author/lookup?{parse.urlencode(params)}"
        debug(f"Making GET request to {url}")
        response = requests.get(url, headers=self.headers)
        if response.ok:
            return (author for author in response.json())
        warning(f"Got response {response.status_code} when attempting to fetch author data")

    def refresh_authors(self) -> Iterator[dict] | None:
        url = f"{self._instance_url}/api/v1/author"
        debug(f"About to GET {url}")
        response = requests.get(url, headers=self.headers)
        if response.ok:
            return (author for author in response.json())
        else:
            warning(f"Got response {response.status_code} when attempting to fetch existing author data")

    def add_author(self, author: Dict, search: bool = False) -> None:
        url = f"{self._instance_url}/api/v1/author"
        data = author
        data["id"] = 0
        data["qualityProfileId"] = self._profile_id
        data["metadataProfileId"] = self._metadata_id
        data["addOptions"] = {
            "searchForMissingBooks": search,
            "monitored": self._default_monitor,
        }
        data["monitored"] = self._default_monitor
        data["rootFolderPath"] = self._root_path
        debug(f"Sending data: {data}")
        response = requests.post(url=url, json=data, headers=self.headers)
        if not response.ok:
            warning(f"Got response {response.status_code} - {response.text}")
        debug(f"Got response {response.status_code} from readarr")

    def rescan_author(self, author_id: str) -> None:
        url = f"{self._instance_url}/api/v1/command/"
        data = {"name": "RefreshAuthor", "authorIds": author_id}
        requests.post(url, json=data, headers=self.headers)

    def delete_author(self, author_id: str) -> None:
        url = f"{self._instance_url}/api/v1/author/{author_id}"
        data = {"id": author_id, "deleteFiles": self._delete_remove_files}
        requests.delete(url, json=data, headers=self.headers)
