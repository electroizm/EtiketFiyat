"""
DOGTAS SCRAPER - COMBINED VERSION
- Ana Doğtaş sitesini scrape eder (tüm sayfalar)
- Other.xlsx'ten SKU okur ve sitemap XML'lerinde arar
- Async yapı (concurrent=1/2)
- Gelişmiş selector fallback
- Veri validasyonu
- Adaptive retry logic
- Filtreleme kuralları
- Excel export
"""
import sys
import os
import asyncio
import aiohttp
from bs4 import BeautifulSoup
import json
import time
import re
from datetime import datetime
from urllib.parse import urljoin
import pandas as pd
from typing import List, Optional, Dict
from pathlib import Path
import logging
import xml.etree.ElementTree as ET


def get_base_dir():
    """Exe veya script dizinini döndür"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def setup_logger(log_dir=None):
    if log_dir is None:
        log_dir = get_base_dir()
    """Logger'i yapılandır - eski logları temizle"""
    log_path = Path(log_dir) / "dogtasCom.log"

    # Eski log dosyasını sil
    if log_path.exists():
        log_path.unlink()

    # Logger yapılandır
    logger = logging.getLogger('DogtasScraper')
    logger.setLevel(logging.INFO)

    # Dosya handler (sadece dosyaya yaz, konsola yazma)
    file_handler = logging.FileHandler(log_path, mode='w', encoding='utf-8')
    file_handler.setLevel(logging.INFO)

    # Format
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s',
                                  datefmt='%Y-%m-%d %H:%M:%S')
    file_handler.setFormatter(formatter)

    # Handler ekle
    logger.addHandler(file_handler)

    return logger


# Global logger
logger = None


class DataValidator:
    """Urun verilerini validate ve temizle"""

    @staticmethod
    def clean_price(price_text: str) -> Optional[float]:
        """
        Fiyat textini temizle ve float'a cevir

        Ornekler:
        "12.500 TL" -> 12500.0
        "12.500,50 TL" -> 12500.50
        """
        if not price_text:
            return None

        try:
            # TL, para birimi sembolleri vs temizle
            clean_text = re.sub(r'[^\d.,]', '', price_text)

            if not clean_text:
                return None

            # Turkce format (12.500,50) -> (12500.50)
            if ',' in clean_text and '.' in clean_text:
                # Nokta binlik ayracsa, virgul ondaliksa
                if clean_text.rindex('.') < clean_text.rindex(','):
                    clean_text = clean_text.replace('.', '').replace(',', '.')
                else:
                    # Virgul binlik ayracsa, nokta ondaliksa
                    clean_text = clean_text.replace(',', '')
            elif ',' in clean_text:
                # Sadece virgul var - ondalik ayrac olarak kabul et
                clean_text = clean_text.replace(',', '.')
            elif '.' in clean_text:
                # Sadece nokta var - binlik mi ondalik mi kontrol et
                parts = clean_text.split('.')
                if len(parts[-1]) == 2:  # Son kısım 2 basamaksa ondalik
                    pass  # Degistirme
                else:  # Binlik ayrac
                    clean_text = clean_text.replace('.', '')

            price = float(clean_text)

            # Makul aralık kontrolu (10 TL - 1.000.000 TL)
            if 10 <= price <= 1_000_000:
                return price
            else:
                print(f"[WARNING] Fiyat aralik disi: {price}")
                return None

        except (ValueError, AttributeError) as e:
            print(f"[WARNING] Fiyat parse hatasi: {price_text}")
            return None

    @staticmethod
    def clean_sku(sku_text: str) -> Optional[str]:
        """SKU temizle ve validate et"""
        if not sku_text:
            return None

        # Sadece rakam ve harf (tire, alt cizgi vs birak)
        sku = re.sub(r'[^A-Za-z0-9\-_]', '', sku_text.strip())

        # En az 3 karakter olmali
        if len(sku) >= 3:
            return sku
        else:
            return None

    @staticmethod
    def clean_discount_percent(discount_text: str) -> Optional[int]:
        """
        Indirim yuzdesi cek

        Ornekler:
        "%50" -> 50
        "% 30 İndirim" -> 30
        """
        if not discount_text:
            return None

        # Yuzde sembolu veya "yuzde" kelimesi ile rakam ara
        match = re.search(r'(?:%|yüzde|yuzde)\s*(\d+)', discount_text, re.IGNORECASE)
        if match:
            percent = int(match.group(1))
            if 0 < percent <= 99:
                return percent

        return None

    @staticmethod
    def validate_product_data(data: Dict) -> Dict:
        """Tum urun verisini validate et ve temizle"""
        validated = data.copy()

        # Fiyat validasyonu - INT olarak kaydet
        if validated.get('orijinal_fiyat'):
            price_float = DataValidator.clean_price(validated['orijinal_fiyat'])
            validated['LISTE'] = int(price_float) if price_float else None
        else:
            validated['LISTE'] = None

        if validated.get('fiyat'):
            price_float = DataValidator.clean_price(validated['fiyat'])
            validated['PERAKENDE'] = int(price_float) if price_float else None
        else:
            validated['PERAKENDE'] = None

        # SKU validasyonu
        if validated.get('sku'):
            validated['sku'] = DataValidator.clean_sku(validated['sku'])

        # String alanlari temizle
        for field in ['urun_adi', 'urun_adi_tam', 'KOLEKSIYON', 'kategori']:
            if validated.get(field):
                validated[field] = validated[field].strip()

        # Gereksiz alanlari kaldir
        fields_to_remove = [
            'orijinal_fiyat', 'indirimli_fiyat', 'fiyat',
            'indirim_yuzdesi', 'kazanc', 'kampanya_metni',
            'sepette_indirim', 'marka',
            'orijinal_fiyat_numeric', 'indirimli_fiyat_numeric',
            'fiyat_numeric', 'indirim_yuzdesi_numeric'
        ]
        for field in fields_to_remove:
            validated.pop(field, None)

        return validated


