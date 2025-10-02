import contextlib
import random
import time
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

# ✅ V2 correct imports
from llama_index.core.schema import Document  # Use LlamaIndex Document
from agno.tools import Toolkit
from agno.utils.log import logger
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait


@dataclass
class SeleniumWebsiteReader:
    """Reader for Websites using Selenium (real browser) - V2 compatible"""

    max_depth: int = 3
    max_links: int = 10
    wait_time: int = 10  # Wait time for page load
    scroll_pause: float = 2.0  # Pause between scrolls
    chunk: bool = False  # Add chunk parameter

    _visited: set[str] = field(default_factory=set)
    _urls_to_crawl: list[tuple[str, int]] = field(default_factory=list)

    def __post_init__(self):
        """Setup Selenium WebDriver with options and set extra headers to bypass crawler restrictions."""
        chrome_options = Options()
        chrome_options.add_argument("--headless=new")  # headless mode (no GUI)
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)
        chrome_options.add_argument(
            "--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        # Add Accept-Language header
        chrome_options.add_argument("--lang=en-US,en;q=0.9")

        self.driver = webdriver.Chrome(options=chrome_options)
        # Remove webdriver property to avoid detection
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        # Set extra headers using Chrome DevTools Protocol (CDP)
        try:
            self.driver.execute_cdp_cmd("Network.enable", {})
            self.driver.execute_cdp_cmd(
                "Network.setExtraHTTPHeaders",
                {
                    "headers": {
                        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                        "Accept-Language": "en-US,en;q=0.9",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
                        "Referer": "https://www.google.com/",
                        "DNT": "1",
                        "Upgrade-Insecure-Requests": "1",
                    }
                },
            )
        except Exception as e:
            logger.warning(f"Could not set extra HTTP headers via CDP: {e}")

    def delay(self, min_seconds=1, max_seconds=3):
        """Introduce a random delay to mimic human browsing."""
        sleep_time = random.uniform(min_seconds, max_seconds)
        time.sleep(sleep_time)

    def _get_primary_domain(self, url: str) -> str:
        """Extract primary domain for filtering."""
        domain_parts = urlparse(url).netloc.split(".")
        return ".".join(domain_parts[-2:])

    def _wait_for_page_load(self, timeout: int = 10):
        """Wait for page to fully load."""
        try:
            WebDriverWait(self.driver, timeout).until(
                lambda driver: driver.execute_script("return document.readyState") == "complete"
            )
        except TimeoutException:
            logger.warning(f"Page load timeout after {timeout} seconds")

    def _scroll_page(self):
        """Scroll the page to load dynamic content."""
        try:
            # Get scroll height
            last_height = self.driver.execute_script("return document.body.scrollHeight")

            while True:
                # Scroll down to bottom
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")

                # Wait to load page
                time.sleep(self.scroll_pause)

                # Calculate new scroll height and compare with last scroll height
                new_height = self.driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height

        except Exception as e:
            logger.warning(f"Error during page scrolling: {e}")

    def _extract_main_content(self, soup: BeautifulSoup, url: str) -> str:
        """Extract main content intelligently from page with enhanced strategies."""
        content = ""
        debug_info = []

        # Strategy 1: Look for legal document specific patterns
        legal_selectors = [
            "div.body",
            "div.judgment",
            "div.decision",
            "div.case-content",
            "div[id*='content']",
            "div[id*='text']",
            "div[id*='body']",
            "div[class*='text']",
            "div[class*='body']",
            "div[class*='main']",
            "section[id*='content']",
            "section[class*='content']",
        ]

        for selector in legal_selectors:
            elements = soup.select(selector)
            for element in elements:
                text = element.get_text(strip=True, separator=" ")
                if len(text) > len(content):
                    content = text
                    debug_info.append(f"Found content with legal selector '{selector}': {len(text)} chars")

        # Strategy 2: Look for semantic HTML elements
        for tag in ["article", "main", "section"]:
            elements = soup.find_all(tag)
            for element in elements:
                text = element.get_text(strip=True, separator=" ")
                if len(text) > len(content):
                    content = text
                    debug_info.append(f"Found content in <{tag}> tag: {len(text)} chars")

        # Strategy 3: Look for content-specific classes
        content_classes = [
            "content",
            "main-content",
            "post-content",
            "entry-content",
            "article-content",
            "story-content",
            "text-content",
            "body-content",
            "page-content",
            "main-text",
            "article-body",
            "post-body",
            "judgment",
            "decision",
            "case-content",
            "legal-content",
        ]

        for class_name in content_classes:
            elements = soup.find_all(class_=class_name)
            for element in elements:
                text = element.get_text(strip=True, separator=" ")
                if len(text) > len(content):
                    content = text
                    debug_info.append(f"Found content in .{class_name} class: {len(text)} chars")

        # Strategy 4: Look for divs with high text density
        if not content:
            divs = soup.find_all("div")
            best_div = None
            best_score = 0

            for div in divs:
                text = div.get_text(strip=True, separator=" ")
                if len(text) > 100:  # Minimum content length
                    # Calculate text density (text length / total div length)
                    div_html = str(div)
                    text_density = len(text) / len(div_html) if div_html else 0

                    if text_density > best_score:
                        best_score = text_density
                        best_div = div

            if best_div:
                content = best_div.get_text(strip=True, separator=" ")
                debug_info.append(
                    f"Found content in high-density div: {len(content)} chars (density: {best_score:.3f})"
                )

        # Strategy 5: Fallback to body text
        if not content:
            body = soup.find("body")
            if body:
                content = body.get_text(strip=True, separator=" ")
                debug_info.append(f"Using body text as fallback: {len(content)} chars")

        # Clean up the content
        if content:
            # Remove excessive whitespace
            content = " ".join(content.split())
            # Remove common boilerplate
            content = self._remove_boilerplate(content)
            debug_info.append(f"After cleanup: {len(content)} chars")

        logger.debug(f"Content extraction debug for {url}: {'; '.join(debug_info)}")
        return content

    def _remove_boilerplate(self, text: str) -> str:
        """Remove common boilerplate text."""
        boilerplate_phrases = [
            "cookie policy",
            "privacy policy",
            "terms of service",
            "contact us",
            "about us",
            "subscribe",
            "newsletter",
            "follow us",
            "share this",
            "advertisement",
            "sponsored",
            "related articles",
            "recommended",
            "copyright",
            "all rights reserved",
            "powered by",
            "built with",
            "back to top",
            "menu",
            "navigation",
            "footer",
            "header",
            "search tips",
            "advanced search",
            "browse",
            "home",
        ]

        lines = text.split("\n")
        filtered_lines = []

        for line in lines:
            line_lower = line.lower().strip()
            is_boilerplate = any(phrase in line_lower for phrase in boilerplate_phrases)
            if not is_boilerplate and len(line.strip()) > 10:
                filtered_lines.append(line)

        return "\n".join(filtered_lines)

    def _get_all_text_content(self, soup: BeautifulSoup) -> str:
        """Get all text content from the page without filtering."""
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()

        # Get all text
        text = soup.get_text()

        # Clean up whitespace
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = " ".join(chunk for chunk in chunks if chunk)

        return text

    def chunk_document(self, doc: Document) -> list[Document]:
        """Chunk a document into smaller pieces - simplified for v2."""
        # Simple chunking implementation
        content = doc.text if hasattr(doc, 'text') else str(doc.content)
        chunk_size = 1000
        chunks = []
        
        for i in range(0, len(content), chunk_size):
            chunk_content = content[i:i + chunk_size]
            chunk_doc = Document(
                text=chunk_content,
                metadata={
                    **doc.metadata,
                    "chunk_index": i // chunk_size,
                    "chunk_size": len(chunk_content)
                }
            )
            chunks.append(chunk_doc)
        
        return chunks

    def crawl(self, url: str, starting_depth: int = 1) -> dict[str, str]:
        """Crawl pages using Selenium and extract main content."""
        num_links = 0
        crawler_result: dict[str, str] = {}
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

                # Wait for page to load
                self._wait_for_page_load(self.wait_time)

                # Scroll to load dynamic content
                self._scroll_page()

                # Get page source after JavaScript execution
                page_source = self.driver.page_source
                soup = BeautifulSoup(page_source, "html.parser")

                # [SCRAPE DEBUG] Log raw HTML
                logger.debug(f"[SCRAPE DEBUG] URL: {current_url}")
                print(f"[SCRAPE DEBUG] URL: {current_url}")
                logger.debug(f"[SCRAPE DEBUG] Raw HTML (first 100 chars): {page_source[:100]}")
                print(f"[SCRAPE DEBUG] Raw HTML (first 100 chars): {page_source[:100]}")

                # Extract main content
                main_content = self._extract_main_content(soup, current_url)

                # [SCRAPE DEBUG] Log extracted content
                logger.debug(f"[SCRAPE DEBUG] Extracted content (first 100 chars): {main_content[:100]}")
                print(f"[SCRAPE DEBUG] Extracted content (first 100 chars): {main_content[:100]}")

                if main_content and len(main_content) > 50:  # Minimum content threshold
                    crawler_result[current_url] = main_content
                    num_links += 1
                    logger.debug(f"Successfully extracted content from {current_url} ({len(main_content)} chars)")
                else:
                    logger.warning(f"Minimal or no content extracted from {current_url}")

                # Extract and queue internal links (only if we haven't reached max_links)
                if num_links < self.max_links:
                    for link in soup.find_all("a", href=True):
                        href_str = str(link["href"])
                        full_url = urljoin(current_url, href_str)
                        parsed_url = urlparse(full_url)

                        if parsed_url.netloc.endswith(primary_domain) and not any(
                            parsed_url.path.endswith(ext)
                            for ext in [".pdf", ".jpg", ".png", ".zip", ".gif", ".mp4", ".mp3"]
                        ):
                            full_url_str = str(full_url)
                            if (
                                full_url_str not in self._visited
                                and (full_url_str, current_depth + 1) not in self._urls_to_crawl
                            ):
                                self._urls_to_crawl.append((full_url_str, current_depth + 1))

            except TimeoutException as e:
                logger.error(f"Timeout while crawling {current_url}: {e}")
                continue
            except WebDriverException as e:
                logger.error(f"WebDriver error while crawling {current_url}: {e}")
                continue
            except Exception as e:
                logger.error(f"Failed to crawl {current_url}: {e}")
                continue

        return crawler_result

    def read(self, url: str) -> list[Document]:
        """Read website and return structured Documents."""
        logger.debug(f"Reading website: {url}")
        crawler_result = self.crawl(url)
        documents = []

        for crawled_url, crawled_content in crawler_result.items():
            # ✅ V2 compatible Document creation
            doc = Document(
                text=crawled_content,  # Use 'text' instead of 'content'
                metadata={
                    "url": crawled_url,
                    "name": url,
                    "id": crawled_url,
                }
            )
            if self.chunk:
                documents.extend(self.chunk_document(doc))
            else:
                documents.append(doc)

        # Clean up Selenium driver
        self.driver.quit()

        return documents


class WebsitePageScraperTools(Toolkit):
    """Tools for extracting content from a single web page using Selenium"""

    def __init__(self):
        super().__init__(name="website_page_scraper_tools")
        self.register(self.scrape)

    def scrape(self, url: str, selector: str = "") -> str:
        """
        Scrape a single web page and extract its <body> text content.
        Optionally use a CSS selector for more precise extraction.
        """
        try:
            logger.info(f"Scraping single page: {url}")
            reader = SeleniumWebsiteReader(max_depth=1, max_links=1)
            reader.driver.get(url)
            reader._wait_for_page_load(reader.wait_time)
            reader._scroll_page()
            page_source = reader.driver.page_source
            soup = BeautifulSoup(page_source, "html.parser")

            # Extract only the <body> text content
            body = soup.find("body")
            content = body.get_text(strip=True, separator=" ") if body else ""

            # Print the first 100 characters of the body text for debugging
            print(f"[SCRAPE DEBUG] <body> text (first 100 chars): {content[:100]}")

            logger.debug(f"[SCRAPE DEBUG] URL: {url}")
            logger.debug(f"[SCRAPE DEBUG] Selector: {selector!r}")
            logger.debug(f"[SCRAPE DEBUG] <body> text (first 100 chars): {content[:100]}")

            if selector:
                element = soup.select_one(selector)
                content = element.get_text(strip=True, separator=" ") if element else ""

            # Print the first 100 characters of the selected content for debugging (if selector is used)
            if selector:
                print(f"[SCRAPE DEBUG] Selector content (first 100 chars): {content[:100]}")

            if not content or len(content) < 50:
                logger.warning(f"Minimal or no content extracted from {url} (single page scrape)")
                return f"❌ Minimal or no content extracted from {url}."
            return content

        except Exception as e:
            logger.error(f"Error scraping single page {url}: {e}")
            return f"❌ Error scraping single page {url}: {str(e)}"
        finally:
            if "reader" in locals() and hasattr(reader, "driver"):
                with contextlib.suppress(Exception):
                    reader.driver.quit()


class WebsiteCrawlerTools(Toolkit):
    """Tools for crawling and extracting content from multiple web pages using Selenium"""

    def __init__(self):
        super().__init__(name="website_crawler_tools")
        self.register(self.crawl)

    def crawl(self, url: str, max_depth: int = 2, max_links: int = 5) -> str:
        """
        Crawl a website and extract its content using Selenium.
        """
        try:
            logger.info(f"Starting website crawl: {url}")
            reader = SeleniumWebsiteReader(max_depth=max_depth, max_links=max_links)
            crawler_result = reader.crawl(url)
            if not crawler_result:
                return f"No content could be extracted from {url}."
            summary_parts = [f"✅ Successfully crawled {len(crawler_result)} pages from {url}"]
            for page_url, content in crawler_result.items():
                truncated_content = content[:800] + "..." if len(content) > 800 else content
                summary_parts.append(f"\n--- {page_url} ({len(content)} chars) ---\n{truncated_content}")
            return "\n".join(summary_parts)
        except Exception as e:
            logger.error(f"Error crawling website {url}: {e}")
            return f"❌ Error crawling website {url}: {str(e)}"
        finally:
            if "reader" in locals() and hasattr(reader, "driver"):
                with contextlib.suppress(Exception):
                    reader.driver.quit()


class SeleniumTools(Toolkit):
    """Legacy toolkit for web scraping and browsing using Selenium (deprecated: use WebsitePageScraperTools or WebsiteCrawlerTools)"""

    def __init__(self):
        super().__init__(name="selenium_tools")
        self.register(self.scrape_website)
        self.register(self.debug_scrape_website)
        self.register(self.extract_raw_content)
        self.register(self.extract_legal_document)
        # scrape and crawl are now in their own toolkits

    def scrape_website(self, url: str) -> str:
        """Legacy method - use WebsitePageScraperTools instead"""
        scraper = WebsitePageScraperTools()
        return scraper.scrape(url)

    def debug_scrape_website(self, url: str) -> str:
        """Legacy method - use WebsitePageScraperTools instead"""
        scraper = WebsitePageScraperTools()
        return scraper.scrape(url)

    def extract_raw_content(self, url: str) -> str:
        """Legacy method - use WebsitePageScraperTools instead"""
        scraper = WebsitePageScraperTools()
        return scraper.scrape(url)

    def extract_legal_document(self, url: str) -> str:
        """Legacy method - use WebsitePageScraperTools instead"""
        scraper = WebsitePageScraperTools()
        return scraper.scrape(url)