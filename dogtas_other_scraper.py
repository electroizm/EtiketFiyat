"""
DOGTAS OTHER.XLSX SCRAPER
- Other.xlsx'ten SKU okur
- Her SKU için Google araması yapar
- Ürün detaylarını çeker
- dogtasCom.xlsx'e kaydeder
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
from urllib.parse import urljoin, quote
import pandas as pd
from typing import List, Optional, Dict
from pathlib import Path


def get_base_dir():
    """Exe veya script dizinini döndür"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


class DataValidator:
    """Ürün verilerini validate ve temizle"""

    @staticmethod
    def clean_price(price_text: str) -> Optional[float]:
        """Fiyat textini temizle ve float'a çevir"""
        if not price_text:
            return None

        try:
            clean_text = re.sub(r'[^\d.,]', '', price_text)
            if not clean_text:
                return None

            # Türkçe format (12.500,50) -> (12500.50)
            if ',' in clean_text and '.' in clean_text:
                if clean_text.rindex('.') < clean_text.rindex(','):
                    clean_text = clean_text.replace('.', '').replace(',', '.')
                else:
                    clean_text = clean_text.replace(',', '')
            elif ',' in clean_text:
                clean_text = clean_text.replace(',', '.')
            elif '.' in clean_text:
                parts = clean_text.split('.')
                if len(parts[-1]) == 2:
                    pass
                else:
                    clean_text = clean_text.replace('.', '')

            price = float(clean_text)

            if 10 <= price <= 1_000_000:
                return price
            else:
                print(f"[WARNING] Fiyat aralık dışı: {price}")
                return None

        except (ValueError, AttributeError) as e:
            print(f"[WARNING] Fiyat parse hatası: {price_text}")
            return None

    @staticmethod
    def clean_sku(sku_text: str) -> Optional[str]:
        """SKU temizle ve validate et"""
        if not sku_text:
            return None

        sku = re.sub(r'[^A-Za-z0-9\-_]', '', sku_text.strip())

        if len(sku) >= 3:
            return sku
        else:
            return None

    @staticmethod
    def validate_product_data(data: Dict) -> Dict:
        """Tüm ürün verisini validate et ve temizle"""
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

        # String alanları temizle
        for field in ['urun_adi', 'urun_adi_tam', 'KOLEKSIYON', 'kategori']:
            if validated.get(field):
                validated[field] = validated[field].strip()

        # Gereksiz alanları kaldır
        fields_to_remove = [
            'orijinal_fiyat', 'indirimli_fiyat', 'fiyat',
            'indirim_yuzdesi', 'kazanc', 'kampanya_metni',
            'sepette_indirim', 'marka'
        ]
        for field in fields_to_remove:
            validated.pop(field, None)

        return validated


class ProductFilter:
    """Ürün filtreleme kuralları"""

    FILTER_KEYWORDS = [
        'Abajur', 'Halı', 'Biblo', 'Kırlent', 'Tablo', 'Sarkıt',
        'Çerceve', 'Vazo', 'Mum', 'Obje', 'Küp', 'Saat',
        'Lambader', 'Tabak', 'Şamdan'
    ]

    @staticmethod
    def should_filter_product(product: Dict) -> bool:
        """Ürünü filtrelemeli miyiz?"""
        kategori = product.get('kategori', '').strip()
        urun_adi = product.get('urun_adi', '').strip()
        urun_adi_tam = product.get('urun_adi_tam', '').strip()

        # Doğtaş Home kategorisini filtrele
        if kategori == "Doğtaş Home":
            print(f"[FILTER] Doğtaş Home kategorisi: {urun_adi_tam}")
            return True

        # Kategori boş ve ürün adı filtreleme kelimelerini içeriyorsa
        if not kategori:
            combined_name = f"{urun_adi} {urun_adi_tam}".lower()
            for keyword in ProductFilter.FILTER_KEYWORDS:
                if keyword.lower() in combined_name:
                    print(f"[FILTER] Boş kategori + {keyword}: {urun_adi_tam}")
                    return True

        return False

    @staticmethod
    def apply_duplication_rules(products: List[Dict]) -> List[Dict]:
        """Duplikasyon kuralları uygula"""
        result = []

        for product in products:
            result.append(product)

            kategori = product.get('kategori', '').strip()
            urun_adi = product.get('urun_adi', '').lower()
            urun_adi_tam = product.get('urun_adi_tam', '').lower()

            # Yemek Odası + (komodin veya ayna) kontrolü
            if kategori == "Yemek Odası":
                if 'komodin' in urun_adi or 'komodin' in urun_adi_tam or \
                   'ayna' in urun_adi or 'ayna' in urun_adi_tam:
                    duplicated = product.copy()
                    duplicated['kategori'] = "Yatak Odası"
                    result.append(duplicated)
                    print(f"[DUPLICATE] Yemek Odası -> Yatak Odası: {product.get('urun_adi_tam')}")

        return result