class ProductFilter:
    """Urun filtreleme kurallari"""

    # Bos kategorideki filtrelenecek kelimeler
    FILTER_KEYWORDS = [
        'Abajur', 'Halı', 'Biblo', 'Kırlent', 'Tablo', 'Sarkıt',
        'Çerceve', 'Vazo', 'Mum', 'Obje', 'Küp', 'Saat',
        'Lambader', 'Tabak', 'Şamdan'
    ]

    @staticmethod
    def should_filter_product(product: Dict) -> bool:
        """
        Urunu filtrelemeli miyiz?
        True = Filtrelenmeli (kaydetme)
        False = Kaydet
        """
        kategori = product.get('kategori', '').strip()
        urun_adi = product.get('urun_adi', '').strip()
        urun_adi_tam = product.get('urun_adi_tam', '').strip()

        # Kural 1: Doğtaş Home kategorisini filtrele
        if kategori == "Doğtaş Home":
            print(f"[FILTER] Doğtaş Home kategorisi: {urun_adi_tam}")
            return True

        # Kural 2: Kategori boş ve ürün adı filtreleme kelimelerini içeriyorsa
        if not kategori:
            combined_name = f"{urun_adi} {urun_adi_tam}".lower()
            for keyword in ProductFilter.FILTER_KEYWORDS:
                if keyword.lower() in combined_name:
                    print(f"[FILTER] Boş kategori + {keyword}: {urun_adi_tam}")
                    return True

        return False

    @staticmethod
    def apply_duplication_rules(products: List[Dict]) -> List[Dict]:
        """
        Duplikasyon kurallari uygula

        Kural: Kategori = "Yemek Odası" ve urun_adi "komodin" veya "ayna" içeriyorsa
        -> Aynı ürünü "Yatak Odası" kategorisi ile de ekle
        """
        result = []

        for product in products:
            # Once orijinal urunu ekle
            result.append(product)

            # Duplikasyon kontrolu
            kategori = product.get('kategori', '').strip()
            urun_adi = product.get('urun_adi', '').lower()
            urun_adi_tam = product.get('urun_adi_tam', '').lower()

            # Yemek Odası + (komodin veya ayna) kontrolu
            if kategori == "Yemek Odası":
                if 'komodin' in urun_adi or 'komodin' in urun_adi_tam or \
                   'ayna' in urun_adi or 'ayna' in urun_adi_tam:
                    # Duplike urun olustur
                    duplicated = product.copy()
                    duplicated['kategori'] = "Yatak Odası"
                    result.append(duplicated)
                    print(f"[DUPLICATE] Yemek Odası -> Yatak Odası: {product.get('urun_adi_tam')}")

        return result


def read_other_xlsx(file_path: str) -> List[str]:
    """
    Other.xlsx dosyasından SKU verilerini oku
    İlk sütundaki 10 haneli ve 3 ile başlayan verileri döndür
    """
    try:
        if not os.path.exists(file_path):
            print(f"[WARNING] Other.xlsx bulunamadı: {file_path}")
            return []

        df = pd.read_excel(file_path, engine='openpyxl')

        if df.empty:
            print("[WARNING] Other.xlsx boş")
            return []

        # İlk sütunu al
        first_column = df.iloc[:, 0]

        # SKU listesi
        sku_list = []
        for value in first_column:
            # String'e çevir ve temizle
            sku_str = str(value).strip()

            # 10 haneli ve 3 ile başlayan kontrolü
            if sku_str.isdigit() and len(sku_str) == 10 and sku_str.startswith('3'):
                sku_list.append(sku_str)

        print(f"[OK] Other.xlsx'den {len(sku_list)} SKU okundu")
        return sku_list

    except Exception as e:
        print(f"[ERROR] Other.xlsx okuma hatası: {e}")
        return []


