# -*- coding: utf-8 -*-

import configparser
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import pandas as pd
import time
from bs4 import BeautifulSoup
import re
import logging

# Logging einrichten
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')


def load_config():
    config = configparser.ConfigParser()
    config.read('config.ini')
    return config['Settings']


def get_ads(driver):
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, 'li.ad-listitem')))
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

        # Numerischen Preis extrahieren
        price_match = re.search(
            r'(\d[\d.]*\d)', price_text.replace('.', '').replace(' €', '').replace('VB', '').strip())
        price = int(price_match.group(0)) if price_match else 0

        location_element = ad.find('div', class_='aditem-main--top--left')
        location = location_element.text.strip() if location_element else 'N/A'

        url_element = ad.find('a', class_='ellipsis')
        url = f"https://www.kleinanzeigen.de{url_element['href']}" if url_element else 'N/A'

        ads.append({
            'Fahrzeug': title,
            'Price': price,
            'Location': location,
            'URL': url
        })
    return ads


def get_ad_details(driver, url):
    try:
        driver.get(url)
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, 'viewad-title')))
        soup = BeautifulSoup(driver.page_source, 'html.parser')

        adid = url.split('/')[-1].split('-')[0]
        title_element = soup.find('h1', id='viewad-title')
        title = title_element.text.strip() if title_element else 'N/A'

        # "Reserviert" und "Gelöscht" aus dem Titel entfernen
        title = title.replace("Reserviert – ", "").replace("Gelöscht – ", "")

        price_element = soup.find('h2', id='viewad-price')
        price = price_element.text.strip() if price_element else 'N/A'

        description_element = soup.find('p', id='viewad-description-text')
        description = description_element.decode_contents().replace(
            '<br>', '\n').strip() if description_element else 'N/A'

        image_elements = soup.find_all('img', id='viewad-image')
        image_urls = [img['src'] for img in image_elements]

        detail_elements = soup.find_all('li', class_='addetailslist--detail')
        details = [detail.find(
            'span', class_='addetailslist--detail--value').text.strip() for detail in detail_elements]

        location_element = soup.find('span', id='viewad-locality')
        location = location_element.text.strip() if location_element else 'N/A'

        date_element = soup.find(
            'div', id='viewad-extra-info').find_all('div')[0].find('span')
        date = date_element.text.strip() if date_element else 'N/A'

        # Datenwörterbuch für CSV-Zeile vorbereiten
        ad_details = {
            'title': adid,
            'Fahrzeug': title,
            'description': description,
            'price': price,
            'location': location,
            'date': date,
            'image_url': image_urls[0] if image_urls else 'N/A',
            'image_alt': title
        }
        for i, url in enumerate(image_urls):
            ad_details[f'image_url_{i+1}'] = url

        for i, detail in enumerate(details):
            ad_details[f'detail{i+1}'] = detail

        return ad_details
    except Exception as e:
        logging.error(
            f"Fehler beim Abrufen der Anzeigedetails für URL {url}: {e}")
        return {}


def save_to_csv(ads, filename='Hoppe_Camper_Anzeigen.csv'):
    df = pd.DataFrame(ads)
    df.to_csv(filename, index=False)


def close_gdpr_banner(driver):
    try:
        # GDPR-Banner schließen, falls vorhanden
        gdpr_button_selectors = [
            (By.ID, "gdpr-banner-accept"),
            (By.CSS_SELECTOR, "[data-testid='gdpr-banner-accept']"),
            (By.XPATH,
             "//button[@aria-label='Datenschutzbestimmungen und Einstellungen akzeptieren']"),
            (By.XPATH, "//*[@id='gdpr-banner-accept']"),
            (By.XPATH, "//*[@data-testid='gdpr-banner-accept']")
        ]

        for method, selector in gdpr_button_selectors:
            try:
                gdpr_banner = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((method, selector)))
                gdpr_banner.click()
                time.sleep(2)  # Warten, bis das Banner geschlossen ist
                logging.info("GDPR-Banner geschlossen.")
                return
            except Exception:
                pass  # Nächsten Selektor ausprobieren

        logging.info("Kein GDPR-Banner gefunden oder Fehler beim Schließen.")
    except Exception as e:
        logging.error(
            f"Unerwarteter Fehler beim Schließen des GDPR-Banners: {e}")


def navigate_to_next_page(driver, current_page):
    try:
        next_page_button = driver.find_element(
            By.XPATH, f"//button[@class='jsx-2946000297 Page' and text()='{current_page + 1}']")
        next_page_button.click()
        time.sleep(5)  # Warten, bis die neue Seite geladen ist
        return True
    except Exception as e:
        logging.error(f"Fehler beim Navigieren zur nächsten Seite: {e}")
        return False

def main():
    config = load_config()
    base_url = config.get('base_url')
    page_start = int(config.get('page_start'))
    page_end = int(config.get('page_end'))
    price_filter = int(config.get('preis'))

    logging.info(f"Basis-URL: {base_url}")
    logging.info(f"Seitenstart: {page_start}, Seitenende: {page_end}")
    logging.info(f"Preisfilter: {price_filter}")

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
                if not navigate_to_next_page(driver, current_page):
                    break  # Abbrechen, wenn kein Weiter-Button vorhanden ist oder die Navigation fehlschlägt

            current_page += 1

        # Anzeigen filtern mit Preis >= price_filter und deren Details abrufen
        ads_over_price = [ad for ad in ads if ad['Price'] >= price_filter]
        detailed_ads = []
        for ad in ads_over_price:
            ad_details = get_ad_details(driver, ad['URL'])
            if ad_details:
                detailed_ads.append(ad_details)

    finally:
        driver.quit()

    save_to_csv(detailed_ads)
    logging.info(
        f"Scraping abgeschlossen. {len(detailed_ads)} Anzeigen in CSV gespeichert.")
    print("Das Skript wurde erfolgreich ausgeführt.")

if __name__ == '__main__':
    main()