def read_other_xlsx(file_path: str) -> List[str]:
    """Other.xlsx dosyasından SKU verilerini oku"""
    try:
        if not os.path.exists(file_path):
            print(f"[ERROR] Other.xlsx bulunamadı: {file_path}")
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
            sku_str = str(value).strip()

            # 10 haneli ve 3 ile başlayan kontrolü
            if sku_str.isdigit() and len(sku_str) == 10 and sku_str.startswith('3'):
                sku_list.append(sku_str)

        print(f"[OK] Other.xlsx'den {len(sku_list)} SKU okundu")
        return sku_list

    except Exception as e:
        print(f"[ERROR] Other.xlsx okuma hatası: {e}")
        return []


class DogtasGoogleScraper:
    """Google arama ile Doğtaş ürün scraper"""

    def __init__(self, max_concurrent=2):
        self.base_url = "https://www.dogtas.com"
        self.max_concurrent = max_concurrent
        self.semaphore = None

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
            'rate_limit_delay': 2,
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

    def get_product_link_from_google(self, soup: BeautifulSoup) -> Optional[str]:
        """Google arama sonucundan Doğtaş ürün linkini bul"""
        if not soup:
            return None

        # Google arama sonuçlarını bul
        # Google'ın farklı selector'ları
        selectors = [
            'div.g a[href*="dogtas.com"]',
            'a[href*="dogtas.com"]',
            '[data-ved] a[href*="dogtas.com"]',
        ]

        for selector in selectors:
            try:
                links = soup.select(selector)

                for link in links:
                    href = link.get('href', '').strip()

                    if not href:
                        continue

                    # Google redirect URL'lerini temizle
                    if '/url?q=' in href:
                        # /url?q=https://www.dogtas.com/... formatından URL'i çek
                        match = re.search(r'/url\?q=([^&]+)', href)
                        if match:
                            href = match.group(1)

                    # Geçersiz linkleri filtrele
                    if any(skip in href.lower() for skip in ['google.com', 'youtube.com', 'kategori', 'collection']):
                        continue

                    # Doğtaş ürün sayfası olmalı
                    if 'dogtas.com' in href and not any(skip in href.lower() for skip in ['/tumu-c-', '/kategori', '/collection']):
                        return href

            except Exception as e:
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
        """SKU ile Google'da ara ve ürün detayını çek"""
        try:
            # Google arama URL'si
            search_url = f"https://www.google.com/search?q=site%3Adogtas.com+{sku}"

            print(f"[SEARCH] SKU: {sku}", end=" ")

            # Google arama sayfasını çek
            soup = await self.get_page_async(session, search_url)
            if not soup:
                print("- Google sayfası yüklenemedi")
                return None

            # Ürün linkini bul
            product_url = self.get_product_link_from_google(soup)

            if not product_url:
                print("- Ürün linki bulunamadı")
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
        print(f"OTHER.XLSX TARAMASI")
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


def save_to_excel(products: List[Dict], filepath: str):
    """Ürünleri Excel'e kaydet"""
    if not products:
        print("[WARNING] Kaydedilecek ürün yok")
        return

    # DataFrame oluştur
    df = pd.DataFrame(products)

    # urun_adi_tam'a göre A-Z sıralama
    if 'urun_adi_tam' in df.columns:
        df = df.sort_values(by='urun_adi_tam', ascending=True, na_position='last')
        df = df.reset_index(drop=True)

    # Sütun sıralaması
    columns_order = [
        'kategori', 'KOLEKSIYON', 'sku', 'urun_adi_tam', 'urun_adi',
        'LISTE', 'PERAKENDE', 'urun_url'
    ]

    existing_columns = [col for col in columns_order if col in df.columns]
    df = df[existing_columns]

    # Excel'e kaydet
    df.to_excel(filepath, index=False, engine='openpyxl')
    print(f"[SAVED] Excel: {filepath} ({len(df)} satır)")