class DogtasAsyncScraper:
    """Gelismis Async Dogtas Scraper"""

    def __init__(self, max_concurrent=1, output_dir=None):
        if output_dir is None:
            output_dir = get_base_dir()
        """
        max_concurrent: Ayni anda kac istek yapilacak
        output_dir: Cikti dosyalarinin kaydedilecegi dizin
        """
        self.base_url = "https://www.dogtas.com"
        self.max_concurrent = max_concurrent
        self.output_dir = Path(output_dir)
        self.semaphore = None

        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        }

        # Config - Daha yavas tarama
        self.config = {
            'initial_timeout': 20,
            'max_timeout': 90,
            'retry_count': 3,
            'backoff_factor': 2,
            'rate_limit_delay': 2,  # Urun arasi bekleme
            'page_delay': 3,  # Sayfa arasi bekleme
        }

    async def get_page_async(self, session: aiohttp.ClientSession, url: str, attempt=1):
        """
        Adaptive timeout ve retry logic ile asenkron sayfa cekme
        """
        max_attempts = self.config['retry_count']
        timeout = self.config['initial_timeout'] * (self.config['backoff_factor'] ** (attempt - 1))
        timeout = min(timeout, self.config['max_timeout'])

        try:
            async with self.semaphore:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
                    response.raise_for_status()
                    html = await response.text()
                    return BeautifulSoup(html, 'html.parser')

        except asyncio.TimeoutError:
            if attempt < max_attempts:
                wait_time = 2 ** attempt
                print(f"[TIMEOUT] Deneme {attempt}/{max_attempts} - Bekleniyor {wait_time}s...")
                await asyncio.sleep(wait_time)
                return await self.get_page_async(session, url, attempt + 1)
            else:
                print(f"[ERROR] Timeout - Maksimum deneme: {url}")
                return None

        except Exception as e:
            if attempt < max_attempts:
                wait_time = attempt * 1.5
                print(f"[ERROR] {e} - Tekrar deneniyor ({attempt}/{max_attempts})...")
                await asyncio.sleep(wait_time)
                return await self.get_page_async(session, url, attempt + 1)
            else:
                print(f"[ERROR] Basarisiz: {url} - {e}")
                return None

    def get_product_links(self, soup: BeautifulSoup) -> List[str]:
        """
        Coklu selector stratejisi ile urun linklerini bul
        """
        if not soup:
            return []

        # Oncelik sirasina gore selector'lar
        selector_strategies = [
            '.carousel-item.active a',
            '.card-product a',
            '.product-card a',
            '.product-item a',
            'div[class*="product"] a',
            'a[href*="dogtas.com"]',
            '[itemtype*="Product"] a',
        ]

        for selector in selector_strategies:
            try:
                links = soup.select(selector)

                # Link'leri filtrele
                valid_links = []
                seen_urls = set()  # Duplike URL'leri onlemek icin

                for link in links:
                    href = link.get('href', '').strip()

                    if not href:
                        continue

                    # Gecersiz linkleri filtrele
                    if any(skip in href.lower() for skip in ['javascript:', '#product-card', 'kategori', 'collection']):
                        continue

                    # Fragment'leri temizle
                    if '#' in href:
                        href = href.split('#')[0]

                    # Tam URL olustur
                    full_url = urljoin(self.base_url, href)

                    # Dogtas.com domain'i olmali
                    if 'dogtas.com' not in full_url:
                        continue

                    # Urun sayfasi olmali (belirli path pattern'leri)
                    # Kategori sayfalari vs haric
                    if any(skip in full_url.lower() for skip in ['/tumu-c-', '/kategori', '/collection', '/sayfa=']):
                        continue

                    # Duplike kontrolu
                    if full_url in seen_urls:
                        continue

                    # Gecerli urun linki
                    valid_links.append(full_url)
                    seen_urls.add(full_url)

                if valid_links:
                    # print(f"[OK] {len(valid_links)} link bulundu (selector: {selector})")
                    return valid_links

            except Exception as e:
                # print(f"[DEBUG] Selector hatasi: {selector} - {e}")
                continue

        print(f"[WARNING] Hic urun linki bulunamadi")
        return []

    def baslik_ayikla(self, baslik_etiketi):
        """Baslik etiketinden koleksiyon adini ve urun adini ayiklar"""
        if not baslik_etiketi:
            return "", ""

        koleksiyon_adi = ""
        span_etiketi = baslik_etiketi.find('span')
        if span_etiketi:
            koleksiyon_adi = span_etiketi.get_text(strip=True)

        urun_adi = ""
        if span_etiketi and span_etiketi.next_sibling:
            urun_adi = span_etiketi.next_sibling.strip()
        elif baslik_etiketi:
            urun_adi = baslik_etiketi.get_text(strip=True)

        return koleksiyon_adi, urun_adi

    async def get_product_detail_async(self, session: aiohttp.ClientSession, url: str):
        """Asenkron urun detay cekme + validasyon"""
        try:
            soup = await self.get_page_async(session, url)
            if not soup:
                return None

            veri = {
                # Temel Bilgiler
                'KOLEKSIYON': "",
                'urun_adi': "",
                'urun_adi_tam': "",
                'sku': "",

                # Fiyat Detaylari
                'orijinal_fiyat': "",
                'indirimli_fiyat': "",
                'fiyat': "",
                'indirim_yuzdesi': "",
                'kazanc': "",
                'kampanya_metni': "",
                'sepette_indirim': "",

                # Kategori
                'kategori': "",

                # Marka
                'marka': "",

                # URL
                'urun_url': url
            }

            # Baslik
            baslik_etiketi = soup.find('h1', class_='title')
            veri['KOLEKSIYON'], veri['urun_adi'] = self.baslik_ayikla(baslik_etiketi)

            # Tam urun adi olustur
            if veri['KOLEKSIYON'] and veri['urun_adi']:
                veri['urun_adi_tam'] = f"{veri['KOLEKSIYON']} {veri['urun_adi']}"
            else:
                veri['urun_adi_tam'] = veri['urun_adi']

            # Eger sadece koleksiyon varsa ve urun adi yoksa, None don
            if veri['KOLEKSIYON'] and not veri['urun_adi']:
                return None

            # SKU
            sku_etiketi = soup.find(class_='sku')
            if sku_etiketi:
                sku_metni = sku_etiketi.get_text(strip=True)
                sku_eslesme = re.search(r'(\d+)', sku_metni)
                veri['sku'] = sku_eslesme.group(1) if sku_eslesme else ""

            # Kategori (breadcrumb)
            breadcrumb_elem = soup.find('ol', class_='breadcrumb')
            if breadcrumb_elem:
                breadcrumb_items = []
                for li in breadcrumb_elem.find_all('li'):
                    text = li.get_text(strip=True)
                    if text and text not in ['Ana Sayfa', 'Home']:
                        breadcrumb_items.append(text)

                if len(breadcrumb_items) >= 1:
                    veri['kategori'] = breadcrumb_items[0]

            # Marka (JSON-LD)
            json_ld_scripts = soup.find_all('script', type='application/ld+json')
            for script in json_ld_scripts:
                try:
                    data = json.loads(script.string)
                    if data.get('@type') == 'Product':
                        if 'brand' in data:
                            brand_info = data['brand']
                            if isinstance(brand_info, dict):
                                veri['marka'] = brand_info.get('name', '')
                            else:
                                veri['marka'] = str(brand_info)
                        break
                except:
                    continue

            # FIYAT DETAYLARI
            # Orijinal fiyat
            original_price_elem = soup.select_one('.sale-price.sale-variant-price, .sale-price.blc')
            if original_price_elem:
                veri['orijinal_fiyat'] = original_price_elem.get_text(strip=True)

            # Indirimli fiyat
            discount_price_elem = soup.select_one('.discount-price, .new-sale-price')
            if discount_price_elem:
                veri['indirimli_fiyat'] = discount_price_elem.get_text(strip=True)
                veri['fiyat'] = veri['indirimli_fiyat']

            # Eger indirimli fiyat yoksa, orijinal fiyati kullan
            if not veri['fiyat'] and veri['orijinal_fiyat']:
                veri['fiyat'] = veri['orijinal_fiyat']

            # Hala fiyat yoksa, kapsamli arama
            if not veri['fiyat']:
                all_prices = soup.find_all(class_=lambda x: x and 'price' in x.lower())
                for p in all_prices:
                    text = p.get_text(strip=True)
                    if 'TL' in text and any(c.isdigit() for c in text):
                        veri['fiyat'] = text
                        break

            # Indirim yuzdesi
            discount_texts = soup.find_all(string=re.compile(r'%\s*\d+'))
            for text in discount_texts:
                percent_match = re.search(r'%\s*(\d+)', text)
                if percent_match:
                    veri['indirim_yuzdesi'] = f"%{percent_match.group(1)}"
                    break

            # Kazanc
            profit_elem = soup.select_one('.profit-price')
            if profit_elem:
                veri['kazanc'] = profit_elem.get_text(strip=True)

            # Kampanya metni
            campaign_pattern = re.compile(r'Her\s+[\d.,]+\s*TL.*?ndirim', re.IGNORECASE)
            campaign_texts = soup.find_all(string=campaign_pattern)
            if campaign_texts:
                veri['kampanya_metni'] = campaign_texts[0].strip()

            # Sepette indirim
            discount_name_elem = soup.find(class_='discount-name')
            if discount_name_elem:
                discount_text = discount_name_elem.get_text(strip=True)
                sepette_match = re.search(r'Sepette\s*%?\s*\d+\s*[İi]ndirim', discount_text, re.IGNORECASE)
                if sepette_match:
                    veri['sepette_indirim'] = sepette_match.group(0)

            # VALIDASYON
            validated_veri = DataValidator.validate_product_data(veri)

            # BOS URUN KONTROLU - Urun adi yoksa kaydetme
            if not validated_veri.get('urun_adi_tam') or not validated_veri.get('urun_adi_tam').strip():
                print(f"[SKIP] Bos urun adi: {url}")
                return None

            print(f"[OK] {validated_veri['urun_adi_tam']}")
            return validated_veri

        except Exception as e:
            print(f"[ERROR] Urun detay hatasi {url}: {str(e)}")
            return None

    async def get_product_links_from_page(self, session: aiohttp.ClientSession, page_url: str):
        """Bir sayfadaki tum urun linklerini al"""
        soup = await self.get_page_async(session, page_url)
        if not soup:
            return []

        # Urun bulunamadi kontrolu
        warning = soup.find(class_='alert alert-warning')
        if warning and 'Ürün bulunamadı' in warning.get_text():
            return None  # None = tarama bitti

        # Link cekme (iyilestirilmis selector sistemi ile)
        product_links = self.get_product_links(soup)
        return product_links

    async def scrape_all_async(self, max_pages=None):
        """Ana asenkron scraping fonksiyonu"""
        base_url = "https://www.dogtas.com/tumu-c-0?siralama=a-z&sayfa="
        all_products = []

        self.semaphore = asyncio.Semaphore(self.max_concurrent)

        connector = aiohttp.TCPConnector(limit=10, limit_per_host=5)
        timeout = aiohttp.ClientTimeout(total=60)

        async with aiohttp.ClientSession(
            headers=self.headers,
            connector=connector,
            timeout=timeout
        ) as session:
            page = 1

            while True:
                if max_pages and page > max_pages:
                    print(f"\n[INFO] Maksimum sayfa sayisina ulasildi: {max_pages}")
                    break

                page_url = f"{base_url}{page}"
                print(f"\n{'='*60}")
                print(f"SAYFA {page}")
                print(f"{'='*60}")

                # 1. Sayfadaki linkleri cek
                product_urls = await self.get_product_links_from_page(session, page_url)

                if product_urls is None:  # Tarama bitti
                    print(f"[INFO] Tarama tamamlandi - urun bulunamadi")
                    break

                if not product_urls:
                    print(f"[WARNING] Link bulunamadi - Tarama tamamlandi")
                    break

                # print(f"[OK] {len(product_urls)} urun bulundu")
                # print(f"[PROCESSING] Urunler cekiliyor...")

                page_success = 0
                for idx, url in enumerate(product_urls, 1):
                    print(f"[{idx}/{len(product_urls)}]", end=" ")

                    result = await self.get_product_detail_async(session, url)

                    if result and not isinstance(result, Exception):
                        # Filtreleme kontrolu
                        if not ProductFilter.should_filter_product(result):
                            all_products.append(result)
                            page_success += 1

                    # Urun arasi bekleme
                    await asyncio.sleep(self.config['rate_limit_delay'])

                print(f"\n[OK] Sayfa {page} tamamlandi")
                print(f"     Kaydedilen: {page_success} urun")
                print(f"     Toplam: {len(all_products)} urun")

                page += 1
                # Sayfa arasi bekleme
                await asyncio.sleep(self.config['page_delay'])

        return all_products

    def save_to_excel(self, data: List[Dict], filename: str):
        """Excel'e kaydet"""
        if not data:
            print("[WARNING] Kaydedilecek veri yok")
            return

        filepath = self.output_dir / filename

        # DataFrame olustur
        df = pd.DataFrame(data)

        # urun_adi_tam'a gore A-Z siralama
        if 'urun_adi_tam' in df.columns:
            df = df.sort_values(by='urun_adi_tam', ascending=True, na_position='last')
            df = df.reset_index(drop=True)

        # Sutun siralamasi - Guncel sütunlar
        columns_order = [
            'kategori', 'KOLEKSIYON', 'sku', 'urun_adi_tam', 'urun_adi',
            'LISTE', 'PERAKENDE', 'urun_url'
        ]

        # Mevcut sutunlari sirala
        existing_columns = [col for col in columns_order if col in df.columns]
        df = df[existing_columns]

        # Excel'e kaydet
        df.to_excel(filepath, index=False, engine='openpyxl')
        print(f"[SAVED] Excel: {filepath} ({len(df)} satir)")

    def save_to_json(self, data: List[Dict], filename: str):
        """JSON'a kaydet"""
        if not data:
            print("[WARNING] Kaydedilecek veri yok")
            return

        filepath = self.output_dir / filename

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"[SAVED] JSON: {filepath} ({len(data)} urun)")

    def run(self, max_pages=None):
        """Sync wrapper - main()'den cagirmak icin"""
        return asyncio.run(self.scrape_all_async(max_pages))


