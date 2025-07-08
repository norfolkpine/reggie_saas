import random
import time
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple
from urllib.parse import urljoin, urlparse

from agno.document.base import Document
from agno.document.reader.base import Reader
from agno.tools import Toolkit
from agno.utils.log import logger
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options


@dataclass
class SeleniumWebsiteReader(Reader):
    """Reader for Websites using Selenium (real browser)"""

    max_depth: int = 3
    max_links: int = 10

    _visited: Set[str] = field(default_factory=set)
    _urls_to_crawl: List[Tuple[str, int]] = field(default_factory=list)

    def __post_init__(self):
        """Setup Selenium WebDriver with options."""
        chrome_options = Options()
        chrome_options.add_argument("--headless=new")  # headless mode (no GUI)
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument(
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )

        self.driver = webdriver.Chrome(options=chrome_options)

    def delay(self, min_seconds=1, max_seconds=3):
        """Introduce a random delay to mimic human browsing."""
        sleep_time = random.uniform(min_seconds, max_seconds)
        time.sleep(sleep_time)

    def _get_primary_domain(self, url: str) -> str:
        """Extract primary domain for filtering."""
        domain_parts = urlparse(url).netloc.split(".")
        return ".".join(domain_parts[-2:])

    def _extract_main_content(self, soup: BeautifulSoup) -> str:
        """Extract main content intelligently from page."""
        for tag in ["article", "main"]:
            element = soup.find(tag)
            if element:
                return element.get_text(strip=True, separator=" ")
        for class_name in ["content", "main-content", "post-content"]:
            element = soup.find(class_=class_name)
            if element:
                return element.get_text(strip=True, separator=" ")
        # Fallback to body text if nothing found
        body = soup.find("body")
        return body.get_text(strip=True, separator=" ") if body else ""

    def crawl(self, url: str, starting_depth: int = 1) -> Dict[str, str]:
        """Crawl pages using Selenium and extract main content."""
        num_links = 0
        crawler_result: Dict[str, str] = {}
        primary_domain = self._get_primary_domain(url)

        self._urls_to_crawl.append((url, starting_depth))

        while self._urls_to_crawl:
            current_url, current_depth = self._urls_to_crawl.pop(0)

            if (
                current_url in self._visited
                or not urlparse(current_url).netloc.endswith(primary_domain)
                or current_depth > self.max_depth
                or num_links >= self.max_links
            ):
                continue

            self._visited.add(current_url)
            self.delay()

            try:
                logger.debug(f"Crawling: {current_url}")
                self.driver.get(current_url)
                page_source = self.driver.page_source
                soup = BeautifulSoup(page_source, "html.parser")

                # Extract main content
                main_content = self._extract_main_content(soup)
                if main_content:
                    crawler_result[current_url] = main_content
                    num_links += 1

                # Extract and queue internal links
                for link in soup.find_all("a", href=True):
                    href_str = str(link["href"])
                    full_url = urljoin(current_url, href_str)
                    parsed_url = urlparse(full_url)

                    if parsed_url.netloc.endswith(primary_domain) and not any(
                        parsed_url.path.endswith(ext) for ext in [".pdf", ".jpg", ".png", ".zip"]
                    ):
                        full_url_str = str(full_url)
                        if (
                            full_url_str not in self._visited
                            and (full_url_str, current_depth + 1) not in self._urls_to_crawl
                        ):
                            self._urls_to_crawl.append((full_url_str, current_depth + 1))

            except Exception as e:
                logger.debug(f"Failed to crawl {current_url}: {e}")
                continue

        return crawler_result

    def read(self, url: str) -> List[Document]:
        """Read website and return structured Documents."""
        logger.debug(f"Reading website: {url}")
        crawler_result = self.crawl(url)
        documents = []

        for crawled_url, crawled_content in crawler_result.items():
            doc = Document(
                name=url,
                id=crawled_url,
                meta_data={"url": crawled_url},
                content=crawled_content,
            )
            if self.chunk:
                documents.extend(self.chunk_document(doc))
            else:
                documents.append(doc)

        # Clean up Selenium driver
        self.driver.quit()

        return documents


class SeleniumTools(Toolkit):
    """Tools for web scraping and browsing using Selenium"""

    def __init__(self):
        super().__init__(name="selenium_tools")
        
        # Register the main function as a tool
        self.register(self.scrape_website)

    def scrape_website(self, url: str, max_depth: int = 2, max_links: int = 5) -> str:
        """
        Scrape a website and extract its content using Selenium.
        
        Args:
            url: The URL to scrape
            max_depth: Maximum depth for crawling (default: 2)
            max_links: Maximum number of links to crawl (default: 5)
            
        Returns:
            A summary of the scraped content from the website
        """
        try:
            # Create a temporary reader instance for this scrape
            reader = SeleniumWebsiteReader(max_depth=max_depth, max_links=max_links)
            
            # Crawl the website
            crawler_result = reader.crawl(url)
            
            if not crawler_result:
                return f"No content could be extracted from {url}"
            
            # Create a summary of the scraped content
            summary_parts = []
            summary_parts.append(f"Successfully scraped {len(crawler_result)} pages from {url}")
            
            for page_url, content in crawler_result.items():
                # Truncate content for summary
                truncated_content = content[:500] + "..." if len(content) > 500 else content
                summary_parts.append(f"\n--- {page_url} ---\n{truncated_content}")
            
            return "\n".join(summary_parts)
            
        except Exception as e:
            logger.error(f"Error scraping website {url}: {e}")
            return f"Error scraping website {url}: {str(e)}"
        finally:
            # Ensure the driver is cleaned up
            if hasattr(reader, 'driver'):
                try:
                    reader.driver.quit()
                except:
                    pass
