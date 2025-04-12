import tkinter as tk
from tkinter import scrolledtext, messagebox, font, ttk
import requests
from bs4 import BeautifulSoup
from datetime import datetime, date
import time
import threading
import queue
import os
import traceback
from urllib.parse import urljoin
import google.generativeai as genai
import sqlite3
import feedparser
import webbrowser # Added for opening URLs

# --- Constants ---
APP_TITLE = "Indian News Scraper"
DEFAULT_DB_PATH = "news_archive.db"
SEARCH_TERM = "modi" # Keyword to filter articles by

# --- API Key Configuration ---
# SECURITY WARNING: Storing API keys directly in code is insecure.
# It's highly recommended to use environment variables or a secrets management system.
# Example: google_api_key = os.environ.get("GOOGLE_API_KEY")
GOOGLE_API_KEY = "AIzaSyB1BUTRr6br9uRzfZIebhnNgou8e1QUBgQ" # Replace if necessary

# --- Website Scraping Configuration ---
WEBSITES = {
    "Hindustan Times India": {
        "url": "https://www.hindustantimes.com/india-news",
        "article_selector": "div.cartHolder, section.listingPage > div > div.cartHolder",
        "title_selector": "h3 > a",
        "link_selector": "h3 > a",
        "date_selector": "span.dateTime",
        "content_fetch": True,
        "content_selector": "div.storyDetails, div.detail",
        "date_selector_article": "div.dateTime, div.detailInfo span",
    },
    "Indian Express India": {
        "url": "https://indianexpress.com/section/india/",
        "article_selector": "div.nation > div.articles",
        "title_selector": "h2 > a, h3 > a",
        "link_selector": "h2 > a, h3 > a",
        "date_selector": "div.date",
        "content_fetch": True,
        "content_selector": "div.story_details, div.full-details",
        "date_selector_article": "span[itemprop='dateModified'], #postinfo_meta span",
    },
    "Times of India": {
        "rss_feed_url": "https://timesofindia.indiatimes.com/rssfeeds/-2128936835.cms",
        "content_fetch": True,
        "content_selector": "div._s30J.clearfix, div.article_content",
        "date_selector_article": "div.byline > span, div._3Mkg- byline",
    },
    "The Hindu": {
        "rss_feed_url": "https://www.thehindu.com/news/national/feeder/default.rss",
        "content_fetch": True,
        "content_selector": "div.article-body, div[itemprop='articleBody']",
        "date_selector_article": "span.publish-time, div.ut-container > span, meta[itemprop='datePublished']",
    },
    "News18": {
        "rss_feed_url": "https://www.news18.com/commonfeeds/v1/eng/rss/india.xml",
        "content_fetch": True,
        "content_selector": "div.article-content, div#article-detail-content",
        "date_selector_article": "div.article_details > ul > li, span.article_date, div.published_date",
    },
    "Zee News": {
        "rss_feed_url": "https://zeenews.india.com/rss/india-national-news.xml",
        "content_fetch": True,
        "content_selector": "div.article-content, div.article_content, div.content",
        "date_selector_article": "span.article-date, div.article-dateline, span.date-app",
    },
    "India TV News": {
        "rss_feed_url": "https://www.indiatvnews.com/rssnews/topstory-india.xml",
        "content_fetch": True,
        "content_selector": "div.content, div.article-content, div.story-data",
        "date_selector_article": "span.date, span.published-date, div.author-details > span",
    },
    "FirstPost": {
        "rss_feed_url": "https://www.firstpost.com/commonfeeds/v1/mfp/rss/india.xml",
        "content_fetch": True,
        "content_selector": "div.article-content, div.inner-copy, div.story-content",
        "date_selector_article": "span.publish-date, div.article-details span, meta[property='article:published_time']",
    },
    "Tribune": {
        "rss_feed_url": "https://publish.tribuneindia.com/newscategory/india/feed/",
        "content_fetch": True,
        "content_selector": "div.article-content, div.story-content",
        "date_selector_article": "div.date-time, span.publish-date, meta[property='article:published_time']"
    },
    "The Week": {
        "rss_feed_url": "https://www.theweek.in/news/india.rss.xml",
        "content_fetch": True,
        "content_selector": "div.article-content, div.story-content, div.articleBody",
        "date_selector_article": "p.story-publish-date, span.date, meta[property='article:published_time']",
    },
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# --- Google AI Setup ---
google_api_key_configured = False
try:
    if not GOOGLE_API_KEY or GOOGLE_API_KEY == "YOUR_API_KEY_HERE": # Added check for placeholder
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        print("!!! WARNING: GOOGLE_API_KEY not set or is placeholder.    !!!")
        print("!!! Sentiment analysis will not work.                   !!!")
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    else:
        genai.configure(api_key=GOOGLE_API_KEY)
        google_api_key_configured = True
except Exception as e:
    print(f"Error configuring Google Generative AI: {e}")

# --- Database Functions ---

def init_db(db_path):
    """Initializes the SQLite database and creates the articles table if needed."""
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS articles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    article_date TEXT NOT NULL,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL UNIQUE,
                    content TEXT,
                    sentiment TEXT
                )
            ''')
            conn.commit()
        print(f"Database ready at {db_path}")
        return True
    except sqlite3.Error as e:
        print(f"Database Error (Initialization) at {db_path}: {e}")
        messagebox.showerror("Database Error", f"Could not initialize database:\n{db_path}\n\n{e}")
        return False
    except Exception as e:
        print(f"Unexpected Error (DB Init): {e}")
        messagebox.showerror("Database Error", f"Unexpected error initializing database:\n{e}")
        return False

def insert_article(db_path, article_data):
    """Inserts a single article into the database, ignoring duplicates based on URL."""
    sql = ''' INSERT OR IGNORE INTO articles(source, article_date, title, url, content, sentiment)
              VALUES(?,?,?,?,?,?) '''
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (
                article_data.get('source', 'N/A'),
                article_data.get('date', 'N/A'),
                article_data.get('title', 'N/A'),
                article_data.get('url', 'N/A'),
                article_data.get('content', ''),
                article_data.get('sentiment', 'N/A')
            ))
            conn.commit()
            return cursor.lastrowid # ID if inserted, 0 if ignored
    except sqlite3.Error as e:
        print(f"Database Error (Insert) for {article_data.get('url', 'N/A')}: {e}")
        return None # Indicate error
    except Exception as e:
        print(f"Unexpected Error (DB Insert): {e}")
        return None

# --- Web Scraping & Parsing Helpers ---

def safe_get_text(element, default=""):
    """Safely get stripped text from a BeautifulSoup element."""
    return element.get_text(strip=True) if element else default

def safe_get_attr(element, attr, default=""):
    """Safely get an attribute from a BeautifulSoup element, avoiding javascript links."""
    if not element:
        return default
    value = element.get(attr)
    if value and attr == 'href' and value.strip().lower().startswith('javascript:'):
        return default
    return value if value else default

def parse_date(date_str, site_name_context):
    """
    Attempts to parse various date string formats into a date object.
    Handles relative dates like 'today', common prefixes/suffixes, and timezones.
    Returns a date object or None if parsing fails.
    This function is complex due to the variety of date formats online.
    """
    if not date_str:
        return None

    today = date.today()
    original_date_str = date_str
    cleaned_date_str = date_str.strip()
    cleaned_date_str_lower = cleaned_date_str.lower()

    # Handle simple relative dates
    if any(word in cleaned_date_str_lower for word in ["hour", "minute", "today", "just now"]):
        return today
    if "yesterday" in cleaned_date_str_lower:
        return None # Explicitly skip yesterday

    # Clean common prefixes and timezone indicators
    prefixes = ["Updated :", "Published :", "Updated:", "Published:"]
    suffixes = ["IST", "PST", "GMT", "UTC"] # Keep suffixes simple for now

    for prefix in prefixes:
        if cleaned_date_str_lower.startswith(prefix.lower()):
            cleaned_date_str = cleaned_date_str[len(prefix):].strip()
            cleaned_date_str_lower = cleaned_date_str.lower() # Update lower version
            break # Assume only one prefix

    # Remove timezone offsets like +0530 (basic removal)
    parts = cleaned_date_str.split()
    if len(parts) > 1:
        last_part = parts[-1]
        if last_part.startswith('+') or (last_part.startswith('-') and ':' not in last_part):
             # Basic check to avoid removing parts of date like '2024-01-01'
             if not last_part.replace('-','').isdigit() or len(last_part) != 5:
                 cleaned_date_str = " ".join(parts[:-1]).strip()

    # Define formats to try (prioritize common ones)
    formats_to_try = [
        # Most common first
        "%b %d, %Y", "%d %b %Y", "%B %d, %Y", "%d %B %Y",
        "%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y", "%d/%m/%Y",
        # With time (time part is ignored)
        "%a, %d %b %Y %H:%M:%S", # RFC 5322 (often in RSS/meta)
        "%Y-%m-%dT%H:%M:%S",     # ISO 8601 common variant
        "%b %d, %Y, %I:%M %p", "%B %d, %Y %I:%M %p",
        "%d %b %Y %H:%M",
        # Less common
        "%Y%m%d",
        "%Y-%m-%dT%H:%M:%S.%fZ", # ISO 8601 with milliseconds and Z
    ]

    parsed_date = None
    for fmt in formats_to_try:
        try:
            # Handle potential 'Z' and milliseconds for specific ISO formats
            parse_str = cleaned_date_str
            if fmt.endswith("%fZ"):
                if '.' not in parse_str and parse_str.endswith('Z'):
                    parse_str = parse_str[:-1] + ".000Z"
                elif not parse_str.endswith('Z'): continue # Skip if format expects Z
            elif fmt == "%Y-%m-%dT%H:%M:%S" and parse_str.endswith('Z'):
                parse_str = parse_str[:-1] # Remove Z if format doesn't expect it

            parsed_datetime = datetime.strptime(parse_str, fmt)
            parsed_date = parsed_datetime.date()
            return parsed_date # Success
        except ValueError:
            # Try parsing just the date part if time might be included
            try:
                date_part = cleaned_date_str.split(',')[0].strip() # e.g., "Apr 12, 2025, ..."
                if date_part != cleaned_date_str: # Check if splitting actually did something
                    parsed_datetime = datetime.strptime(date_part, fmt)
                    parsed_date = parsed_datetime.date()
                    return parsed_date
            except ValueError:
                try:
                    date_part = cleaned_date_str.split('T')[0] # ISO Date part
                    if date_part != cleaned_date_str:
                        parsed_datetime = datetime.strptime(date_part, "%Y-%m-%d")
                        parsed_date = parsed_datetime.date()
                        return parsed_date
                except ValueError:
                    continue # Try next format

    # Fallback: Check if today's components are present (less reliable)
    if not parsed_date:
         year_str = str(today.year)
         month_short = today.strftime("%b").lower()
         month_long = today.strftime("%B").lower()
         day_str = str(today.day)
         # Check for day number with common separators/endings
         if (year_str in cleaned_date_str_lower and
             (month_short in cleaned_date_str_lower or month_long in cleaned_date_str_lower) and
             (f" {day_str} " in cleaned_date_str_lower or
              f" {day_str}," in cleaned_date_str_lower or
              cleaned_date_str_lower.endswith(f" {day_str}"))):
              print(f"[{site_name_context}] Warning: Fallback date match for '{original_date_str}'")
              return today

    print(f"[{site_name_context}] Failed to parse date: '{original_date_str}' (Cleaned: '{cleaned_date_str}')")
    return None

def fetch_html(url):
    """Fetches HTML/XML content from a URL with error handling and content type check."""
    try:
        response = requests.get(url, headers=HEADERS, timeout=20, stream=True)
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)

        content_type = response.headers.get('content-type', '').lower()
        if not ('html' in content_type or 'xml' in content_type or 'application/rss+xml' in content_type):
            print(f"Warning: Non-HTML/XML content type '{content_type}' from {url}. Skipping.")
            response.close()
            return None

        content = response.content # Read the content
        response.close()
        # Decode robustly, ignoring errors
        return content.decode('utf-8', errors='ignore')

    except requests.exceptions.Timeout:
        print(f"Timeout fetching {url}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Request error fetching {url}: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error fetching {url}: {e}")
        traceback.print_exc()
        return None

def get_article_content(article_url, config):
    """Fetches and extracts main article content using configured and fallback selectors."""
    if not article_url:
        return "Error: No URL provided for content fetching."

    # Ensure URL is absolute
    base_url = config.get('url', article_url) # Use article_url itself as base if 'url' isn't in config (likely RSS)
    try:
        absolute_url = urljoin(base_url, article_url.strip())
        if not absolute_url.startswith('http'):
             print(f"Could not construct absolute URL from base '{base_url}' and relative '{article_url}'")
             return "Error: Could not construct absolute URL."
    except Exception as e:
        print(f"Error joining base '{base_url}' and relative '{article_url}': {e}")
        return "Error: Could not construct absolute URL."

    print(f"Fetching content from: {absolute_url}")
    html = fetch_html(absolute_url)
    if not html:
        return "Error: Could not fetch article page."

    try:
        soup = BeautifulSoup(html, 'lxml')
        content_area = None
        used_selector = "N/A"

        # Try primary selectors first
        primary_selectors = config.get("content_selector", "").split(',')
        for sel in primary_selectors:
            sel = sel.strip()
            if sel:
                content_area = soup.select_one(sel)
                if content_area:
                    used_selector = sel
                    print(f"Using primary selector '{sel}' for {absolute_url}")
                    break

        # Try common fallbacks if primary fails
        if not content_area:
            print(f"Primary selector(s) '{config.get('content_selector')}' failed for {absolute_url}. Trying fallbacks...")
            common_selectors = [
                'div[itemprop="articleBody"]', 'div.article-body', 'div.story-body',
                'div.entry-content', 'div.main-content', 'div.story_details',
                'div.story-details', 'div.article-content', 'div#storybody',
                'article', 'main', 'div[role="main"]',
                'div.article-body-content', 'div.abp-story-detail', 'div._s30J.clearfix',
                'div.article_content', 'div.content', 'div.story-data', 'div.inner-copy',
                'div.articleBody' # Added from The Week config
            ]
            for sel in common_selectors:
                content_area = soup.select_one(sel)
                if content_area:
                    print(f"Using fallback selector '{sel}' for {absolute_url}")
                    used_selector = sel
                    break

        # Extract text if content area found
        if content_area:
            # Get paragraphs, preferring direct children first
            paragraphs = content_area.find_all('p', recursive=False)
            if not paragraphs:
                paragraphs = content_area.find_all('p')

            content_parts = []
            for p in paragraphs:
                # Skip if paragraph seems to be inside a figure/caption/aside
                parent = p.find_parent(['figure', 'figcaption', 'aside'])
                if parent and parent in content_area.find_parents(['figure', 'figcaption', 'aside']):
                    continue

                text = p.get_text(" ", strip=True)

                # Filter out short/irrelevant paragraphs
                if text and len(text) > 40 and 'Advertisement' not in text and 'also read:' not in text.lower():
                    # Avoid paragraphs that are mostly just link text
                    links_in_p = p.find_all('a')
                    link_text_len = sum(len(a.get_text(strip=True)) for a in links_in_p)
                    if len(text) - link_text_len > 20: # Require some non-link text
                        content_parts.append(text)

            content = "\n\n".join(content_parts)
            if content:
                 return content
            else:
                 # Last resort: get all text from the content area
                 fallback_text = content_area.get_text(" ", strip=True)
                 if fallback_text and len(fallback_text) > 100:
                     print(f"Warning: Extracted content using get_text() fallback for {absolute_url}")
                     return fallback_text
                 else:
                    return f"Warning: Content area found (selector: '{used_selector}'), but no suitable text extracted."
        else:
            return "Error: Could not find content area using any selectors."

    except Exception as e:
        print(f"Error parsing content from {absolute_url}: {e}")
        traceback.print_exc()
        return f"Error: Parsing content failed ({e})"

# --- Sentiment Analysis ---

def get_sentiment(text):
    """Determines sentiment using Google Gemini API (Positive, Negative, Neutral)."""
    if not google_api_key_configured:
        return "API Key Missing"

    max_chars = 8000 # Limit input text length
    truncated_text = text[:max_chars]

    prompt = f"""Analyze the sentiment of the following news article content regarding the main subject mentioned. Respond with only one word: Positive, Negative, or Neutral.

    Text:
    \"\"\"
    {truncated_text}
    \"\"\"

    Sentiment:"""

    try:
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
        generation_config = genai.types.GenerationConfig(temperature=0, max_output_tokens=10)
        safety_settings=[ # Allow most content, typical for news analysis
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]

        response = model.generate_content(
            prompt,
            generation_config=generation_config,
            safety_settings=safety_settings
        )

        if not response.candidates:
             print("Warning: Gemini response blocked or empty.")
             try: print(f"Prompt Feedback: {response.prompt_feedback}")
             except Exception: pass
             return "Blocked"

        sentiment = response.text.strip().capitalize()

        # Validate and normalize response
        if sentiment in ["Positive", "Negative", "Neutral"]:
            return sentiment
        elif "positive" in sentiment.lower(): return "Positive"
        elif "negative" in sentiment.lower(): return "Negative"
        elif "neutral" in sentiment.lower(): return "Neutral"
        else:
            print(f"Warning: Unexpected sentiment response: '{sentiment}'")
            return "Unknown"

    except Exception as e:
        print(f"Error getting sentiment from Google Gemini: {e}")
        traceback.print_exc()
        if "API key not valid" in str(e) or "PermissionDenied" in str(e):
            return "Auth Error"
        return "API Error"

# --- Core Scraping Logic ---

def _process_article(article_info, config, results_queue):
    """Fetches content, gets sentiment, and queues the result if it matches the filter."""
    title = article_info['title']
    link = article_info['link']
    article_date = article_info['article_date']
    site_name = article_info['site_name']

    content = "Content not fetched."
    sentiment = "Not Analyzed"

    if config.get("content_fetch"):
        time.sleep(0.2) # Politeness delay
        content = get_article_content(link, config)

    # Filter by search term in title or content
    title_lower = title.lower()
    content_lower = content.lower()

    if SEARCH_TERM in title_lower or SEARCH_TERM in content_lower:
        # Get sentiment if content was fetched successfully
        if not content.startswith("Error:") and not content.startswith("Warning:") and content != "Content not fetched.":
            print(f"[{site_name}] Getting sentiment for: {title[:50]}...")
            text_for_sentiment = f"Title: {title}\n\nContent: {content}"
            sentiment = get_sentiment(text_for_sentiment)
            time.sleep(0.5) # Delay after API call
        else:
            sentiment = "No Content" # Indicate content fetching issue

        # Prepare and queue the final result
        result = {
            "title": title,
            "date": article_date.strftime("%Y-%m-%d"),
            "sentiment": sentiment,
            "content": content,
            "source": site_name,
            "url": link
        }
        results_queue.put(result)
        return True # Indicates article matched filter and was processed
    else:
        # print(f"[{site_name}] Skipping article (filter mismatch): {title[:50]}...") # Optional logging
        return False # Indicates article did not match filter

def _scrape_rss_feed(site_name, config, today_date, results_queue, processed_links):
    """Scrapes articles from an RSS feed."""
    feed_url = config['rss_feed_url']
    print(f"[{site_name}] Using RSS feed: {feed_url}")
    feed_content = fetch_html(feed_url)
    if not feed_content:
        results_queue.put(f"--- Failed to fetch RSS feed for {site_name} ---")
        return 0 # Return count of matched articles

    feed = feedparser.parse(feed_content)
    matched_count = 0

    if feed.bozo:
        print(f"[{site_name}] Warning: RSS parsing issue: {feed.bozo_exception}")
        results_queue.put(f"--- Warning: RSS parsing issue for {site_name} ---")

    if not feed.entries:
        print(f"[{site_name}] No entries found in RSS feed.")
        results_queue.put(f"--- No entries found in RSS feed for {site_name} ---")
        return 0

    print(f"[{site_name}] Found {len(feed.entries)} items in RSS feed.")

    for entry in feed.entries:
        title = entry.get('title', '').strip()
        link = entry.get('link', '').strip()

        if not link or not title:
            print(f"[{site_name}] Skipping RSS entry: missing title or link.")
            continue

        # Ensure link is absolute
        try:
            base_url = feed.feed.get('link', '') # Use feed's base URL if available
            link = urljoin(base_url, link)
            if not link.startswith('http'):
                print(f"[{site_name}] Skipping invalid RSS link after join: {link}")
                continue
        except Exception as e:
            print(f"[{site_name}] Error processing RSS link {link}: {e}")
            continue

        if link in processed_links:
            continue
        processed_links.add(link)

        # Parse date from RSS entry
        article_date = None
        if hasattr(entry, 'published_parsed') and entry.published_parsed:
            try:
                ts = time.mktime(entry.published_parsed)
                article_date = datetime.fromtimestamp(ts).date()
            except Exception as e:
                print(f"[{site_name}] Error converting RSS parsed date: {e}. Trying 'published'.")
                date_str = entry.get('published')
                if date_str:
                    article_date = parse_date(date_str, f"{site_name} (RSS String)")
        elif 'published' in entry:
            date_str = entry.get('published')
            if date_str:
                article_date = parse_date(date_str, f"{site_name} (RSS String)")

        # Process if date matches today
        if article_date == today_date:
            article_info = {
                'title': title,
                'link': link,
                'article_date': article_date,
                'site_name': site_name
            }
            if _process_article(article_info, config, results_queue):
                matched_count += 1
        # else: # Optional logging for non-matching dates
        #     if article_date: print(f"[{site_name}] Skipping RSS (not today: {article_date}): {title[:50]}...")
        #     else: print(f"[{site_name}] Skipping RSS (no date): {title[:50]}...")

    return matched_count

def _scrape_html_listing(site_name, config, today_date, results_queue, processed_links):
    """Scrapes articles from an HTML listing page."""
    list_url = config['url']
    print(f"[{site_name}] Using HTML scraping: {list_url}")
    html_content = fetch_html(list_url)
    if not html_content:
        results_queue.put(f"--- Failed to fetch HTML listing for {site_name} ---")
        return 0

    soup = BeautifulSoup(html_content, 'lxml')
    matched_count = 0

    # Find article elements using configured selectors
    articles = []
    for sel in config['article_selector'].split(','):
        sel = sel.strip()
        if sel:
            articles.extend(soup.select(sel))

    # Basic fallback if primary selectors fail
    if not articles:
         print(f"Warning: Primary selectors failed for {site_name}. Trying fallbacks...")
         articles = soup.find_all('article')
         if not articles:
             articles = soup.select('div[class*="item"], div[class*="post"], li[class*="item"], li[class*="post"]')
         if not articles:
             results_queue.put(f"--- No articles found on HTML listing for {site_name} (all selectors failed) ---")
             return 0

    print(f"[{site_name}] Found {len(articles)} potential article elements on listing page.")

    for article_element in articles:
        # Extract title, link, and potentially date from the listing item
        title_element = link_element = date_element = None
        for sel in config['title_selector'].split(','):
            title_element = article_element.select_one(sel.strip())
            if title_element: break
        for sel in config['link_selector'].split(','):
            link_element = article_element.select_one(sel.strip())
            if link_element: break
        if config.get('date_selector'):
            for sel in config['date_selector'].split(','):
                date_element = article_element.select_one(sel.strip())
                if date_element: break

        title = safe_get_text(title_element)
        link = safe_get_attr(link_element, 'href')

        if not link or not title:
            continue # Skip if essential info is missing

        # Resolve link URL
        try:
            link = urljoin(list_url, link.strip())
            if not link.startswith('http'):
                print(f"[{site_name}] Skipping invalid link after join: {link}")
                continue
        except Exception as e:
            print(f"[{site_name}] Error joining URL {link}: {e}")
            continue

        if link in processed_links:
            continue
        processed_links.add(link)

        # Attempt to parse date from listing
        article_date = None
        date_str_listing = None
        if date_element:
             date_str_listing = safe_get_attr(date_element, 'datetime') or safe_get_text(date_element)
             if date_str_listing:
                 article_date = parse_date(date_str_listing, f"{site_name} (Listing)")

        # Determine if fetching the article page is necessary
        fetch_article_page = config.get("content_fetch") or \
                             (not article_date and config.get("date_selector_article"))

        if fetch_article_page:
            time.sleep(0.2) # Politeness delay
            article_html = fetch_html(link)
            if article_html:
                article_soup = BeautifulSoup(article_html, 'lxml')
                # Try parsing date from article page if needed or listing date failed
                if not article_date and config.get("date_selector_article"):
                    date_element_article = None
                    for sel in config["date_selector_article"].split(','):
                        date_element_article = article_soup.select_one(sel.strip())
                        if date_element_article: break

                    if date_element_article:
                        date_str_article = safe_get_attr(date_element_article, 'datetime') or \
                                           safe_get_attr(date_element_article, 'content') or \
                                           safe_get_text(date_element_article)
                        parsed_page_date = parse_date(date_str_article, f"{site_name} (Article)")
                        if parsed_page_date:
                            article_date = parsed_page_date # Update date if found on page
            else:
                 print(f"[{site_name}] Could not fetch article page {link} for details.")
                 # Use listing date as fallback if it existed but wasn't today
                 if not article_date and date_str_listing:
                     article_date = parse_date(date_str_listing, f"{site_name} (Listing Fallback)")


        # Process if date matches today
        if article_date == today_date:
            article_info = {
                'title': title,
                'link': link,
                'article_date': article_date,
                'site_name': site_name
            }
            # Pass to the common processing function (which handles content fetching again if needed)
            if _process_article(article_info, config, results_queue):
                matched_count += 1
        # else: # Optional logging
        #     if article_date: print(f"[{site_name}] Skipping HTML (not today: {article_date}): {title[:50]}...")
        #     else: print(f"[{site_name}] Skipping HTML (no date): {title[:50]}...")

    return matched_count


def scrape_website(site_name, config, today_date, results_queue):
    """Main function to scrape a single website, choosing between RSS and HTML."""
    print(f"Scraping {site_name}...")
    results_queue.put(f"--- Starting {site_name} ---")
    processed_links = set() # Keep track of processed links for this site
    matched_articles_count = 0

    try:
        if "rss_feed_url" in config:
            matched_articles_count = _scrape_rss_feed(
                site_name, config, today_date, results_queue, processed_links
            )
        elif "url" in config:
            matched_articles_count = _scrape_html_listing(
                site_name, config, today_date, results_queue, processed_links
            )
        else:
            results_queue.put(f"--- Skipping {site_name}: No 'url' or 'rss_feed_url' in config ---")

    except Exception as e:
        print(f"!!! Unhandled Error scraping {site_name}: {e} !!!")
        traceback.print_exc()
        results_queue.put(f"--- CRITICAL Error during scraping {site_name}: {e} ---")

    print(f"Finished scraping {site_name}. Matched filter: {matched_articles_count} articles.")
    results_queue.put(f"--- Finished {site_name} ({matched_articles_count} matched filter) ---")


# --- GUI Application Class ---
class NewsScraperApp:
    def __init__(self, master):
        self.master = master
        master.title(APP_TITLE)
        master.geometry("900x700")

        # Fonts
        self.bold_font = font.Font(family="Arial", size=10, weight="bold")
        self.normal_font = font.Font(family="Arial", size=10)
        self.log_font = font.Font(family="Courier New", size=9)
        self.sentiment_font = font.Font(family="Arial", size=8, weight="bold")

        # State variables
        self.is_fetching = False
        self.is_saving = False
        self.scraper_threads = []
        self.collected_articles = []
        self.results_queue = queue.Queue()

        # Setup UI
        self._setup_ui()

    def _setup_ui(self):
        """Creates the GUI elements."""
        # Top Control Frame
        control_frame = tk.Frame(self.master, pady=5)
        control_frame.pack(fill=tk.X, padx=10)

        self.fetch_button = tk.Button(control_frame, text="Fetch Today's News", command=self.start_fetching_news, width=20, height=2)
        self.fetch_button.pack(side=tk.LEFT, padx=(0, 10))

        self.status_label = tk.Label(control_frame, text="Status: Idle", fg="blue", font=self.normal_font)
        self.status_label.pack(side=tk.LEFT, padx=10, fill=tk.X, expand=True)

        # Database Control Frame
        db_frame = tk.Frame(self.master, pady=5)
        db_frame.pack(fill=tk.X, padx=10)

        db_label = tk.Label(db_frame, text="Database Path:", font=self.normal_font)
        db_label.pack(side=tk.LEFT, padx=(0, 5))

        self.db_path_var = tk.StringVar(value=DEFAULT_DB_PATH)
        self.db_path_entry = tk.Entry(db_frame, textvariable=self.db_path_var, width=50, font=self.normal_font)
        self.db_path_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        self.save_button = tk.Button(db_frame, text="Save Results", command=self.save_results_action, state=tk.DISABLED)
        self.save_button.pack(side=tk.LEFT, padx=(10, 0))

        # Notebook for Tabs
        self.notebook = ttk.Notebook(self.master)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=(5, 10))

        self.tab_text_widgets = {}

        # Summary Tab
        self._create_tab("Summary", is_log_tab=True)

        # Website Tabs
        for site_name in WEBSITES.keys():
            self._create_tab(site_name)

    def _create_tab(self, tab_name, is_log_tab=False):
        """Helper function to create a tab and its text widget."""
        tab_frame = tk.Frame(self.notebook, bg="#F0F0F0" if is_log_tab else "white")
        tab_frame.pack(fill=tk.BOTH, expand=True)

        widget_font = self.log_font if is_log_tab else self.normal_font
        text_widget = scrolledtext.ScrolledText(
            tab_frame, wrap=tk.WORD, state=tk.DISABLED, font=widget_font,
            padx=5, pady=5, bg=tab_frame["bg"]
        )
        text_widget.pack(fill=tk.BOTH, expand=True)

        if is_log_tab:
            text_widget.tag_configure("error", foreground="red", font=self.log_font)
            text_widget.tag_configure("info", foreground="blue", font=self.log_font)
            text_widget.tag_configure("success", foreground="green", font=self.log_font)
            text_widget.config(state=tk.NORMAL)
            text_widget.insert('1.0', "Scraping log will appear here...\n\n", "info")
            text_widget.config(state=tk.DISABLED)
        else:
            # Configure tags for article display
            text_widget.tag_configure("title", font=self.bold_font, foreground="#00008B")
            text_widget.tag_configure("source_info", foreground="#555555", font=("Arial", 8))
            text_widget.tag_configure("date_info", foreground="#006400", font=("Arial", 8))
            text_widget.tag_configure("url_info", foreground="blue", underline=True, font=("Arial", 8))
            text_widget.tag_configure("content", font=self.normal_font)
            text_widget.tag_configure("separator", foreground="gray")
            text_widget.tag_configure("sentiment_pos", foreground="dark green", font=self.sentiment_font)
            text_widget.tag_configure("sentiment_neg", foreground="red", font=self.sentiment_font)
            text_widget.tag_configure("sentiment_neu", foreground="dark orange", font=self.sentiment_font)
            text_widget.tag_configure("sentiment_err", foreground="purple", font=self.sentiment_font)
            text_widget.tag_bind("url_info", "<Button-1>", self.open_url)

        self.notebook.add(tab_frame, text=tab_name)
        self.tab_text_widgets[tab_name] = text_widget

    def open_url(self, event):
        """Callback to open URL when clicked in a text widget."""
        widget = event.widget
        index = widget.index(f"@{event.x},{event.y}")
        tags = widget.tag_names(index)

        if "url_info" in tags:
            # Find the exact range of the tag at the clicked position
            tag_range = widget.tag_ranges("url_info")
            url = None
            for i in range(0, len(tag_range), 2):
                start, end = tag_range[i], tag_range[i+1]
                if widget.compare(index, ">=", start) and widget.compare(index, "<", end):
                    url = widget.get(start, end)
                    break
            if url:
                try:
                    print(f"Opening URL: {url}")
                    webbrowser.open(url)
                except Exception as e:
                    print(f"Failed to open URL {url}: {e}")
                    messagebox.showerror("Error", f"Could not open URL:\n{url}\n\n{e}")
            else:
                 print("Could not extract URL from tag range.")

    def update_status(self, message, color="blue"):
        """Safely updates the status label from any thread."""
        self.master.after(0, lambda: self.status_label.config(text=f"Status: {message}", fg=color))

    def display_result(self, result):
        """Displays a result (article dict or log string) in the appropriate tab."""
        target_widget = None
        is_log_message = False
        log_tag = "info"

        if isinstance(result, dict) and 'source' in result:
            source = result['source']
            target_widget = self.tab_text_widgets.get(source)
            if target_widget:
                self.collected_articles.append(result) # Store valid articles for saving
            else:
                print(f"Error: No tab found for source '{source}'. Discarding article.")
                return
        elif isinstance(result, str) and "---" in result:
            target_widget = self.tab_text_widgets.get("Summary")
            is_log_message = True
            if not target_widget:
                print(f"Error: Summary tab widget not found. Discarding log: {result}")
                return
            # Determine log tag based on content
            if "Error" in result or "Failed" in result: log_tag = "error"
            elif "Finished" in result and "0 matched" not in result: log_tag = "success"
            else: log_tag = "info"
        else:
            print(f"Received unknown result type: {type(result)}. Discarding.")
            return

        # Schedule GUI update in the main thread
        self.master.after(0, self._update_widget_content, target_widget, result, is_log_message, log_tag)

    def _update_widget_content(self, widget, content_data, is_log, log_tag_type):
        """Helper function to perform the actual text widget update (runs in main thread)."""
        if not widget: return
        try:
            widget.config(state=tk.NORMAL)
            if is_log:
                timestamp = datetime.now().strftime("%H:%M:%S")
                widget.insert(tk.END, f"{timestamp} - {content_data}\n", log_tag_type)
            elif isinstance(content_data, dict):
                # Format and insert article data
                widget.insert(tk.END, f"{content_data['title']}\n", "title")
                widget.insert(tk.END, f"Source: {content_data['source']} | ", "source_info")
                widget.insert(tk.END, f"Date: {content_data['date']} | ", "date_info")

                # Format sentiment
                sentiment = content_data.get("sentiment", "N/A")
                sentiment_tag = {
                    "Positive": "sentiment_pos", "Negative": "sentiment_neg",
                    "Neutral": "sentiment_neu"
                }.get(sentiment, "sentiment_err") # Default to error tag

                widget.insert(tk.END, f"Sentiment: {sentiment}", sentiment_tag)
                widget.insert(tk.END, " | ")

                # Insert clickable URL
                url_start = widget.index(tk.INSERT)
                widget.insert(tk.INSERT, f"{content_data['url']}")
                url_end = widget.index(tk.INSERT)
                widget.tag_add("url_info", url_start, url_end)
                widget.insert(tk.END, "\n")

                # Insert content and separator
                widget.insert(tk.END, f"{content_data['content']}\n\n", "content")
                widget.insert(tk.END, "-" * 60 + "\n\n", "separator")

            widget.see(tk.END) # Scroll to the end
            widget.config(state=tk.DISABLED)
        except tk.TclError as e:
             print(f"Tkinter Error updating widget: {e}") # Handle cases where widget might be destroyed
        except Exception as e:
             print(f"Unexpected error updating widget: {e}")
             traceback.print_exc()


    def process_queue(self):
        """Processes results from the queue and updates the GUI."""
        try:
            while True: # Process all available items
                result = self.results_queue.get_nowait()
                self.display_result(result)
                self.master.update_idletasks() # Allow GUI to refresh between items
        except queue.Empty:
            # Queue is empty, check if scraping is done
            still_fetching = self.is_fetching or any(t.is_alive() for t in self.scraper_threads if t is not None)
            if still_fetching:
                self.master.after(100, self.process_queue) # Check again later
            else:
                # Fetching is false AND all threads are done
                self.update_status("Finished Fetching.", "green")
                self.master.after(0, lambda: self.fetch_button.config(state=tk.NORMAL))
                if self.collected_articles: # Enable save only if there's something to save
                    self.master.after(0, lambda: self.save_button.config(state=tk.NORMAL))
                print("Queue empty and all scraping threads finished.")
                self._add_summary_log("=== All scraping finished ===", "success")

    def fetch_news_thread_runner(self):
        """Runs the scraping process in background threads."""
        self.is_fetching = True
        self.scraper_threads = []
        self.collected_articles = [] # Clear previous results
        today = date.today()

        # Update GUI elements (safely from main thread)
        self.master.after(0, lambda: self.save_button.config(state=tk.DISABLED))
        self._clear_results()
        self.update_status("Fetching...", "orange")
        self._add_summary_log("--- Starting news fetch ---", "info")

        # Start a thread for each website
        for site_name, config in WEBSITES.items():
            thread = threading.Thread(target=scrape_website, args=(site_name, config, today, self.results_queue), daemon=True)
            self.scraper_threads.append(thread)
            thread.start()
            time.sleep(0.05) # Slight stagger

        # Start a monitor thread to wait for all scraping threads to finish
        monitor_thread = threading.Thread(target=self.wait_for_threads, args=(self.scraper_threads,), daemon=True)
        monitor_thread.start()

        # Start polling the results queue
        self.master.after(100, self.process_queue)

    def wait_for_threads(self, threads):
        """Waits for all provided threads to complete."""
        print(f"Monitoring {len(threads)} scraping threads...")
        for i, t in enumerate(threads):
            if t: t.join()
        print("All scraping threads have joined.")
        self.is_fetching = False
        # Trigger a final queue check from the main thread
        self.master.after(10, self.process_queue)

    def _clear_results(self):
        """Safely clears all result text widgets."""
        def _do_clear():
            for name, text_widget in self.tab_text_widgets.items():
                try:
                    text_widget.config(state=tk.NORMAL)
                    text_widget.delete('1.0', tk.END)
                    if name == "Summary": # Reset summary log message
                        text_widget.insert('1.0', "Scraping log will appear here...\n\n", "info")
                    text_widget.config(state=tk.DISABLED)
                except tk.TclError: pass # Ignore if widget is already destroyed
        self.master.after(0, _do_clear)

    def _add_summary_log(self, message, tag):
        """Safely adds a timestamped message to the summary log."""
        self.master.after(0, self._update_widget_content, self.tab_text_widgets.get("Summary"), message, True, tag)

    def start_fetching_news(self):
        """Starts the news fetching process if not already running."""
        if not google_api_key_configured:
             messagebox.showerror("API Key Error", "Google API Key not configured. Sentiment analysis disabled.")
             # Allow fetching without sentiment if desired, or return here
             # return

        if self.is_fetching:
            messagebox.showwarning("Busy", "Already fetching news. Please wait.")
            return
        if self.is_saving:
             messagebox.showwarning("Busy", "Currently saving results. Please wait.")
             return

        self.fetch_button.config(state=tk.DISABLED)
        self.save_button.config(state=tk.DISABLED)
        self.update_status("Starting Fetch...", "orange")

        # Run the fetching process in a separate thread to keep GUI responsive
        fetch_thread = threading.Thread(target=self.fetch_news_thread_runner, daemon=True)
        fetch_thread.start()

    def save_results_action(self):
        """Handles the 'Save Results' button click and starts the save thread."""
        if self.is_fetching:
            messagebox.showwarning("Busy", "Cannot save while fetching. Please wait.")
            return
        if self.is_saving:
            messagebox.showwarning("Busy", "Already saving results.")
            return
        if not self.collected_articles:
            messagebox.showinfo("No Results", "No articles have been collected to save.")
            return

        db_path = self.db_path_var.get().strip()
        if not db_path:
            messagebox.showerror("Input Error", "Please enter a valid database file path.")
            return

        if not messagebox.askyesno("Confirm Save", f"Save {len(self.collected_articles)} collected articles to '{db_path}'?"):
            return

        self.is_saving = True
        self.save_button.config(state=tk.DISABLED)
        self.fetch_button.config(state=tk.DISABLED)
        self.update_status(f"Saving to {db_path}...", "orange")
        self._add_summary_log(f"--- Starting database save to {db_path} ---", "info")

        # Pass a copy of the articles list to the save thread
        articles_to_save = list(self.collected_articles)
        save_thread = threading.Thread(target=self.save_results_thread_runner, args=(db_path, articles_to_save), daemon=True)
        save_thread.start()

    def save_results_thread_runner(self, db_path, articles):
        """Performs database saving in a background thread and updates GUI on completion."""
        start_time = time.time()
        inserted_count, ignored_count, error_count = 0, 0, 0

        if not init_db(db_path):
            # Error already shown by init_db, just update status
            self.master.after(0, lambda: self.update_status("Database Initialization Failed!", "red"))
            self.master.after(0, lambda: self._add_summary_log("--- Database save failed (init error) ---", "error"))
            self.is_saving = False
            # Re-enable buttons if not fetching
            if not self.is_fetching:
                 self.master.after(0, lambda: self.fetch_button.config(state=tk.NORMAL))
                 self.master.after(0, lambda: self.save_button.config(state=tk.NORMAL if self.collected_articles else tk.DISABLED))
            return

        # Insert articles one by one (handles INSERT OR IGNORE easily)
        for i, article in enumerate(articles):
            result_id = insert_article(db_path, article)
            if result_id is None: error_count += 1
            elif result_id > 0: inserted_count += 1
            else: ignored_count += 1

            # Optional periodic status update for large saves
            if (i + 1) % 50 == 0:
                 progress_msg = f"Saving... ({i+1}/{len(articles)})"
                 self.master.after(0, lambda msg=progress_msg: self.update_status(msg, "orange"))

        duration = time.time() - start_time

        # Final GUI update after saving is complete
        def _final_update():
            if error_count > 0:
                final_message = f"Save finished with {error_count} errors."
                final_color = "red"
                messagebox.showerror("Save Error", f"Finished saving with {error_count} errors.\nInserted: {inserted_count}, Ignored (duplicates): {ignored_count}\nCheck summary log.")
            else:
                final_message = f"Saved {inserted_count} new articles."
                final_color = "green"
                messagebox.showinfo("Save Complete", f"Successfully saved results to '{db_path}'.\nInserted: {inserted_count}\nIgnored (duplicates): {ignored_count}\nDuration: {duration:.2f}s")

            self.update_status(final_message, final_color)
            log_msg = f"--- Database save finished: Inserted={inserted_count}, Ignored={ignored_count}, Errors={error_count}, Duration={duration:.2f}s ---"
            log_tag = "error" if error_count > 0 else "success"
            self._add_summary_log(log_msg, log_tag)

            self.is_saving = False
            # Re-enable buttons if not fetching
            if not self.is_fetching:
                 self.fetch_button.config(state=tk.NORMAL)
                 # Keep save enabled if there were results originally
                 self.save_button.config(state=tk.NORMAL if self.collected_articles else tk.DISABLED)

        self.master.after(0, _final_update)


# --- Main Execution ---
if __name__ == "__main__":
    root = tk.Tk()

    # Apply a modern theme if available
    style = ttk.Style()
    try:
        available_themes = style.theme_names()
        print(f"Available ttk themes: {available_themes}")
        # Prefer 'clam' on non-Windows, 'vista' on Windows
        theme_to_use = 'clam'
        if os.name == 'nt' and 'vista' in available_themes:
            theme_to_use = 'vista'
        elif 'clam' not in available_themes and available_themes:
             theme_to_use = available_themes[0] # Fallback to first available

        if theme_to_use in available_themes:
            style.theme_use(theme_to_use)
            print(f"Using ttk theme: '{theme_to_use}'")
        else:
            print(f"Theme '{theme_to_use}' not available, using default Tk theme.")
    except Exception as e:
        print(f"Error setting ttk theme: {e}. Using default Tk theme.")

    app = NewsScraperApp(root)
    root.mainloop()
