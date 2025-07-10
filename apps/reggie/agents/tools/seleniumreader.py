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
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait


@dataclass
class SeleniumWebsiteReader(Reader):
    """Reader for Websites using Selenium (real browser)"""

    max_depth: int = 3
    max_links: int = 10
    wait_time: int = 10  # Wait time for page load
    scroll_pause: float = 2.0  # Pause between scrolls

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
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)
        chrome_options.add_argument(
            "--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )

        self.driver = webdriver.Chrome(options=chrome_options)
        # Remove webdriver property to avoid detection
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

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

                # Wait for page to load
                self._wait_for_page_load(self.wait_time)

                # Scroll to load dynamic content
                self._scroll_page()

                # Get page source after JavaScript execution
                page_source = self.driver.page_source
                soup = BeautifulSoup(page_source, "html.parser")

                # Extract main content
                main_content = self._extract_main_content(soup, current_url)
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
        self.register(self.debug_scrape_website)
        self.register(self.extract_raw_content)
        self.register(self.extract_legal_document)

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
            logger.info(f"Starting website scrape: {url}")

            # Create a temporary reader instance for this scrape
            reader = SeleniumWebsiteReader(max_depth=max_depth, max_links=max_links)

            # Crawl the website
            crawler_result = reader.crawl(url)

            if not crawler_result:
                return f"No content could be extracted from {url}. This might be due to:\n- The page requires JavaScript that couldn't be executed\n- The page has anti-bot protection\n- The page structure doesn't match our content extraction patterns\n- Network connectivity issues"

            # Create a summary of the scraped content
            summary_parts = []
            summary_parts.append(f"✅ Successfully scraped {len(crawler_result)} pages from {url}")

            for page_url, content in crawler_result.items():
                # Truncate content for summary
                truncated_content = content[:800] + "..." if len(content) > 800 else content
                summary_parts.append(f"\n--- {page_url} ({len(content)} chars) ---\n{truncated_content}")

            return "\n".join(summary_parts)

        except Exception as e:
            logger.error(f"Error scraping website {url}: {e}")
            return f"❌ Error scraping website {url}: {str(e)}\n\nThis could be due to:\n- Network connectivity issues\n- Invalid URL\n- Website blocking automated access\n- Selenium/Chrome driver issues"
        finally:
            # Ensure the driver is cleaned up
            if "reader" in locals() and hasattr(reader, "driver"):
                try:
                    reader.driver.quit()
                except:
                    pass

    def debug_scrape_website(self, url: str) -> str:
        """
        Debug version of website scraping with detailed information.

        Args:
            url: The URL to scrape

        Returns:
            Detailed debugging information about the scraping process
        """
        try:
            logger.info(f"Starting debug scrape: {url}")

            # Create a temporary reader instance
            reader = SeleniumWebsiteReader(max_depth=1, max_links=1)

            debug_info = []
            debug_info.append(f"🔍 Debug scraping: {url}")

            try:
                # Navigate to the page
                debug_info.append("📡 Navigating to page...")
                reader.driver.get(url)

                # Check page title
                title = reader.driver.title
                debug_info.append(f"📄 Page title: {title}")

                # Check page source length
                page_source = reader.driver.page_source
                debug_info.append(f"📏 Page source length: {len(page_source)} characters")

                # Check for common content indicators
                soup = BeautifulSoup(page_source, "html.parser")

                # Count various elements
                article_count = len(soup.find_all("article"))
                main_count = len(soup.find_all("main"))
                content_divs = len(soup.find_all(class_=lambda x: x and "content" in x.lower()))

                debug_info.append(f"🔍 Found {article_count} <article> tags")
                debug_info.append(f"🔍 Found {main_count} <main> tags")
                debug_info.append(f"🔍 Found {content_divs} divs with 'content' in class name")

                # Try to extract content
                content = reader._extract_main_content(soup, url)
                debug_info.append(f"📝 Extracted content length: {len(content)} characters")

                if content:
                    debug_info.append(f"📝 Content preview: {content[:200]}...")
                else:
                    debug_info.append("❌ No content extracted")

                # Get all text content for comparison
                all_text = reader._get_all_text_content(soup)
                debug_info.append(f"📄 All text content length: {len(all_text)} characters")

                # Calculate content coverage
                if all_text and content:
                    coverage = (len(content) / len(all_text)) * 100
                    debug_info.append(f"📊 Content coverage: {coverage:.1f}%")

                    if coverage < 50:
                        debug_info.append("⚠️ Low content coverage - may be missing important content")

                    # Show what might be missing
                    missing_chars = len(all_text) - len(content)
                    if missing_chars > 1000:
                        debug_info.append(f"⚠️ Potentially missing {missing_chars} characters of content")

                # Analyze page structure
                debug_info.append("\n🏗️ Page Structure Analysis:")

                # Find all divs with significant text
                significant_divs = []
                for div in soup.find_all("div"):
                    text = div.get_text(strip=True)
                    if len(text) > 500:  # Only consider divs with substantial text
                        significant_divs.append(
                            {
                                "text_length": len(text),
                                "id": div.get("id", "no-id"),
                                "class": " ".join(div.get("class", [])),
                                "preview": text[:100] + "..." if len(text) > 100 else text,
                            }
                        )

                # Sort by text length
                significant_divs.sort(key=lambda x: x["text_length"], reverse=True)

                debug_info.append(f"🔍 Found {len(significant_divs)} divs with >500 characters")
                for i, div_info in enumerate(significant_divs[:5]):  # Show top 5
                    debug_info.append(
                        f"  {i + 1}. {div_info['text_length']} chars | id='{div_info['id']}' | class='{div_info['class']}'"
                    )
                    debug_info.append(f"     Preview: {div_info['preview']}")

                # Check for JavaScript errors
                js_errors = reader.driver.execute_script(
                    "return window.performance.getEntriesByType('resource').filter(r => r.name.includes('error')).length"
                )
                debug_info.append(f"⚠️ JavaScript errors detected: {js_errors}")

                # Check for common legal document patterns
                debug_info.append("\n⚖️ Legal Document Analysis:")
                legal_patterns = {
                    "judgment": len(soup.find_all(string=lambda text: text and "judgment" in text.lower())),
                    "decision": len(soup.find_all(string=lambda text: text and "decision" in text.lower())),
                    "court": len(soup.find_all(string=lambda text: text and "court" in text.lower())),
                    "case": len(soup.find_all(string=lambda text: text and "case" in text.lower())),
                    "paragraphs": len(soup.find_all("p")),
                    "headings": len(soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])),
                }

                for pattern, count in legal_patterns.items():
                    debug_info.append(f"  📋 {pattern.title()}: {count} occurrences")

            except Exception as e:
                debug_info.append(f"❌ Error during debug: {str(e)}")

            return "\n".join(debug_info)

        except Exception as e:
            return f"❌ Debug failed: {str(e)}"
        finally:
            # Ensure the driver is cleaned up
            if "reader" in locals() and hasattr(reader, "driver"):
                try:
                    reader.driver.quit()
                except:
                    pass

    def extract_raw_content(self, url: str) -> str:
        """
        Extract raw content without any filtering or processing.

        Args:
            url: The URL to scrape

        Returns:
            Raw text content from the page
        """
        try:
            logger.info(f"Extracting raw content from: {url}")

            # Create a temporary reader instance
            reader = SeleniumWebsiteReader(max_depth=1, max_links=1)

            try:
                # Navigate to the page
                reader.driver.get(url)

                # Wait for page to load
                reader._wait_for_page_load(reader.wait_time)

                # Scroll to load dynamic content
                reader._scroll_page()

                # Get page source
                page_source = reader.driver.page_source
                soup = BeautifulSoup(page_source, "html.parser")

                # Extract all text content
                raw_content = reader._get_all_text_content(soup)

                return f"Raw content from {url}:\n\n{raw_content}"

            except Exception as e:
                return f"❌ Error extracting raw content: {str(e)}"

        except Exception as e:
            return f"❌ Failed to extract raw content: {str(e)}"
        finally:
            # Ensure the driver is cleaned up
            if "reader" in locals() and hasattr(reader, "driver"):
                try:
                    reader.driver.quit()
                except:
                    pass

    def extract_legal_document(self, url: str) -> str:
        """
        Extract legal document content with specialized handling for legal websites.

        Args:
            url: The URL to scrape

        Returns:
            Structured legal document content
        """
        try:
            logger.info(f"Extracting legal document from: {url}")

            # Create a temporary reader instance
            reader = SeleniumWebsiteReader(max_depth=1, max_links=1)

            try:
                # Navigate to the page
                reader.driver.get(url)

                # Wait for page to load
                reader._wait_for_page_load(reader.wait_time)

                # Scroll to load dynamic content
                reader._scroll_page()

                # Get page source
                page_source = reader.driver.page_source
                soup = BeautifulSoup(page_source, "html.parser")

                # Extract structured legal content
                legal_content = {}

                # Get case details
                case_details = {}
                coversheet = soup.find("div", class_="coversheet")
                if coversheet:
                    dt_elements = coversheet.find_all("dt")
                    dd_elements = coversheet.find_all("dd")
                    for dt, dd in zip(dt_elements, dd_elements):
                        key = dt.get_text(strip=True)
                        value = dd.get_text(strip=True)
                        case_details[key] = value

                # Get judgment content
                judgment_content = ""
                body_div = soup.find("div", class_="body")
                if body_div:
                    judgment_content = body_div.get_text(strip=True, separator=" ")

                # Get title
                title = soup.find("title")
                title_text = title.get_text(strip=True) if title else ""

                # Compile the result
                result_parts = []
                result_parts.append(f"LEGAL DOCUMENT: {title_text}")
                result_parts.append("=" * 80)

                if case_details:
                    result_parts.append("CASE DETAILS:")
                    for key, value in case_details.items():
                        result_parts.append(f"{key}: {value}")
                    result_parts.append("")

                if judgment_content:
                    result_parts.append("JUDGMENT CONTENT:")
                    result_parts.append(judgment_content)

                return "\n".join(result_parts)

            except Exception as e:
                return f"❌ Error extracting legal document: {str(e)}"

        except Exception as e:
            return f"❌ Failed to extract legal document: {str(e)}"
        finally:
            # Ensure the driver is cleaned up
            if "reader" in locals() and hasattr(reader, "driver"):
                try:
                    reader.driver.quit()
                except:
                    pass
