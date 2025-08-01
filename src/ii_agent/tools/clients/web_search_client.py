import json
import os
import asyncio
import aiohttp
import urllib
from ii_agent.tools.utils import truncate_content
from ii_agent.core.storage.models.settings import Settings
from typing import Optional


class BaseSearchClient:
    """
    A base class for search clients.
    """

    max_results: int
    name: str

    def forward(self, query: str) -> str:
        return asyncio.run(self.forward_async(query))

    async def forward_async(self, query: str) -> str:
        raise NotImplementedError("Subclasses must implement this method.")


class JinaSearchClient(BaseSearchClient):
    """
    A client for the Jina search engine.
    """

    name = "Jina"

    def __init__(self, max_results=10, api_key: Optional[str] = None, **kwargs):
        self.max_results = max_results
        self.api_key = api_key or ""

    async def _search_query_by_jina(self, query, max_results=10):
        """Searches the query using Jina AI search API."""
        jina_api_key = self.api_key
        if not jina_api_key:
            print("Error: Jina API key not provided")
            return []

        url = "https://s.jina.ai/"
        params = {"q": query, "num": max_results}
        encoded_url = url + "?" + urllib.parse.urlencode(params)

        headers = {
            "Authorization": f"Bearer {jina_api_key}",
            "X-Respond-With": "no-content",
            "Accept": "application/json",
        }

        search_response = []
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(encoded_url, headers=headers) as response:
                    if response.status == 200:
                        search_results_data = await response.json()
                        search_results = search_results_data["data"]
                        if search_results:
                            for result in search_results:
                                search_response.append(
                                    {
                                        "title": result.get("title", ""),
                                        "url": result.get("url", ""),
                                        "content": result.get("description", ""),
                                    }
                                )
                        return search_response
        except Exception as e:
            print(f"Error: {e}. Failed fetching sources. Resulting in empty response.")
            search_response = []

        return search_response

    async def forward_async(self, query: str) -> str:
        try:
            response = await self._search_query_by_jina(query, self.max_results)
            formatted_results = json.dumps(response, indent=4)
            return truncate_content(formatted_results)
        except Exception as e:
            return f"Error searching with Jina: {str(e)}"


class SerpAPISearchClient(BaseSearchClient):
    """
    A client for the SerpAPI search engine.
    """

    name = "SerpAPI"

    def __init__(self, max_results=10, api_key: Optional[str] = None, **kwargs):
        self.max_results = max_results
        self.api_key = api_key or ""

    async def _search_query_by_serp_api(self, query, max_results=10):
        """Searches the query using SerpAPI."""

        serpapi_api_key = self.api_key

        url = "https://serpapi.com/search.json"
        params = {"q": query, "api_key": serpapi_api_key}
        encoded_url = url + "?" + urllib.parse.urlencode(params)
        search_response = []
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(encoded_url) as response:
                    if response.status == 200:
                        search_results = await response.json()
                        if search_results:
                            results = search_results["organic_results"]
                            results_processed = 0
                            for result in results:
                                if results_processed >= max_results:
                                    break
                                search_response.append(
                                    {
                                        "title": result["title"],
                                        "url": result["link"],
                                        "content": result["snippet"],
                                    }
                                )
                                results_processed += 1
        except Exception as e:
            print(f"Error: {e}. Failed fetching sources. Resulting in empty response.")
            search_response = []

        return search_response

    async def forward_async(self, query: str) -> str:
        try:
            response = await self._search_query_by_serp_api(query, self.max_results)
            formatted_results = json.dumps(response, indent=4)
            return truncate_content(formatted_results)
        except Exception as e:
            return f"Error searching with SerpAPI: {str(e)}"


class DuckDuckGoSearchClient(BaseSearchClient):
    """
    A client for the DuckDuckGo search engine.
    """

    name = "DuckDuckGo"

    def __init__(self, max_results=10, **kwargs):
        self.max_results = max_results
        try:
            from duckduckgo_search import DDGS
        except ImportError as e:
            raise ImportError(
                "You must install package `duckduckgo-search` to run this tool: for instance run `pip install duckduckgo-search`."
            ) from e
        self.ddgs = DDGS(**kwargs)

    async def forward_async(self, query: str) -> str:
        # Note: duckduckgo_search doesn't have async support, so we run it in a thread pool
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None, self.ddgs.text, query, self.max_results
        )
        if len(results) == 0:
            raise Exception("No results found! Try a less restrictive/shorter query.")
        postprocessed_results = [
            f"[{result['title']}]({result['href']})\n{result['body']}"
            for result in results
        ]
        return truncate_content(
            "## Search Results\n\n" + "\n\n".join(postprocessed_results)
        )