class DogtasSitemapScraper:
    """Sitemap XML ile Doğtaş ürün scraper - Other.xlsx için"""

    def __init__(self, max_concurrent=2):
        self.base_url = "https://www.dogtas.com"
        self.max_concurrent = max_concurrent
        self.semaphore = None

        # Sitemap XML URL'leri
        self.sitemap_urls = [
            "https://www.dogtas.com/sitemap/products/1.xml",
            "https://www.dogtas.com/sitemap/products/2.xml",
            "https://www.dogtas.com/sitemap/products/3.xml",
            "https://www.dogtas.com/sitemap/products/4.xml",
            "https://www.dogtas.com/sitemap/products/5.xml",
            "https://www.dogtas.com/sitemap/products/6.xml",
        ]

        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        }

        self.config = {
            'initial_timeout': 20,
            'max_timeout': 90,
            'retry_count': 3,
            'backoff_factor': 2,
            'rate_limit_delay': 1,  # Sitemap için daha hızlı
        }

    async def get_page_async(self, session: aiohttp.ClientSession, url: str, attempt=1):
        """Adaptive timeout ve retry logic ile asenkron sayfa çekme"""
        max_attempts = self.config['retry_count']
        timeout = self.config['initial_timeout'] * (self.config['backoff_factor'] ** (attempt - 1))
        timeout = min(timeout, self.config['max_timeout'])

        try:
            async with self.semaphore:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
                    response.raise_for_status()
                    html = await response.text()
                    return BeautifulSoup(html, 'html.parser')

        except asyncio.TimeoutError:
            if attempt < max_attempts:
                wait_time = 2 ** attempt
                print(f"[TIMEOUT] Deneme {attempt}/{max_attempts} - Bekleniyor {wait_time}s...")
                await asyncio.sleep(wait_time)
                return await self.get_page_async(session, url, attempt + 1)
            else:
                print(f"[ERROR] Timeout - Maksimum deneme: {url}")
                return None

        except Exception as e:
            if attempt < max_attempts:
                wait_time = attempt * 1.5
                print(f"[ERROR] {e} - Tekrar deneniyor ({attempt}/{max_attempts})...")
                await asyncio.sleep(wait_time)
                return await self.get_page_async(session, url, attempt + 1)
            else:
                print(f"[ERROR] Başarısız: {url} - {e}")
                return None

    async def get_xml_async(self, session: aiohttp.ClientSession, url: str) -> Optional[str]:
        """XML sitemap dosyasını indir"""
        try:
            async with self.semaphore:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    response.raise_for_status()
                    xml_content = await response.text()
                    return xml_content
        except Exception as e:
            print(f"[ERROR] XML indirme hatası {url}: {e}")
            return None

    def find_sku_in_xml(self, xml_content: str, sku: str) -> Optional[str]:
        """XML içinde SKU'yu ara ve URL döndür"""
        if not xml_content:
            return None

        try:
            # XML namespace
            namespaces = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}

            root = ET.fromstring(xml_content)

            # Tüm <loc> etiketlerini kontrol et
            for url_elem in root.findall('ns:url', namespaces):
                loc_elem = url_elem.find('ns:loc', namespaces)
                if loc_elem is not None and loc_elem.text:
                    url = loc_elem.text.strip()
                    # SKU URL içinde geçiyor mu?
                    if sku in url:
                        return url

            return None

        except Exception as e:
            print(f"[ERROR] XML parse hatası: {e}")
            return None

    async def search_sku_in_sitemaps(self, session: aiohttp.ClientSession, sku: str) -> Optional[str]:
        """SKU'yu tüm sitemap XML'lerinde ara (1-6)"""
        for idx, sitemap_url in enumerate(self.sitemap_urls, 1):
            try:
                # XML indir
                xml_content = await self.get_xml_async(session, sitemap_url)

                if xml_content:
                    # SKU'yu ara
                    product_url = self.find_sku_in_xml(xml_content, sku)

                    if product_url:
                        print(f"[XML-{idx}]", end=" ")
                        return product_url

                # Kısa bekleme
                await asyncio.sleep(0.5)

            except Exception as e:
                print(f"[ERROR] Sitemap {idx} hatası: {e}")
                continue

        return None

    def baslik_ayikla(self, baslik_etiketi):
        """Başlık etiketinden koleksiyon adını ve ürün adını ayıklar"""
        if not baslik_etiketi:
            return "", ""

        koleksiyon_adi = ""
        span_etiketi = baslik_etiketi.find('span')
        if span_etiketi:
            koleksiyon_adi = span_etiketi.get_text(strip=True)

        urun_adi = ""
        if span_etiketi and span_etiketi.next_sibling:
            urun_adi = span_etiketi.next_sibling.strip()
        elif baslik_etiketi:
            urun_adi = baslik_etiketi.get_text(strip=True)

        return koleksiyon_adi, urun_adi

    async def get_product_detail_async(self, session: aiohttp.ClientSession, url: str):
        """Asenkron ürün detay çekme"""
        try:
            soup = await self.get_page_async(session, url)
            if not soup:
                return None

            veri = {
                'KOLEKSIYON': "",
                'urun_adi': "",
                'urun_adi_tam': "",
                'sku': "",
                'orijinal_fiyat': "",
                'fiyat': "",
                'kategori': "",
                'marka': "",
                'urun_url': url
            }

            # Başlık
            baslik_etiketi = soup.find('h1', class_='title')
            veri['KOLEKSIYON'], veri['urun_adi'] = self.baslik_ayikla(baslik_etiketi)

            # Tam ürün adı oluştur
            if veri['KOLEKSIYON'] and veri['urun_adi']:
                veri['urun_adi_tam'] = f"{veri['KOLEKSIYON']} {veri['urun_adi']}"
            else:
                veri['urun_adi_tam'] = veri['urun_adi']

            # Eger sadece koleksiyon varsa ve ürün adı yoksa, None dön
            if veri['KOLEKSIYON'] and not veri['urun_adi']:
                return None

            # SKU
            sku_etiketi = soup.find(class_='sku')
            if sku_etiketi:
                sku_metni = sku_etiketi.get_text(strip=True)
                sku_eslesme = re.search(r'(\d+)', sku_metni)
                veri['sku'] = sku_eslesme.group(1) if sku_eslesme else ""

            # Kategori (breadcrumb)
            breadcrumb_elem = soup.find('ol', class_='breadcrumb')
            if breadcrumb_elem:
                breadcrumb_items = []
                for li in breadcrumb_elem.find_all('li'):
                    text = li.get_text(strip=True)
                    if text and text not in ['Ana Sayfa', 'Home']:
                        breadcrumb_items.append(text)

                if len(breadcrumb_items) >= 1:
                    veri['kategori'] = breadcrumb_items[0]

            # Marka (JSON-LD)
            json_ld_scripts = soup.find_all('script', type='application/ld+json')
            for script in json_ld_scripts:
                try:
                    data = json.loads(script.string)
                    if data.get('@type') == 'Product':
                        if 'brand' in data:
                            brand_info = data['brand']
                            if isinstance(brand_info, dict):
                                veri['marka'] = brand_info.get('name', '')
                            else:
                                veri['marka'] = str(brand_info)
                        break
                except:
                    continue

            # FIYAT DETAYLARI
            # Orijinal fiyat
            original_price_elem = soup.select_one('.sale-price.sale-variant-price, .sale-price.blc')
            if original_price_elem:
                veri['orijinal_fiyat'] = original_price_elem.get_text(strip=True)

            # İndirimli fiyat
            discount_price_elem = soup.select_one('.discount-price, .new-sale-price')
            if discount_price_elem:
                veri['fiyat'] = discount_price_elem.get_text(strip=True)

            # Eger indirimli fiyat yoksa, orijinal fiyatı kullan
            if not veri['fiyat'] and veri['orijinal_fiyat']:
                veri['fiyat'] = veri['orijinal_fiyat']

            # Hala fiyat yoksa, kapsamlı arama
            if not veri['fiyat']:
                all_prices = soup.find_all(class_=lambda x: x and 'price' in x.lower())
                for p in all_prices:
                    text = p.get_text(strip=True)
                    if 'TL' in text and any(c.isdigit() for c in text):
                        veri['fiyat'] = text
                        break

            # VALIDASYON
            validated_veri = DataValidator.validate_product_data(veri)

            # BOŞ ÜRÜN KONTROLÜ
            if not validated_veri.get('urun_adi_tam') or not validated_veri.get('urun_adi_tam').strip():
                return None

            return validated_veri

        except Exception as e:
            print(f"[ERROR] Ürün detay hatası {url}: {str(e)}")
            return None

    async def search_and_scrape_sku(self, session: aiohttp.ClientSession, sku: str):
        """SKU ile sitemap XML'lerinde ara ve ürün detayını çek"""
        try:
            print(f"[SEARCH] SKU: {sku}", end=" ")

            # Sitemap XML'lerinde ara (1-6)
            product_url = await self.search_sku_in_sitemaps(session, sku)

            if not product_url:
                print("- Ürün bulunamadı")
                return None

            print(f"- Link bulundu", end=" ")

            # Ürün detayını çek
            result = await self.get_product_detail_async(session, product_url)

            if result:
                # Filtreleme kontrolü
                if not ProductFilter.should_filter_product(result):
                    print(f"- OK: {result.get('urun_adi_tam')}")
                    return result
                else:
                    print(f"- Filtrelendi")
                    return None
            else:
                print("- Detay çekilemedi")
                return None

        except Exception as e:
            print(f"[ERROR] SKU {sku} arama hatası: {e}")
            return None

    async def scrape_from_sku_list_async(self, sku_list: List[str]):
        """SKU listesinden ürünleri çek"""
        if not sku_list:
            print("[INFO] SKU listesi boş")
            return []

        print(f"\n{'='*80}")
        print(f"OTHER.XLSX TARAMASI (SITEMAP XML)")
        print(f"{'='*80}")
        print(f"[INFO] {len(sku_list)} SKU taranacak...")

        products = []
        self.semaphore = asyncio.Semaphore(self.max_concurrent)

        connector = aiohttp.TCPConnector(limit=10, limit_per_host=5)
        timeout = aiohttp.ClientTimeout(total=60)

        async with aiohttp.ClientSession(
            headers=self.headers,
            connector=connector,
            timeout=timeout
        ) as session:

            for idx, sku in enumerate(sku_list, 1):
                print(f"[{idx}/{len(sku_list)}] ", end="")

                result = await self.search_and_scrape_sku(session, sku)

                if result:
                    products.append(result)

                # SKU arası bekleme
                await asyncio.sleep(self.config['rate_limit_delay'])

        print(f"\n[OK] Tarama tamamlandı")
        print(f"     Toplam: {len(products)} ürün bulundu")

        return products


