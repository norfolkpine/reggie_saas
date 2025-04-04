import os
import requests
import re
from datetime import datetime, timedelta
from typing import List, Optional
from agno.agent import Agent
from agno.models.google import Gemini
from agno.tools import Toolkit
from agno.utils.log import logger


class CoinGeckoTools(Toolkit):
    def __init__(self):
        super().__init__(name="coingecko_tools")
        self.base_url = "https://api.coingecko.com/api/v3"
        self.coins_list = self.fetch_coin_list()  # Cache the list
    
        # Use environment variable or fallback to CoinGecko demo API key
        self.api_key = os.getenv("COINGECKO_API_KEY", "demo")

        # Set headers to automatically handle API key
        self.headers = {"x-cg-demo-api-key": self.api_key}

        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
            "x-cg-api-key": self.api_key  # Add API Key
        }

        # Registering functions as Agno tools
        self.register(self.get_current_price)
        self.register(self.get_historical_price)
        self.register(self.get_market_cap)
        self.register(self.get_coingecko_id)
        self.register(self.get_top_tokens)

    def fetch_coin_list(self) -> Optional[List[dict]]:
        """Fetches and caches the list of coins from CoinGecko."""
        url = f"{self.base_url}/coins/list"
        try:
            response = requests.get(url)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching coin list: {e}")
            return None

    def get_current_price(self, token: str, currency: str = "usd") -> str:
        """Fetches the current price of a given token and returns a formatted string."""
        token_data = self.get_coingecko_id(token)
        if not token_data:
            return f"Error: Token '{token}' not found."

        coingecko_id, name, symbol, _ = token_data

        url = f"{self.base_url}/simple/price?ids={coingecko_id}&vs_currencies={currency}"
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            data = response.json()

            price = data.get(coingecko_id, {}).get(currency.lower(), None)

            if price is not None:
                return f"The current price of {name} ({symbol.upper()}) is {price:,.10f} {currency.upper()}."
            else:
                return f"Error: Could not fetch price for {name} ({symbol.upper()}) in {currency.upper()}."

        except requests.exceptions.RequestException as e:
            return f"Error fetching current price: {e}"

    def get_historical_price(self, token: str, days: int = 7, currency: str = "usd") -> str:
        """Fetches historical prices for a given token over the last 'days' days."""
        token_id, _, _, _ = self.get_coingecko_id(token)
        if not token_id:
            return f"Error: Token '{token}' not found."

        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        start_timestamp = int(start_date.timestamp())
        end_timestamp = int(end_date.timestamp())

        url = f"{self.base_url}/coins/{token_id}/market_chart/range?vs_currency={currency}&from={start_timestamp}&to={end_timestamp}"
        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            prices = data.get("prices", [])

            if not prices:
                return f"Error: Could not retrieve historical price data for {token.upper()}."

            output = f"Historical prices for {token.upper()} (last {days} days):\n"
            for timestamp, price in prices:
                date = datetime.fromtimestamp(timestamp / 1000).strftime("%Y-%m-%d")
                output += f"- {date}: ${price} {currency.upper()}\n"
            return output
        
        except requests.exceptions.RequestException as e:
            return f"Error fetching historical price: {e}"

    def get_market_cap(self, token: str, currency: str = "usd") -> str:
        """Fetches the market cap of a given token."""
        token_id, _, _, _ = self.get_coingecko_id(token)
        if not token_id:
            return f"Error: Token '{token}' not found."

        url = f"{self.base_url}/coins/{token_id}"
        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            market_cap = data.get("market_data", {}).get("market_cap", {}).get(currency, None)

            if market_cap is not None:
                return f"The market cap of {token.upper()} is ${market_cap} {currency.upper()}."
            else:
                return f"Error: Could not fetch market cap for {token.upper()}."

        except requests.exceptions.RequestException as e:
            return f"Error fetching market cap: {e}"

    def get_coingecko_id(self, token: str) -> Optional[tuple]:
        """Retrieves the most actively traded CoinGecko ID for a given token using trading volume."""
        if not self.coins_list:
            return None

        # Find all matching tokens by symbol or name
        matching_tokens = [
            coin for coin in self.coins_list
            if coin["symbol"].lower() == token.lower() or coin["name"].lower() == token.lower()
        ]

        if not matching_tokens:
            return None

        # Fetch market data for all matching tokens
        market_data_url = f"{self.base_url}/coins/markets?vs_currency=usd&ids=" + ",".join(
            coin["id"] for coin in matching_tokens
        )

        try:
            response = requests.get(market_data_url, headers=self.headers)
            response.raise_for_status()
            market_data = response.json()

            # Sort by highest trading volume (most actively traded token)
            market_data = sorted(market_data, key=lambda x: x.get("total_volume", 0), reverse=True)

            if market_data:
                top_token = market_data[0]
                return top_token["id"], top_token["name"], top_token["symbol"], top_token["total_volume"]

        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching market data: {e}")

        return None


    def get_top_tokens(self, limit: int = 10, currency: str = "usd") -> str:
        """Fetches the top tokens by market cap."""
        url = f"{self.base_url}/coins/markets?vs_currency={currency}&order=market_cap_desc&per_page={limit}&page=1&sparkline=false"
        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()

            if not data:
                return "Error: Could not retrieve top tokens data."

            output = f"Top {limit} tokens by market cap:\n"
            for token in data:
                output += f"{token['name']} ({token['symbol']}): ${token['current_price']} {currency.upper()} (Market Cap: ${token['market_cap']:,.0f})\n" 
            return output

        except requests.exceptions.RequestException as e:
            return f"Error fetching top tokens: {e}"