class TavilySearchClient(BaseSearchClient):
    """
    A client for the Tavily search engine.
    """

    name = "Tavily"

    def __init__(self, max_results=5, api_key: Optional[str] = None, **kwargs):
        self.max_results = max_results
        self.api_key = api_key or ""
        if not self.api_key:
            print(
                "Warning: Tavily API key not provided. Tool may not function correctly."
            )

    async def forward_async(self, query: str) -> str:
        try:
            from tavily import AsyncTavilyClient
        except ImportError as e:
            raise ImportError(
                "You must install package `tavily` to run this tool: for instance run `pip install tavily-python`."
            ) from e

        try:
            # Initialize Tavily client
            tavily_client = AsyncTavilyClient(api_key=self.api_key)

            response = await tavily_client.search(query, max_results=self.max_results)

            # Check if response contains results
            if not response or "results" not in response or not response["results"]:
                return f"No search results found for query: {query}"

            # Format and return the results
            formatted_results = json.dumps(response["results"], indent=4)
            return truncate_content(formatted_results)

        except Exception as e:
            return f"Error searching with Tavily: {str(e)}"


class ImageSearchClient:
    """
    A client for the SerpAPI search engine.
    """

    name = "ImageSerpAPI"

    def __init__(self, max_results=10, api_key: Optional[str] = None, **kwargs):
        self.max_results = max_results
        self.api_key = api_key or ""

    async def _search_query_by_serp_api(self, query, max_results=10):
        """Searches the query using SerpAPI."""

        serpapi_api_key = self.api_key

        url = "https://serpapi.com/search.json"
        params = {"q": query, "api_key": serpapi_api_key, "engine": "google_images"}
        encoded_url = url + "?" + urllib.parse.urlencode(params)
        search_response = []
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(encoded_url) as response:
                    if response.status == 200:
                        search_results = await response.json()
                        if search_results:
                            results = search_results["images_results"]
                            results_processed = 0
                            for result in results:
                                if results_processed >= max_results:
                                    break
                                search_response.append(
                                    {
                                        "title": result["title"],
                                        "image_url": result["original"],
                                        "width": result["original_width"],
                                        "height": result["original_height"],
                                    }
                                )
                                results_processed += 1
        except Exception as e:
            print(f"Error: {e}. Failed fetching sources. Resulting in empty response.")
            search_response = []

        return search_response

    async def forward_async(self, query: str) -> str:
        try:
            response = await self._search_query_by_serp_api(query, self.max_results)
            formatted_results = json.dumps(response, indent=4)
            return truncate_content(formatted_results)
        except Exception as e:
            return f"Error searching with SerpAPI: {str(e)}"


def create_search_client(
    settings: Optional[Settings] = None, max_results=10, **kwargs
) -> BaseSearchClient:
    """
    A search client that selects from available search APIs in the following order:
    SerpAPI > Jina > Tavily > DuckDuckGo

    It defaults to DuckDuckGo if no API keys are found for the other services.

    Args:
        settings: Settings object containing API keys
        max_results: Maximum number of results to return
        **kwargs: Additional arguments
    """

    # Extract API keys from settings if available, otherwise fall back to environment
    serpapi_key = None
    jina_key = None
    tavily_key = None

    if settings and settings.search_config:
        serpapi_key = (
            settings.search_config.serpapi_api_key.get_secret_value()
            if settings.search_config.serpapi_api_key
            else None
        )
        jina_key = (
            settings.search_config.jina_api_key.get_secret_value()
            if settings.search_config.jina_api_key
            else None
        )
        tavily_key = (
            settings.search_config.tavily_api_key.get_secret_value()
            if settings.search_config.tavily_api_key
            else None
        )

    # Fall back to environment variables if not in settings
    if not serpapi_key:
        serpapi_key = os.environ.get("SERPAPI_API_KEY", "")
    if not jina_key:
        jina_key = os.environ.get("JINA_API_KEY", "")
    if not tavily_key:
        tavily_key = os.environ.get("TAVILY_API_KEY", "")

    if serpapi_key:
        print("Using SerpAPI to search")
        return SerpAPISearchClient(
            max_results=max_results, api_key=serpapi_key, **kwargs
        )

    if jina_key:
        print("Using Jina to search")
        return JinaSearchClient(max_results=max_results, api_key=jina_key, **kwargs)

    if tavily_key:
        print("Using Tavily to search")
        return TavilySearchClient(max_results=max_results, api_key=tavily_key, **kwargs)

    print("Using DuckDuckGo to search")
    return DuckDuckGoSearchClient(max_results=max_results, **kwargs)


def create_image_search_client(
    settings: Optional[Settings] = None, max_results=5, **kwargs
) -> Optional[ImageSearchClient]:
    """
    A search client that selects from available image search APIs.

    Args:
        settings: Settings object containing API keys
        max_results: Maximum number of results to return
        **kwargs: Additional arguments
    """

    # Extract API key from settings if available, otherwise fall back to environment
    serpapi_key = None

    if settings and settings.search_config:
        serpapi_key = (
            settings.search_config.serpapi_api_key.get_secret_value()
            if settings.search_config.serpapi_api_key
            else None
        )

    # Fall back to environment variables if not in settings
    if not serpapi_key:
        serpapi_key = os.environ.get("SERPAPI_API_KEY", "")

    if serpapi_key:
        print("Using SerpAPI to search for images")
        return ImageSearchClient(max_results=max_results, api_key=serpapi_key, **kwargs)
    else:
        print("No image search API key found")
        return None