def print_statistics(products: List[Dict]):
    """İstatistikleri yazdır"""
    print("\n" + "="*80)
    print("ÖZET İSTATİSTİKLER")
    print("="*80)
    print(f"Toplam Ürün: {len(products)}")

    # Kategorilere göre dağılım
    kategoriler = {}
    for p in products:
        kat = p.get('kategori', 'Bilinmiyor')
        if kat:
            kategoriler[kat] = kategoriler.get(kat, 0) + 1

    print(f"\nKategoriler:")
    for kat, sayi in sorted(kategoriler.items(), key=lambda x: x[1], reverse=True):
        print(f"  - {kat}: {sayi} ürün")

    # Fiyat istatistikleri
    liste_prices = [p.get('LISTE') for p in products if p.get('LISTE')]
    perakende_prices = [p.get('PERAKENDE') for p in products if p.get('PERAKENDE')]

    if liste_prices:
        print(f"\nLİSTE Fiyat İstatistikleri:")
        print(f"  - Ortalama: {sum(liste_prices)/len(liste_prices):,.0f} TL")
        print(f"  - Minimum: {min(liste_prices):,} TL")
        print(f"  - Maksimum: {max(liste_prices):,} TL")

    if perakende_prices:
        print(f"\nPERAKENDE Fiyat İstatistikleri:")
        print(f"  - Ortalama: {sum(perakende_prices)/len(perakende_prices):,.0f} TL")
        print(f"  - Minimum: {min(perakende_prices):,} TL")
        print(f"  - Maksimum: {max(perakende_prices):,} TL")


def main():
    """Ana fonksiyon"""
    # Stdout'u flush et
    sys.stdout.reconfigure(line_buffering=True)

    print("="*80, flush=True)
    print("DOGTAS OTHER.XLSX SCRAPER", flush=True)
    print("Other.xlsx'ten SKU okur -> Google'da arar -> dogtasCom.xlsx'e kaydeder", flush=True)
    print("="*80, flush=True)

    # Other.xlsx yolu
    other_xlsx_path = r"D:\GoogleDrive\PRG\Fiyat\Etiket\Other.xlsx"

    # Linux ortamında test için alternatif yol
    if not os.path.exists(other_xlsx_path):
        other_xlsx_path = os.path.join(get_base_dir(), "Other.xlsx")

    if not os.path.exists(other_xlsx_path):
        print(f"[ERROR] Other.xlsx bulunamadı: {other_xlsx_path}")
        print("[INFO] Lütfen Other.xlsx dosyasını script ile aynı dizine koyun")
        return

    # SKU'ları oku
    print(f"\n[INFO] Other.xlsx okunuyor: {other_xlsx_path}")
    sku_list = read_other_xlsx(other_xlsx_path)

    if not sku_list:
        print("[ERROR] Other.xlsx'ten SKU okunamadı")
        return

    # Scraper oluştur
    scraper = DogtasGoogleScraper(max_concurrent=2)

    # Zamanlama
    start_time = time.time()

    # SCRAPING
    print("\n" + "="*80)
    print("SCRAPING BAŞLIYOR...")
    print("="*80)

    products = asyncio.run(scraper.scrape_from_sku_list_async(sku_list))

    # Duplikasyon kuralları uygula
    if products:
        print("\n[PROCESSING] Duplikasyon kuralları uygulanıyor...")
        products = ProductFilter.apply_duplication_rules(products)

    elapsed = time.time() - start_time

    # SONUÇLAR
    print(f"\n{'='*80}")
    print(f"TARAMA TAMAMLANDI!")
    print(f"Süre: {elapsed:.2f} saniye ({elapsed/60:.2f} dakika)")
    if products:
        print(f"Hız: {len(products)/elapsed:.2f} ürün/saniye")
    print(f"{'='*80}")

    if products:
        # dogtasCom.xlsx'e kaydet
        output_path = os.path.join(os.path.dirname(other_xlsx_path), "dogtasCom.xlsx")
        save_to_excel(products, output_path)

        # İstatistikler
        print_statistics(products)

        print("\n" + "="*80)
        print(f"DOSYA: {output_path}")
        print("="*80)
    else:
        print("\n[HATA] Hiç ürün çekilemedi!")


if __name__ == "__main__":
    main()