def print_statistics(products: List[Dict]):
    """Istatistikleri yazdir"""
    print("\n" + "="*80)
    print("OZET ISTATISTIKLER")
    print("="*80)
    print(f"Toplam Urun: {len(products)}")

    # Kategorilere gore dagilim
    kategoriler = {}
    for p in products:
        kat = p.get('kategori', 'Bilinmiyor')
        if kat:
            kategoriler[kat] = kategoriler.get(kat, 0) + 1

    print(f"\nKategoriler (Top 10):")
    for kat, sayi in sorted(kategoriler.items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"  - {kat}: {sayi} urun")

    # Fiyat istatistikleri
    liste_prices = [p.get('LISTE') for p in products if p.get('LISTE')]
    perakende_prices = [p.get('PERAKENDE') for p in products if p.get('PERAKENDE')]

    if liste_prices:
        print(f"\nLISTE Fiyat Istatistikleri:")
        print(f"  - Ortalama: {sum(liste_prices)/len(liste_prices):,.0f} TL")
        print(f"  - Minimum: {min(liste_prices):,} TL")
        print(f"  - Maksimum: {max(liste_prices):,} TL")

    if perakende_prices:
        print(f"\nPERAKENDE Fiyat Istatistikleri:")
        print(f"  - Ortalama: {sum(perakende_prices)/len(perakende_prices):,.0f} TL")
        print(f"  - Minimum: {min(perakende_prices):,} TL")
        print(f"  - Maksimum: {max(perakende_prices):,} TL")

    # Duplike urunler (komodin veya ayna)
    yemek_yatak = [p for p in products if p.get('kategori') == 'Yatak Odası' and
                   ('komodin' in p.get('urun_adi', '').lower() or 'ayna' in p.get('urun_adi', '').lower())]
    if yemek_yatak:
        print(f"\nYemek Odası -> Yatak Odası duplike: {len(yemek_yatak)} urun")


