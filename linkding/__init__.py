from datetime import datetime, timedelta
import requests
from pathlib import Path
from time import sleep
from albert import *
from urllib import parse

md_iid = "2.1"
md_version = "2.0"
md_name = "Linkding"
md_description = "Manage saved bookmarks via a linkding instance"
md_license = "MIT"
md_url = "https://github.com/Pete-Hamlin/albert-python"
md_maintainers = ["@Pete-Hamlin"]
md_lib_dependencies = ["requests"]


class Plugin(PluginInstance, TriggerQueryHandler):
    iconUrls = [f"file:{Path(__file__).parent}/linkding.png"]
    limit = 20
    user_agent = "org.albert.linkding"

    def __init__(self):
        TriggerQueryHandler.__init__(
            self,
            id=md_id,
            name=md_name,
            description=md_description,
            synopsis="<article-name>",
            defaultTrigger="ld ",
        )
        PluginInstance.__init__(self, extensions=[self])

        self._instance_url = self.readConfig("instance_url", str) or "http://localhost:9090"
        self._api_key = self.readConfig("api_key", str) or ""

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

    def configWidget(self):
        return [
            {"type": "lineedit", "property": "instance_url", "label": "URL"},
            {
                "type": "lineedit",
                "property": "api_key",
                "label": "API key",
                "widget_properties": {"echoMode": "Password"},
            },
        ]

    def handleTriggerQuery(self, query):
        stripped = query.string.strip()
        if stripped:
            # avoid spamming server
            for _ in range(50):
                sleep(0.01)
                if not query.isValid:
                    return

            data = self.get_results()
            articles = (item for item in data if stripped in self.create_filters(item))
            items = [item for item in self.gen_items(articles)]
            print(items)
            query.add(items)

        else:
            query.add(
                StandardItem(
                    id=md_id, text=md_name, subtext="Search for an article saved via Linkding", iconUrls=self.iconUrls
                )
            )
        #    query.add(
        #         StandardItem(
        #             id=md_id, text="Refresh cache", subtext="Refresh cached articles", iconUrls=self.iconUrls
        #         )
        #     )

    def create_filters(self, item: dict):
        # TODO: Add filter options?ld 
        return ",".join([item["url"], item["title"], ",".join(tag for tag in item["tag_names"])])

    def gen_items(self, articles: object):
            for article in articles:
                print(article)
                yield StandardItem(
                    id=md_id,
                    text=article["title"] or article['url'],
                    subtext="{}: {}".format(",".join(tag for tag in article["tag_names"]), article["url"]),
                    iconUrls=self.iconUrls,
                    actions=[
                        Action("open", "Open article", lambda u=article["url"]: openUrl(u)),
                        Action("copy", "Copy URL to clipboard", lambda u=article["url"]: setClipboardText(u)),
                    ],
                )

    def get_results(self):
        return self.fetch_results()

    def fetch_results(self):
        params = {"limit": self.limit}
        headers = {"User-Agent": self.user_agent, "Authorization": f"Token {self._api_key}"}
        url = f"{self._instance_url}/api/bookmarks/?{parse.urlencode(params)}"
        return (article for article_list in self.get_articles(url, headers) for article in article_list)
    
    def get_articles(self, url: str, headers: dict):
        while url:
            response = requests.get(url, headers=headers, timeout=5)
            if response.ok:
                result = response.json()
                url = result["next"]
                yield result["results"]
            else:
                warning(f"Got response {response.status_code} querying {url}")

