import configparser
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import pandas as pd
import time
from bs4 import BeautifulSoup
import re


def load_config():
    config = configparser.ConfigParser()
    config.read('config.ini')
    return config['Settings']


def get_ads(driver):
    time.sleep(5)  # Wait for the page to load
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    return soup


def parse_ads(soup):
    ad_list = soup.find_all('li', class_='ad-listitem')
    ads = []
    for ad in ad_list:
        title_element = ad.find('div', class_='Title Title-h3')
        title = title_element.text.strip() if title_element else 'N/A'

        price_element = ad.find('p', class_='aditem-main--middle--price')
        price_text = price_element.text.strip() if price_element else 'N/A'

        # Extract numeric price
        price_match = re.search(
            r'(\d[\d.]*\d)', price_text.replace('.', '').replace(' €', '').replace('VB', '').strip())
        price = int(price_match.group(0)) if price_match else 0

        location_element = ad.find('div', class_='aditem-main--top--left')
        location = location_element.text.strip() if location_element else 'N/A'

        url_element = ad.find('a', class_='ellipsis')
        url = f"https://www.kleinanzeigen.de{url_element['href']}" if url_element else 'N/A'

        ads.append({
            'Title': title,
            'Price': price,
            'Location': location,
            'URL': url
        })
    return ads


def get_ad_details(driver, url):
    driver.get(url)
    time.sleep(5)  # Wait for the page to load
    soup = BeautifulSoup(driver.page_source, 'html.parser')

    adid = url.split('/')[-1].split('-')[0]
    title_element = soup.find('h1', id='viewad-title')
    title = title_element.text.strip() if title_element else 'N/A'

    # Remove "Reserviert" and "Gelöscht" from title
    title = title.replace("Reserviert • ", "").replace("Gelöscht • ", "")

    price_element = soup.find('h2', id='viewad-price')
    price = price_element.text.strip() if price_element else 'N/A'

    description_element = soup.find('p', id='viewad-description-text')
    description = description_element.text.strip() if description_element else 'N/A'

    image_elements = soup.find_all('img', id='viewad-image')
    image_urls = [img['src'] for img in image_elements]

    detail_elements = soup.find_all('li', class_='addetailslist--detail')
    details = [detail.text.strip() for detail in detail_elements]

    # Prepare data dictionary for CSV row
    ad_details = {
        'adid': adid,
        'title': title,
        'description': description,
        'price': price,
        'location': 'N/A',  # Assume location is not needed in the detailed view
        'date': 'N/A',  # Assume date is not directly available in the detailed view
        'image_url': image_urls[0] if image_urls else 'N/A',
        'image_alt': title
    }
    for i, url in enumerate(image_urls):
        ad_details[f'image_url_{i+1}'] = url

    for i, detail in enumerate(details):
        ad_details[f'detail{i+1}'] = detail

    return ad_details


def save_to_csv(ads, filename='ads_over_30000.csv'):
    df = pd.DataFrame(ads)
    df.to_csv(filename, index=False)


def close_gdpr_banner(driver):
    try:
        # Close GDPR banner if present
        possible_selectors = [
            "gdpr-banner-accept",
            "gdpr-accept",  # Add other possible IDs or classes here
        ]
        for selector in possible_selectors:
            try:
                gdpr_banner = driver.find_element(By.ID, selector)
                gdpr_banner.click()
                time.sleep(2)  # Wait for the banner to close
                return
            except Exception:
                continue
        print("No GDPR banner found or error closing it.")
    except Exception as e:
        print(f"Unexpected error while closing GDPR banner: {e}")


def main():
    config = load_config()
    base_url = 'https://www.kleinanzeigen.de/pro/Hoppe-Camper-Fahrzeughandel-GmbH'
    page_start = int(config.get('page_start'))
    page_end = int(config.get('page_end'))
    price_filter = int(config.get('preis'))

    ads = []

    options = Options()
    options.headless = True
    driver = webdriver.Chrome(service=Service(
        ChromeDriverManager().install()), options=options)

    try:
        driver.get(base_url)
        close_gdpr_banner(driver)

        current_page = page_start
        while current_page <= page_end:
            soup = get_ads(driver)
            ads_on_page = parse_ads(soup)
            ads.extend(ads_on_page)

            if current_page < page_end:
                # Try to find and click the "Nächste" button
                try:
                    next_button = driver.find_element(
                        By.XPATH, '//button[@title="Nächste"]')
                    if 'isDisabled' in next_button.get_attribute('class'):
                        break  # If the button is disabled, we are on the last page
                    next_button.click()
                    time.sleep(2)  # Wait for the next page to load
                except Exception as e:
                    print(f"Error finding or clicking the next button: {e}")
                    break

            current_page += 1

        # Filter ads with price >= price_filter and get their details
        ads_over_price = [ad for ad in ads if ad['Price'] >= price_filter]
        detailed_ads = []
        for ad in ads_over_price:
            ad_details = get_ad_details(driver, ad['URL'])
            detailed_ads.append(ad_details)

    finally:
        driver.quit()

    save_to_csv(detailed_ads)


if __name__ == '__main__':
    main()