def main():
    # Stdout'u flush et (gerçek zamanlı çıktı için)
    sys.stdout.reconfigure(line_buffering=True)

    # Başlangıç mesajları - konsola yaz
    print("="*80, flush=True)
    print("DOGTAS SCRAPER - COMBINED VERSION", flush=True)
    print("1) Ana Doğtaş sitesini tarar (tüm sayfalar)", flush=True)
    print("2) Other.xlsx'ten SKU okur ve Sitemap XML'de arar", flush=True)
    print("="*80, flush=True)

    # Eski backup dosyalarini temizle
    output_dir = Path(get_base_dir())
    backup_files = list(output_dir.glob("dogtas_backup_page*.xlsx"))
    if backup_files:
        print(f"\n[CLEANUP] {len(backup_files)} eski backup dosyası siliniyor...", flush=True)
        for backup_file in backup_files:
            try:
                backup_file.unlink()
                print(f"  - Silindi: {backup_file.name}", flush=True)
            except Exception as e:
                print(f"  - Hata: {backup_file.name} - {e}", flush=True)
        print("[OK] Temizlik tamamlandı\n", flush=True)

    # Scraper olustur (concurrent=1, yavas tarama)
    scraper = DogtasAsyncScraper(max_concurrent=1)

    # TUM SAYFALARI CEK (max_pages = None)
    print(f"\n[INFO] TUM sayfalar cekilecek...", flush=True)

    # Zamanlama
    start_time = time.time()

    # SCRAPING
    print("\n" + "="*80, flush=True)
    print("SCRAPING BASLIYOR...", flush=True)
    print("="*80, flush=True)

    all_products = scraper.run(max_pages=None)

    # Duplikasyon kurallari uygula
    print("\n[PROCESSING] Duplikasyon kurallari uygulanıyor...")
    all_products = ProductFilter.apply_duplication_rules(all_products)

    # OTHER.XLSX TARAMASI - SITEMAP XML KULLANARAK
    other_xlsx_path = output_dir / "Other.xlsx"
    if other_xlsx_path.exists():
        print(f"\n[INFO] Other.xlsx dosyası bulundu, Sitemap XML taraması başlıyor...")

        # SKU'ları oku
        sku_list = read_other_xlsx(str(other_xlsx_path))

        if sku_list:
            # DogtasSitemapScraper ile SKU'lar için tarama yap
            sitemap_scraper = DogtasSitemapScraper(max_concurrent=2)
            other_products = asyncio.run(sitemap_scraper.scrape_from_sku_list_async(sku_list))

            # Duplikasyon kurallarını uygula
            if other_products:
                print(f"[PROCESSING] Other.xlsx verileri için duplikasyon kuralları uygulanıyor...")
                other_products = ProductFilter.apply_duplication_rules(other_products)

                # Ana listeye ekle
                all_products.extend(other_products)
                print(f"[OK] Other.xlsx'den {len(other_products)} ürün eklendi")
                print(f"[OK] Toplam ürün sayısı: {len(all_products)}")
    else:
        print(f"\n[INFO] Other.xlsx bulunamadı: {other_xlsx_path}")

    elapsed = time.time() - start_time

    # SONUCLAR
    print(f"\n{'='*80}")
    print(f"TARAMA TAMAMLANDI!")
    print(f"Sure: {elapsed:.2f} saniye ({elapsed/60:.2f} dakika)")
    if all_products:
        print(f"Hiz: {len(all_products)/elapsed:.2f} urun/saniye")
    print(f"{'='*80}")

    if all_products:
        # SABIT DOSYA ISIMLERI
        excel_filename = "dogtasCom.xlsx"

        # EXCEL KAYDI
        scraper.save_to_excel(all_products, excel_filename)

        # ISTATISTIKLER
        print_statistics(all_products)

        print("\n" + "="*80)
        print("DOSYALAR:")
        print(f"  - Excel: {excel_filename}")
        print("="*80)
    else:
        print("\n[HATA] Hic urun cekilemedi!")


if __name__ == "__main__":
    main()
