from flask import Flask, render_template, request
import requests
import base64
import os
import whois
import tweepy
from dotenv import load_dotenv
from urllib.parse import urlparse

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# Retrieve API keys from environment variables
API_KEY = os.getenv('VIRUSTOTAL_API_KEY')
TWITTER_BEARER_TOKEN = os.getenv('TWITTER_BEARER_TOKEN')
SCREENSHOT_API_KEY = os.getenv('SCREENSHOT_API_KEY')

if not API_KEY:
    raise ValueError("VirusTotal API key is not set in environment variables.")
if not TWITTER_BEARER_TOKEN:
    raise ValueError("Twitter Bearer Token is not set in environment variables.")
if not SCREENSHOT_API_KEY:
    raise ValueError("Screenshot API key is not set in environment variables.")

VT_URL = 'https://www.virustotal.com/api/v3/urls'
SCREENSHOT_URL = 'https://api.screenshotapi.net/screenshot'

def normalize_url(url):
    """Remove the protocol from the URL if it exists."""
    if '://' in url:
        return url.split('://', 1)[-1]
    return url

def get_virus_total_report(url):
    headers = {'x-apikey': API_KEY}
    normalized_url = normalize_url(url)
    url_to_encode = urlparse(normalized_url).netloc + urlparse(normalized_url).path
    if not url_to_encode:
        return {'error': 'Invalid URL format.'}
    
    url_id = base64.urlsafe_b64encode(url_to_encode.encode('utf-8')).decode('utf-8').rstrip('=')
    
    try:
        response = requests.get(f'{VT_URL}/{url_id}', headers=headers)
        data = response.json()
        
        if 'error' in data:
            error_message = data['error'].get('message', 'Unknown error occurred')
            return {'error': error_message}
        
        attributes = data.get('data', {}).get('attributes', {})
        stats = attributes.get('last_analysis_stats', {})
        malicious_count = stats.get('malicious', 0)
        total_scans = stats.get('total', 0)
        scan_results = attributes.get('last_analysis_results', {})
        categories = attributes.get('categories', {})

        top_malicious_vendors = {vendor: info['result'] for vendor, info in sorted(scan_results.items(), key=lambda x: x[1]['result'] == 'malicious', reverse=True)[:10]}
        
        community_comments = attributes.get('community_reviews', [])
        if not community_comments:
            community_comments = ['No community reviews available']
        
        relations = attributes.get('relations', {})
        subdomains = relations.get('subdomains', [])
        urls = relations.get('urls', [])
        communicating_files = relations.get('communicating_files', [])
        
        if not subdomains:
            subdomains = ['No subdomains found']
        if not urls:
            urls = ['No URLs found']
        if not communicating_files:
            communicating_files = ['No communicating files found']
        
        suggested_category = categories.get('suggested', 'N/A')
        all_categories = ', '.join(f'{key}: {value}' for key, value in categories.items())
        
        return {
            'url': normalized_url,
            'malicious_count': malicious_count,
            'total_scans': total_scans,
            'vendor_analysis': top_malicious_vendors,
            'community_comments': community_comments,
            'subdomains': subdomains,
            'urls': urls,
            'communicating_files': communicating_files,
            'suggested_category': suggested_category,
            'all_categories': all_categories
        }
    
    except Exception as e:
        return {'error': f"Error fetching VirusTotal report: {str(e)}"}

def get_screenshot(url):
    try:
        params = {
            'key': SCREENSHOT_API_KEY,
            'url': url,
            'output': 'json',
            'fresh': 'true'
        }
        response = requests.get(SCREENSHOT_URL, params=params)
        data = response.json()
        screenshot_url = data.get('screenshot', {}).get('url', '')
        return screenshot_url if screenshot_url else 'No screenshot available'
    except Exception as e:
        return f"Error fetching screenshot: {str(e)}"

def get_whois_info(domain):
    try:
        domain_info = whois.whois(domain)
        result = {
            'domain': domain,
            'registrar': domain_info.registrar,
            'creation_date': domain_info.creation_date,
            'expiration_date': domain_info.expiration_date,
            'name_servers': domain_info.name_servers,
            'org': domain_info.get('org', 'N/A'),
            'state': domain_info.get('state', 'N/A'),
            'country': domain_info.get('country', 'N/A')
        }
        return result
    except Exception as e:
        return {'error': f"Error fetching WHOIS information: {str(e)}"}

def search_twitter(query):
    try:
        client = tweepy.Client(bearer_token=TWITTER_BEARER_TOKEN)
        tweets = client.search_recent_tweets(query=query, max_results=5)
        tweet_texts = [tweet.text for tweet in tweets.data] if tweets.data else ['No recent tweets found']
        return tweet_texts
    except Exception as e:
        return [f"Error fetching Twitter data: {str(e)}"]

@app.route('/', methods=['GET', 'POST'])
def index():
    result = None
    whois_result = None
    screenshot_url = None
    urlscan_url = None
    google_url = None
    twitter_url = None
    tweets = None
    proxy_url = None

    if request.method == 'POST':
        url = request.form.get('url')
        
        if url:
            try:
                # Get VirusTotal report for the original URL
                result = get_virus_total_report(url)
                
                # Extract domain and get Whois info using the original URL
                parsed_url = urlparse(url)
                domain = parsed_url.netloc or parsed_url.path
                if not domain:
                    raise ValueError("Invalid URL format.")
                whois_result = get_whois_info(domain)

                # Get screenshot of the URL
                screenshot_url = get_screenshot(url)

                # Construct URLScan.io search URL
                urlscan_url = f'https://urlscan.io/search/#{normalize_url(url)}'
                
                # Normalize the query by removing protocol if present
                normalized_query = normalize_url(url)

                # Construct Google and Twitter search URLs
                google_url = f'https://www.google.com/search?q={normalized_query}'
                twitter_url = f'https://twitter.com/search?q={normalized_query}'
                
                # Search Twitter
                tweets = search_twitter(normalized_query)

            except Exception as e:
                result = {'error': str(e)}
    
    if request.method == 'GET' and request.args.get('url'):
        proxy_url = request.args.get('url')
    
    return render_template('index.html', result=result, whois_result=whois_result, screenshot_url=screenshot_url, urlscan_url=urlscan_url, google_url=google_url, twitter_url=twitter_url, tweets=tweets, proxy_url=proxy_url)

if __name__ == '__main__':
    app.run(debug=True)
