"""
JSON Görüntüleyici Widget
etiketEkle.json ve dogtasCom.xlsx dosyalarını tablo şeklinde karşılaştıran modül
"""

import sys
import os
import json
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                             QLabel, QMessageBox, QHeaderView, QLineEdit,
                             QTableWidget, QTableWidgetItem, QApplication,
                             QMainWindow, QCheckBox, QTreeWidget, QTreeWidgetItem)
from PyQt5.QtGui import QFont, QColor, QBrush
import pandas as pd
from datetime import datetime


def get_base_dir():
    """Exe veya script dizinini döndür"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


class PriceLoader:
    """Excel dosyasından fiyat verilerini yükleyen sınıf"""

    def __init__(self, excel_file):
        self.excel_file = excel_file
        self.price_data = {}
        self.load_prices()

    def load_prices(self):
        """Excel dosyasını yükle ve SKU bazlı fiyat sözlüğü oluştur"""
        try:
            df = pd.read_excel(self.excel_file)
            # SKU'yu string'e çevir ve fiyat bilgilerini sözlüğe aktar
            for _, row in df.iterrows():
                sku = str(row['sku'])
                self.price_data[sku] = {
                    'liste': float(row['LISTE']) if pd.notna(row['LISTE']) else 0.0,
                    'perakende': float(row['PERAKENDE']) if pd.notna(row['PERAKENDE']) else 0.0,
                    'kategori': str(row.get('kategori', '')),
                    'koleksiyon': str(row.get('KOLEKSIYON', ''))
                }
        except Exception as e:
            print(f"Excel yükleme hatası: {e}")
            self.price_data = {}

    def get_price(self, sku):
        """SKU'ya göre fiyat bilgisi döndür"""
        sku_str = str(sku)
        return self.price_data.get(sku_str, {
            'liste': 0.0,
            'perakende': 0.0,
            'kategori': '',
            'koleksiyon': ''
        })


class JsonGosterWidget(QWidget):
    """JSON Görüntüleyici Widget - Ana pencereye embed edilebilir"""

    def __init__(self, parent=None):
        super().__init__(parent)

        # Dosya yolları
        base_dir = get_base_dir()
        self.json_file = os.path.join(base_dir, "etiketEkle.json")
        self.excel_file = os.path.join(base_dir, "dogtasCom.xlsx")
        self.json_data = None
        self.price_loader = None
        self.table_data = []  # Tüm ürün verilerini saklar
        self.koleksiyon_widgets = {}  # {(kategori, koleksiyon): {'sec': checkbox, 'exc': checkbox, 'sube': checkbox, 'has_price_diff': bool}}
        self.takim_widgets = {}  # {(kategori, koleksiyon, takim_adi): checkbox}

        # UI setup
        self.setup_ui()
        self.load_data()

    def setup_ui(self):
        """UI bileşenlerini oluştur"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(10)

        # Arama kutusu ve butonlar (tek satırda)
        search_layout = QHBoxLayout()

        search_label = QLabel("🔍 Ara:")
        search_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        search_layout.addWidget(search_label)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Kategori, Koleksiyon, SKU veya Ürün Adı ara...")
        self.search_box.setStyleSheet("""
            QLineEdit {
                font-size: 12px;
                padding: 6px;
                border-radius: 4px;
                border: 2px solid #3498db;
                max-width: 400px;
            }
        """)
        self.search_box.textChanged.connect(self.filter_table)
        search_layout.addWidget(self.search_box)

        search_layout.addStretch()

        # Temizle butonu
        clear_btn = QPushButton("✖ Temizle")
        clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #000000;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2a2a2a;
            }
        """)
        clear_btn.clicked.connect(lambda: self.search_box.clear())
        search_layout.addWidget(clear_btn)

        # Yenile butonu
        refresh_btn = QPushButton("🔄 Yenile")
        refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #000000;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2a2a2a;
            }
        """)
        refresh_btn.clicked.connect(self.load_data)
        search_layout.addWidget(refresh_btn)

        # Koleksiyon Sil butonu
        delete_koleksiyon_btn = QPushButton("🗑 Koleksiyon Sil")
        delete_koleksiyon_btn.setStyleSheet("""
            QPushButton {
                background-color: #000000;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2a2a2a;
            }
        """)
        delete_koleksiyon_btn.clicked.connect(self.delete_unselected_koleksiyonlar)
        search_layout.addWidget(delete_koleksiyon_btn)

        # Takım Sil butonu
        delete_takim_btn = QPushButton("🗑 Takım Sil")
        delete_takim_btn.setStyleSheet("""
            QPushButton {
                background-color: #000000;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2a2a2a;
            }
        """)
        delete_takim_btn.clicked.connect(self.delete_selected_takimlar)
        search_layout.addWidget(delete_takim_btn)

        # Genişlet butonu (Sadece kategori ve koleksiyon)
        expand_partial_btn = QPushButton("⬇ Genişlet")
        expand_partial_btn.setStyleSheet("""
            QPushButton {
                background-color: #000000;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2a2a2a;
            }
        """)
        expand_partial_btn.clicked.connect(self.expand_partial)
        search_layout.addWidget(expand_partial_btn)

        # Tümünü Genişlet butonu
        expand_all_btn = QPushButton("⬇⬇ Tümünü Genişlet")
        expand_all_btn.setStyleSheet("""
            QPushButton {
                background-color: #000000;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2a2a2a;
            }
        """)
        expand_all_btn.clicked.connect(self.expand_all)
        search_layout.addWidget(expand_all_btn)

        # Kaydet butonu
        save_btn = QPushButton("💾 Kaydet")
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: #000000;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2a2a2a;
            }
        """)
        save_btn.clicked.connect(self.save_data)
        search_layout.addWidget(save_btn)

        main_layout.addLayout(search_layout)

        # Ana Tree (Gruplandırılmış Tablo)
        self.tree = QTreeWidget()
        self.tree.setStyleSheet("""
            QTreeWidget {
                font-size: 11px;
                border: 2px solid #bdc3c7;
                border-radius: 4px;
                background-color: white;
                gridline-color: #ecf0f1;
            }
            QTreeWidget::item {
                padding: 5px;
            }
            QHeaderView::section {
                background-color: #3498db;
                color: white;
                padding: 6px;
                border: 1px solid #2980b9;
                font-weight: bold;
                font-size: 11px;
            }
        """)

        # Tree kolonlarını ayarla
        self.tree.setColumnCount(13)
        self.tree.setHeaderLabels([
            "SEÇ",
            "EXC",
            "SUBE",
            "Kategori / KOLEKSIYON",
            "Takım",
            "Miktar",
            "Malzeme Adı",
            "LISTE",
            "PERAKENDE",
            "Fark",
            "LISTE_new",
            "PERAKENDE_new",
            "sku"
        ])

        main_layout.addWidget(self.tree)

        # Status label
        self.status_label = QLabel("Hazır")
        self.status_label.setStyleSheet("""
            QLabel {
                color: #2c3e50;
                padding: 6px;
                background-color: #ecf0f1;
                border-top: 1px solid #bdc3c7;
                font-size: 11px;
                font-weight: bold;
                border-radius: 3px;
            }
        """)
        main_layout.addWidget(self.status_label)

    def load_data(self):
        """JSON ve Excel dosyalarını yükle"""
        try:
            self.status_label.setText("🔄 Veriler yükleniyor...")
            QApplication.processEvents()

            # JSON dosyasını kontrol et
            if not os.path.exists(self.json_file):
                self.status_label.setText("❌ JSON dosyası bulunamadı")
                QMessageBox.warning(self, "Uyarı", f"JSON dosyası bulunamadı:\n{self.json_file}")
                return

            # Excel dosyasını kontrol et
            if not os.path.exists(self.excel_file):
                self.status_label.setText("❌ Excel dosyası bulunamadı")
                QMessageBox.warning(self, "Uyarı", f"Excel dosyası bulunamadı:\n{self.excel_file}")
                return

            # JSON dosyasını oku
            with open(self.json_file, 'r', encoding='utf-8') as f:
                self.json_data = json.load(f)

            # Excel fiyat verilerini yükle
            self.price_loader = PriceLoader(self.excel_file)

            # Tablo verilerini hazırla
            self.prepare_table_data()

            # Tree'yi doldur (gruplandırılmış)
            self.populate_tree()

            total_urunler = len(self.table_data)
            self.status_label.setText(f"✅ Veriler yüklendi: {total_urunler} ürün, {len(self.price_loader.price_data)} SKU")

        except Exception as e:
            error_msg = f"Veri yükleme hatası: {str(e)}"
            self.status_label.setText(f"❌ {error_msg}")
            QMessageBox.critical(self, "Hata", error_msg)

    def prepare_table_data(self):
        """JSON'dan tüm etiket_listesi ve takım verilerini çıkar"""
        self.table_data = []
        self.takim_data = {}  # {kategori: {koleksiyon: {takim_adi: [products]}}}

        if not self.json_data:
            return

        # Her kategori için
        for kategori_adi, kategori_data in self.json_data.items():
            # Her koleksiyon için
            for koleksiyon_adi, koleksiyon_data in kategori_data.items():
                # Etiket listesini kontrol et
                if 'etiket_listesi' in koleksiyon_data:
                    etiket_listesi = koleksiyon_data['etiket_listesi']
                    urunler = etiket_listesi.get('urunler', [])

                    # Her ürün için
                    for urun in urunler:
                        sku = str(urun.get('sku', ''))

                        # SKU filtreleme: 3 ile başlamalı ve 10 haneli olmalı
                        if not sku.startswith('3') or len(sku) != 10:
                            continue

                        urun_adi = urun.get('urun_adi_tam', '')
                        liste_fiyat = urun.get('liste_fiyat', 0.0)
                        perakende_fiyat = urun.get('perakende_fiyat', 0.0)

                        # Excel'den güncel fiyatı al
                        price_info = self.price_loader.get_price(sku) if self.price_loader else {
                            'liste': 0.0,
                            'perakende': 0.0,
                            'kategori': kategori_adi,
                            'koleksiyon': koleksiyon_adi
                        }

                        # Malzeme adı: KOLEKSIYON + Ürün Adı
                        Malzeme_adi = f"{koleksiyon_adi} {urun_adi.replace(koleksiyon_adi, '').strip()}"

                        # Tabloya eklenecek satır verisi (etiket_listesi için)
                        row_data = {
                            'type': 'etiket_listesi',
                            'sku': sku,
                            'miktar': 1,
                            'urun_adi': urun_adi,
                            'Malzeme_adi': Malzeme_adi,
                            'liste': liste_fiyat,
                            'perakende': perakende_fiyat,
                            'kategori': kategori_adi,
                            'koleksiyon': koleksiyon_adi,
                            'liste_new': price_info['liste'],
                            'perakende_new': price_info['perakende']
                        }

                        self.table_data.append(row_data)

                # Takım verilerini topla
                if kategori_adi not in self.takim_data:
                    self.takim_data[kategori_adi] = {}
                if koleksiyon_adi not in self.takim_data[kategori_adi]:
                    self.takim_data[kategori_adi][koleksiyon_adi] = {}

                # Takımları bul
                for key, value in koleksiyon_data.items():
                    if key != 'etiket_listesi' and isinstance(value, dict) and 'products' in value:
                        takim_adi = key
                        products = value.get('products', [])

                        # Takım ürünlerini işle
                        takim_urunler = []
                        for product in products:
                            product_sku = str(product.get('sku', ''))

                            # SKU filtreleme: 3 ile başlamalı ve 10 haneli olmalı
                            if not product_sku.startswith('3') or len(product_sku) != 10:
                                continue

                            product_miktar = product.get('miktar', 1)
                            urun_adi = product.get('urun_adi_tam', '')

                            # Excel'den güncel fiyatı al
                            price_info = self.price_loader.get_price(product_sku) if self.price_loader else {
                                'liste': 0.0,
                                'perakende': 0.0,
                                'kategori': kategori_adi,
                                'koleksiyon': koleksiyon_adi
                            }

                            # Malzeme adı
                            Malzeme_adi = f"{koleksiyon_adi} {urun_adi.replace(koleksiyon_adi, '').strip()}"

                            # Takım ürünü verisi
                            takim_urun = {
                                'type': 'takim_urun',
                                'sku': product_sku,
                                'miktar': product_miktar,
                                'urun_adi': urun_adi,
                                'Malzeme_adi': Malzeme_adi,
                                'liste': 0.0,  # Takım ürünlerinde liste fiyatı yok
                                'perakende': 0.0,  # Takım ürünlerinde perakende fiyatı yok
                                'kategori': kategori_adi,
                                'koleksiyon': koleksiyon_adi,
                                'liste_new': price_info['liste'],
                                'perakende_new': price_info['perakende']
                            }

                            takim_urunler.append(takim_urun)

                        self.takim_data[kategori_adi][koleksiyon_adi][takim_adi] = takim_urunler

    def populate_tree(self, filter_text=""):
        """Tree'yi gruplandırılmış şekilde doldur (Kategori -> Koleksiyon -> Etiket Listesi + Takımlar)"""
        # Tree'yi temizle
        self.tree.clear()
        self.koleksiyon_widgets = {}  # Widget referanslarını sıfırla
        self.takim_widgets = {}  # Takım widget referanslarını sıfırla

        # Filtre uygula
        filtered_data = self.table_data
        if filter_text:
            filter_lower = filter_text.lower()
            filtered_data = [
                row for row in self.table_data
                if (filter_lower in row['kategori'].lower() or
                    filter_lower in row['koleksiyon'].lower() or
                    filter_lower in row['sku'].lower() or
                    filter_lower in row['urun_adi'].lower() or
                    filter_lower in row['Malzeme_adi'].lower())
            ]

        # Kategorilere göre grupla
        from collections import defaultdict
        kategori_groups = defaultdict(lambda: defaultdict(list))

        for row_data in filtered_data:
            kategori = row_data['kategori']
            koleksiyon = row_data['koleksiyon']
            kategori_groups[kategori][koleksiyon].append(row_data)

        # Tree'ye ekle
        for kategori_adi in sorted(kategori_groups.keys()):
            # Kategori seviyesi
            kategori_item = QTreeWidgetItem(self.tree)
            kategori_item.setText(0, f"📂 {kategori_adi}")  # İlk sütuna yaz
            kategori_item.setExpanded(False)  # Başlangıçta kapalı

            # Kategori başlığını bold yap
            font = QFont()
            font.setBold(True)
            font.setPointSize(10)
            kategori_item.setFont(0, font)

            # Tüm kolonlara arka plan rengi ver
            for col in range(13):
                kategori_item.setBackground(col, QBrush(QColor("#ecf0f1")))

            # İlk kolonu tüm sütunlara yay (span) - doğru kullanım
            from PyQt5.QtCore import QModelIndex
            row_index = self.tree.indexOfTopLevelItem(kategori_item)
            self.tree.setFirstColumnSpanned(row_index, QModelIndex(), True)

            koleksiyonlar = kategori_groups[kategori_adi]

            for koleksiyon_adi in sorted(koleksiyonlar.keys()):
                # Koleksiyon seviyesi
                koleksiyon_item = QTreeWidgetItem(kategori_item)

                # Fiyat farkı olup olmadığını kontrol et
                urunler = koleksiyonlar[koleksiyon_adi]
                has_price_diff = False
                for row_data in urunler:
                    fark = abs(row_data['perakende_new'] - row_data['perakende'])
                    if fark > 7:
                        has_price_diff = True
                        break

                # JSON'dan mevcut değerleri oku
                exc_deger = False
                sube_deger = False

                if (self.json_data and
                    kategori_adi in self.json_data and
                    koleksiyon_adi in self.json_data[kategori_adi]):

                    koleksiyon_data = self.json_data[kategori_adi][koleksiyon_adi]
                    if 'etiket_listesi' in koleksiyon_data and 'takim_sku' in koleksiyon_data['etiket_listesi']:
                        takim_sku = koleksiyon_data['etiket_listesi']['takim_sku']

                        # String değerleri boolean'a çevir
                        exc_deger = takim_sku.get('excDeger', 'false').lower() == 'true'
                        sube_deger = takim_sku.get('subeDeger', 'false').lower() == 'true'

                # SEÇ kolonu - Checkbox (varsayılan olarak HER ZAMAN seçili)
                sec_checkbox = QCheckBox()
                sec_checkbox.setChecked(True)  # Her zaman seçili
                sec_widget = QWidget()
                sec_layout = QHBoxLayout(sec_widget)
                sec_layout.addWidget(sec_checkbox)
                sec_layout.setAlignment(Qt.AlignCenter)
                sec_layout.setContentsMargins(0, 0, 0, 0)
                self.tree.setItemWidget(koleksiyon_item, 0, sec_widget)

                # EXC kolonu - Checkbox (JSON'dan gelen değere göre)
                exc_checkbox = QCheckBox()
                exc_checkbox.setChecked(exc_deger)  # JSON'dan oku
                exc_widget = QWidget()
                exc_layout = QHBoxLayout(exc_widget)
                exc_layout.addWidget(exc_checkbox)
                exc_layout.setAlignment(Qt.AlignCenter)
                exc_layout.setContentsMargins(0, 0, 0, 0)
                self.tree.setItemWidget(koleksiyon_item, 1, exc_widget)

                # SUBE kolonu - Checkbox (JSON'dan gelen değere göre)
                sube_checkbox = QCheckBox()
                sube_checkbox.setChecked(sube_deger)  # JSON'dan oku
                sube_widget = QWidget()
                sube_layout = QHBoxLayout(sube_widget)
                sube_layout.addWidget(sube_checkbox)
                sube_layout.setAlignment(Qt.AlignCenter)
                sube_layout.setContentsMargins(0, 0, 0, 0)
                self.tree.setItemWidget(koleksiyon_item, 2, sube_widget)

                # Widget referanslarını sakla
                self.koleksiyon_widgets[(kategori_adi, koleksiyon_adi)] = {
                    'sec': sec_checkbox,
                    'exc': exc_checkbox,
                    'sube': sube_checkbox,
                    'has_price_diff': has_price_diff
                }

                # Kategori / KOLEKSIYON kolonu
                koleksiyon_item.setText(3, f"📁 {koleksiyon_adi}")
                koleksiyon_item.setExpanded(False)  # Başlangıçta kapalı

                # Koleksiyon başlığını bold yap
                font2 = QFont()
                font2.setBold(True)
                font2.setPointSize(9)
                koleksiyon_item.setFont(3, font2)

                # Fiyat farkı varsa koleksiyon başlığını kırmızı yap
                if has_price_diff:
                    koleksiyon_item.setBackground(3, QBrush(QColor("#ffcccc")))
                else:
                    koleksiyon_item.setBackground(3, QBrush(QColor("#d5dbdb")))

                # Etiket listesi ürünleri
                urunler = koleksiyonlar[koleksiyon_adi]
                for row_data in urunler:
                    # Fark hesaplama (satır renklendirme için)
                    fark = abs(row_data['perakende_new'] - row_data['perakende'])
                    satir_kirmizi = fark > 7

                    # Ürün satırı
                    urun_item = QTreeWidgetItem(koleksiyon_item)

                    # SEÇ, EXC, SUBE, Kategori/KOLEKSIYON, Takım kolonları boş
                    urun_item.setText(0, "")
                    urun_item.setText(1, "")
                    urun_item.setText(2, "")
                    urun_item.setText(3, "")
                    urun_item.setText(4, "")

                    # Miktar (etiket_listesi için boş - çünkü products[].miktar yok)
                    urun_item.setText(5, "")

                    # Malzeme Adı - Düzenlenebilir
                    urun_item.setText(6, row_data['Malzeme_adi'])
                    urun_item.setFlags(urun_item.flags() | Qt.ItemIsEditable)

                    # LISTE (JSON - liste_fiyat)
                    urun_item.setText(7, f"{row_data['liste']:,.0f}")

                    # PERAKENDE (JSON - perakende_fiyat)
                    urun_item.setText(8, f"{row_data['perakende']:,.0f}")

                    # Fark
                    urun_item.setText(9, f"{fark:,.2f}")

                    # LISTE_new (Excel)
                    urun_item.setText(10, f"{row_data['liste_new']:,.0f}")

                    # PERAKENDE_new (Excel)
                    urun_item.setText(11, f"{row_data['perakende_new']:,.0f}")

                    # sku (EN SON)
                    urun_item.setText(12, row_data['sku'])

                    # Kırmızı renklendirme
                    if satir_kirmizi:
                        for col in range(13):
                            urun_item.setBackground(col, QBrush(QColor("#ffcccc")))

                # Takımları ekle (koleksiyon altında)
                if kategori_adi in self.takim_data and koleksiyon_adi in self.takim_data[kategori_adi]:
                    takimlar = self.takim_data[kategori_adi][koleksiyon_adi]

                    for takim_adi in sorted(takimlar.keys()):
                        takim_urunler = takimlar[takim_adi]

                        if not takim_urunler:
                            continue

                        # Takım seviyesi (koleksiyon benzeri)
                        takim_item = QTreeWidgetItem(koleksiyon_item)

                        # Orijinal takım adını item'a kaydet (save sırasında kullanmak için)
                        takim_item.setData(0, Qt.UserRole, {
                            'kategori': kategori_adi,
                            'koleksiyon': koleksiyon_adi,
                            'orijinal_takim_adi': takim_adi
                        })

                        # Takım checkbox'ı ekle (varsayılan olarak işaretsiz)
                        takim_checkbox = QCheckBox()
                        takim_checkbox.setChecked(False)  # Varsayılan olarak işaretsiz
                        takim_checkbox_widget = QWidget()
                        takim_checkbox_layout = QHBoxLayout(takim_checkbox_widget)
                        takim_checkbox_layout.addWidget(takim_checkbox)
                        takim_checkbox_layout.setAlignment(Qt.AlignCenter)
                        takim_checkbox_layout.setContentsMargins(0, 0, 0, 0)
                        self.tree.setItemWidget(takim_item, 0, takim_checkbox_widget)

                        # Takım widget referansını sakla
                        self.takim_widgets[(kategori_adi, koleksiyon_adi, takim_adi)] = takim_checkbox

                        # Takım başlığı - "Takım" sütunu hizasında (kolon 4)
                        takim_item.setText(4, f"📁 {takim_adi}")
                        takim_item.setExpanded(False)  # Başlangıçta kapalı

                        # Takım adını düzenlenebilir yap
                        takim_item.setFlags(takim_item.flags() | Qt.ItemIsEditable)

                        # Takım başlığını bold ve koyu yap
                        font_takim = QFont()
                        font_takim.setBold(True)
                        font_takim.setPointSize(9)
                        takim_item.setFont(4, font_takim)

                        # Tüm kolonlara arka plan rengi ver
                        for col in range(13):
                            takim_item.setBackground(col, QBrush(QColor("#d5dbdb")))

                        # Takım ürünlerini ekle
                        for takim_urun in takim_urunler:
                            # Takım ürün satırı
                            takim_urun_item = QTreeWidgetItem(takim_item)

                            # SEÇ, EXC, SUBE, Kategori/KOLEKSIYON, Takım kolonları boş
                            takim_urun_item.setText(0, "")
                            takim_urun_item.setText(1, "")
                            takim_urun_item.setText(2, "")
                            takim_urun_item.setText(3, "")
                            takim_urun_item.setText(4, "")

                            # Miktar (products[].miktar) - Düzenlenebilir
                            takim_urun_item.setText(5, str(takim_urun['miktar']))
                            takim_urun_item.setFlags(takim_urun_item.flags() | Qt.ItemIsEditable)

                            # Malzeme Adı (urun_adi_tam) - Düzenlenebilir
                            takim_urun_item.setText(6, takim_urun['Malzeme_adi'])
                            takim_urun_item.setFlags(takim_urun_item.flags() | Qt.ItemIsEditable)

                            # LISTE, PERAKENDE, Fark, LISTE_new, PERAKENDE_new (takım ürünleri için boş)
                            takim_urun_item.setText(7, "")
                            takim_urun_item.setText(8, "")
                            takim_urun_item.setText(9, "")
                            takim_urun_item.setText(10, "")
                            takim_urun_item.setText(11, "")

                            # sku (EN SON)
                            takim_urun_item.setText(12, takim_urun['sku'])

        # Sütun genişliklerini ayarla
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # SEÇ

        # EXC sütunu - Sabit genişlik (Kategori metni genişliği etkilemesin)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        self.tree.setColumnWidth(1, 60)  # Sadece "EXC" genişliği kadar

        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # SUBE

        # Kategori/KOLEKSIYON sütunu - Fixed genişlik (ağaç yapısı genişliği etkilemesin)
        header.setSectionResizeMode(3, QHeaderView.Interactive)  # Kategori / KOLEKSIYON
        self.tree.setColumnWidth(3, 200)  # Sabit genişlik

        # Takım sütunu - Dinamik genişlik
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # Takım

        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)  # Miktar

        # Malzeme Adı sütunu - Dinamik genişlik
        header.setSectionResizeMode(6, QHeaderView.Stretch)  # Malzeme Adı

        header.setSectionResizeMode(7, QHeaderView.ResizeToContents)  # LISTE
        header.setSectionResizeMode(8, QHeaderView.ResizeToContents)  # PERAKENDE
        header.setSectionResizeMode(9, QHeaderView.ResizeToContents)  # Fark
        header.setSectionResizeMode(10, QHeaderView.ResizeToContents)  # LISTE_new
        header.setSectionResizeMode(11, QHeaderView.ResizeToContents)  # PERAKENDE_new
        header.setSectionResizeMode(12, QHeaderView.ResizeToContents)  # sku

    def filter_table(self, text):
        """Arama filtresini uygula"""
        self.populate_tree(text)

    def expand_partial(self):
        """Sadece kategorileri ve koleksiyonları genişlet, ürünleri değil"""
        root = self.tree.invisibleRootItem()

        # Tüm kategorileri genişlet
        for i in range(root.childCount()):
            kategori_item = root.child(i)
            kategori_item.setExpanded(True)

            # Her kategorinin altındaki koleksiyonları genişlet
            for j in range(kategori_item.childCount()):
                koleksiyon_item = kategori_item.child(j)
                koleksiyon_item.setExpanded(False)  # Koleksiyonların altındaki ürünler kapalı

    def expand_all(self):
        """Tüm kategorileri, koleksiyonları ve ürünleri genişlet"""
        self.tree.expandAll()

    def update_takim_data_from_tree(self, json_data):
        """Tree'deki takım güncellemelerini JSON'a uygula"""
        try:
            # Değişen takım adlarını sakla
            degisen_takimlar = []

            # Tree'yi tara
            root = self.tree.invisibleRootItem()

            for i in range(root.childCount()):
                kategori_item = root.child(i)
                # Kategori adını al (📂 prefix'ini kaldır)
                kategori_text = kategori_item.text(0)
                kategori_adi = kategori_text.replace("📂 ", "").strip()

                for j in range(kategori_item.childCount()):
                    koleksiyon_item = kategori_item.child(j)
                    # Koleksiyon adını al (📁 prefix'ini kaldır)
                    koleksiyon_text = koleksiyon_item.text(3)
                    koleksiyon_adi = koleksiyon_text.replace("📁 ", "").strip()

                    # JSON'da bu kategori ve koleksiyon var mı?
                    if kategori_adi not in json_data or koleksiyon_adi not in json_data[kategori_adi]:
                        continue

                    # Koleksiyon altındaki item'leri tara
                    for k in range(koleksiyon_item.childCount()):
                        item = koleksiyon_item.child(k)

                        # Takım mı kontrol et (kolon 4'te değer varsa)
                        takim_text = item.text(4)
                        # Emoji ile başlayıp başlamadığına bakmadan, kolon 4'te metin varsa takım olarak kabul et
                        if takim_text and len(takim_text.strip()) > 0:
                            # Bu bir takım item'i - tree'deki güncel ad
                            # Emoji varsa kaldır, yoksa olduğu gibi kullan
                            tree_takim_adi = takim_text.replace("📁 ", "").strip()

                            # Item'dan orijinal takım adını al
                            item_data = item.data(0, Qt.UserRole)

                            if not item_data or 'orijinal_takim_adi' not in item_data:
                                # Veri yoksa, tree'deki adı kullan
                                eski_takim_adi = tree_takim_adi
                            else:
                                eski_takim_adi = item_data['orijinal_takim_adi']

                            # JSON'da bu takım var mı kontrol et
                            if (kategori_adi not in json_data or
                                koleksiyon_adi not in json_data[kategori_adi] or
                                eski_takim_adi not in json_data[kategori_adi][koleksiyon_adi]):
                                continue

                            # Takım adı değişti mi?
                            if eski_takim_adi != tree_takim_adi:
                                # Takım adını güncelle (key değiştir)
                                takım_data = json_data[kategori_adi][koleksiyon_adi][eski_takim_adi]
                                json_data[kategori_adi][koleksiyon_adi][tree_takim_adi] = takım_data
                                del json_data[kategori_adi][koleksiyon_adi][eski_takim_adi]
                                guncel_takim_adi = tree_takim_adi

                                # Değişikliği kaydet
                                degisen_takimlar.append({
                                    'koleksiyon': koleksiyon_adi,
                                    'eski_ad': eski_takim_adi,
                                    'yeni_ad': tree_takim_adi
                                })
                            else:
                                guncel_takim_adi = eski_takim_adi

                            # Takım ürünlerini güncelle
                            takim_data = json_data[kategori_adi][koleksiyon_adi][guncel_takim_adi]
                            if 'products' in takim_data:
                                products = takim_data['products']

                                # Tree'deki takım ürünlerini al
                                for m in range(item.childCount()):
                                    urun_item = item.child(m)
                                    sku_text = urun_item.text(12)  # SKU kolonu
                                    miktar_text = urun_item.text(5)  # Miktar kolonu
                                    malzeme_adi_text = urun_item.text(6)  # Malzeme Adı kolonu

                                    if not sku_text:
                                        continue

                                    # Bu SKU'yu products içinde bul
                                    for product in products:
                                        if str(product.get('sku', '')) == sku_text:
                                            # Miktar güncelle
                                            try:
                                                yeni_miktar = int(miktar_text) if miktar_text else 1
                                                if product.get('miktar', 1) != yeni_miktar:
                                                    product['miktar'] = yeni_miktar
                                            except ValueError:
                                                pass  # Geçersiz miktar, değiştirme

                                            # Malzeme adını güncelle (urun_adi_tam)
                                            if malzeme_adi_text:
                                                if product.get('urun_adi_tam', '') != malzeme_adi_text.strip():
                                                    product['urun_adi_tam'] = malzeme_adi_text.strip()
                                            break

                        else:
                            # Bu bir etiket listesi ürünü (takım değil)
                            # SKU ve Malzeme Adı var mı kontrol et
                            sku_text = item.text(12)  # SKU kolonu
                            malzeme_adi_text = item.text(6)  # Malzeme Adı kolonu

                            if not sku_text or not malzeme_adi_text:
                                continue

                            # JSON'da etiket_listesi > urunler içinde bu SKU'yu bul ve güncelle
                            koleksiyon_data = json_data[kategori_adi][koleksiyon_adi]
                            if 'etiket_listesi' in koleksiyon_data and 'urunler' in koleksiyon_data['etiket_listesi']:
                                urunler = koleksiyon_data['etiket_listesi']['urunler']
                                for urun in urunler:
                                    if str(urun.get('sku', '')) == sku_text:
                                        # Malzeme adını güncelle (urun_adi_tam)
                                        if urun.get('urun_adi_tam') != malzeme_adi_text.strip():
                                            urun['urun_adi_tam'] = malzeme_adi_text.strip()
                                        break

            return degisen_takimlar

        except Exception as e:
            import traceback
            traceback.print_exc()
            return []

    def delete_selected_takimlar(self):
        """İşaretlenmiş takımları JSON dosyasından sil"""
        try:
            # İşaretlenmiş takımları bul
            selected_takimlar = []
            for (kategori_adi, koleksiyon_adi, takim_adi), checkbox in self.takim_widgets.items():
                if checkbox.isChecked():
                    selected_takimlar.append((kategori_adi, koleksiyon_adi, takim_adi))

            if not selected_takimlar:
                QMessageBox.warning(self, "Uyarı", "Lütfen silmek istediğiniz takımları işaretleyin!")
                return

            # Kullanıcıya onay sor
            takim_sayisi = len(selected_takimlar)
            mesaj = f"{takim_sayisi} takım silinecek. Emin misiniz?\n\n"
            mesaj += "\n".join([f"• {k} > {kol} > {t}" for k, kol, t in selected_takimlar[:5]])
            if takim_sayisi > 5:
                mesaj += f"\n... ve {takim_sayisi - 5} takım daha"

            reply = QMessageBox.question(
                self,
                "Takım Silme Onayı",
                mesaj,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if reply != QMessageBox.Yes:
                return

            self.status_label.setText("🗑 Takımlar siliniyor...")
            QApplication.processEvents()

            # JSON dosyasını oku
            with open(self.json_file, 'r', encoding='utf-8') as f:
                json_data = json.load(f)

            # Seçili takımları sil
            silinen_sayisi = 0
            for kategori_adi, koleksiyon_adi, takim_adi in selected_takimlar:
                if (kategori_adi in json_data and
                    koleksiyon_adi in json_data[kategori_adi] and
                    takim_adi in json_data[kategori_adi][koleksiyon_adi]):

                    # Takımı sil
                    del json_data[kategori_adi][koleksiyon_adi][takim_adi]
                    silinen_sayisi += 1

            # JSON dosyasını kaydet
            with open(self.json_file, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, ensure_ascii=False, indent=2)

            self.status_label.setText(f"✅ {silinen_sayisi} takım başarıyla silindi")
            QMessageBox.information(self, "Başarılı", f"{silinen_sayisi} takım başarıyla silindi!")

            # Verileri yeniden yükle
            self.load_data()

        except Exception as e:
            error_msg = f"Takım silme hatası: {str(e)}"
            self.status_label.setText(f"❌ {error_msg}")
            QMessageBox.critical(self, "Hata", error_msg)

    def delete_unselected_koleksiyonlar(self):
        """SEÇ checkbox'ı işaretli OLMAYAN koleksiyonları JSON dosyasından sil"""
        try:
            # İşaretli OLMAYAN koleksiyonları bul
            unselected_koleksiyonlar = []
            for (kategori_adi, koleksiyon_adi), widgets in self.koleksiyon_widgets.items():
                if not widgets['sec'].isChecked():  # İşaretli değilse
                    unselected_koleksiyonlar.append((kategori_adi, koleksiyon_adi))

            if not unselected_koleksiyonlar:
                QMessageBox.warning(self, "Uyarı", "Tüm koleksiyonlar kullanımda (SEÇ işaretli)!\nSilmek için önce SEÇ işaretini kaldırın.")
                return

            # Kullanıcıya onay sor
            koleksiyon_sayisi = len(unselected_koleksiyonlar)
            mesaj = f"{koleksiyon_sayisi} koleksiyon (kullanılmayan) silinecek. Emin misiniz?\n\n"
            mesaj += "⚠️ DİKKAT: Koleksiyona ait TÜM veriler (etiket listesi + takımlar) silinecek!\n\n"
            mesaj += "\n".join([f"• {k} > {kol}" for k, kol in unselected_koleksiyonlar[:10]])
            if koleksiyon_sayisi > 10:
                mesaj += f"\n... ve {koleksiyon_sayisi - 10} koleksiyon daha"

            reply = QMessageBox.question(
                self,
                "Koleksiyon Silme Onayı",
                mesaj,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if reply != QMessageBox.Yes:
                return

            self.status_label.setText("🗑 Koleksiyonlar siliniyor...")
            QApplication.processEvents()

            # JSON dosyasını oku
            with open(self.json_file, 'r', encoding='utf-8') as f:
                json_data = json.load(f)

            # Seçili olmayan koleksiyonları sil
            silinen_sayisi = 0
            for kategori_adi, koleksiyon_adi in unselected_koleksiyonlar:
                if (kategori_adi in json_data and
                    koleksiyon_adi in json_data[kategori_adi]):

                    # Koleksiyonu tamamen sil (etiket_listesi + tüm takımlar)
                    del json_data[kategori_adi][koleksiyon_adi]
                    silinen_sayisi += 1

                    # Eğer kategori boş kaldıysa kategoriyi de sil
                    if not json_data[kategori_adi]:
                        del json_data[kategori_adi]

            # JSON dosyasını kaydet
            with open(self.json_file, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, ensure_ascii=False, indent=2)

            self.status_label.setText(f"✅ {silinen_sayisi} koleksiyon başarıyla silindi")
            QMessageBox.information(self, "Başarılı", f"{silinen_sayisi} koleksiyon başarıyla silindi!")

            # Verileri yeniden yükle
            self.load_data()

        except Exception as e:
            error_msg = f"Koleksiyon silme hatası: {str(e)}"
            self.status_label.setText(f"❌ {error_msg}")
            QMessageBox.critical(self, "Hata", error_msg)

    def save_data(self):
        """JSON dosyasını radio buton durumlarına ve yeni fiyatlara göre güncelle"""
        try:
            self.status_label.setText("💾 Veriler kaydediliyor...")
            QApplication.processEvents()

            # Mevcut düzenlemeyi tamamla (pending edits)
            # Kullanıcı bir hücreyi düzenlerken kaydet basarsa, o düzenlemeyi commit et
            current_item = self.tree.currentItem()
            if current_item:
                current_column = self.tree.currentColumn()
                if current_column >= 0:
                    # Düzenleme modundaysa kapat
                    self.tree.closePersistentEditor(current_item, current_column)

            # Tree'nin focus'unu kaldır (tüm pending değişiklikleri commit eder)
            self.tree.clearFocus()
            QApplication.processEvents()

            # JSON dosyasını oku
            with open(self.json_file, 'r', encoding='utf-8') as f:
                json_data = json.load(f)

            # Şu anki tarih-saat
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Her kategori ve koleksiyon için
            for (kategori_adi, koleksiyon_adi), widgets in self.koleksiyon_widgets.items():
                # Checkbox durumlarını al
                sec_checked = widgets['sec'].isChecked()
                exc_checked = widgets['exc'].isChecked()
                sube_checked = widgets['sube'].isChecked()

                # JSON'daki ilgili koleksiyona eriş
                if kategori_adi not in json_data:
                    continue
                if koleksiyon_adi not in json_data[kategori_adi]:
                    continue

                koleksiyon_data = json_data[kategori_adi][koleksiyon_adi]

                # etiket_listesi > takim_sku altına secDeger, excDeger, subeDeger ekle/güncelle
                if 'etiket_listesi' in koleksiyon_data and 'takim_sku' in koleksiyon_data['etiket_listesi']:
                    takim_sku = koleksiyon_data['etiket_listesi']['takim_sku']
                    takim_sku['secDeger'] = "true" if sec_checked else "false"
                    takim_sku['excDeger'] = "true" if exc_checked else "false"
                    takim_sku['subeDeger'] = "true" if sube_checked else "false"

                    # Fiyat güncellemelerini yap (sadece SEÇ işaretli olanlar için ve fiyat farkı varsa)
                    if sec_checked and widgets['has_price_diff']:
                        # etiket_listesi > urunler içindeki SKU'ları güncelle
                        if 'urunler' in koleksiyon_data['etiket_listesi']:
                            urunler = koleksiyon_data['etiket_listesi']['urunler']
                            for urun in urunler:
                                sku = str(urun.get('sku', ''))
                                # Excel'den yeni fiyatları al
                                price_info = self.price_loader.get_price(sku) if self.price_loader else None
                                if price_info:
                                    # Sadece mutlak değer farkı 7'den büyükse güncelle
                                    old_perakende = urun.get('perakende_fiyat', 0.0)
                                    new_perakende = price_info['perakende']
                                    if abs(new_perakende - old_perakende) > 7:
                                        urun['liste_fiyat'] = price_info['liste']
                                        urun['perakende_fiyat'] = price_info['perakende']

                        # takim_sku fiyatlarını yeniden hesapla
                        total_liste = 0.0
                        total_perakende = 0.0
                        if 'urunler' in koleksiyon_data['etiket_listesi']:
                            for urun in koleksiyon_data['etiket_listesi']['urunler']:
                                total_liste += urun.get('liste_fiyat', 0.0)
                                total_perakende += urun.get('perakende_fiyat', 0.0)

                        takim_sku['liste_fiyat'] = round(total_liste, 2)
                        takim_sku['perakende_fiyat'] = round(total_perakende, 2)

                        # indirim_yuzde hesapla
                        if total_liste > 0:
                            indirim_yuzde = round(((total_liste - total_perakende) / total_liste) * 100)
                            takim_sku['indirim_yuzde'] = indirim_yuzde
                        else:
                            takim_sku['indirim_yuzde'] = 0

                        # updated_at güncelle
                        takim_sku['updated_at'] = current_time

                # Özel takım adlarının fiyatlarını güncelle (SEÇ işaretli olanlar için ve fiyat farkı varsa)
                if sec_checked and widgets['has_price_diff']:
                    # etiket_listesi dışındaki tüm takımları bul ve fiyatlarını güncelle
                    for key, value in koleksiyon_data.items():
                        if key != 'etiket_listesi' and isinstance(value, dict) and 'products' in value:
                            # Bu bir özel takım adı
                            products = value.get('products', [])

                            # Takım için toplam fiyatları hesapla
                            total_liste = 0.0
                            total_perakende = 0.0

                            for product in products:
                                product_sku = str(product.get('sku', ''))
                                product_miktar = product.get('miktar', 1)

                                # Excel'den yeni fiyatları al
                                price_info = self.price_loader.get_price(product_sku) if self.price_loader else None
                                if price_info:
                                    # Fiyatları miktar ile çarp ve topla
                                    total_liste += price_info['liste'] * product_miktar
                                    total_perakende += price_info['perakende'] * product_miktar

                            # Toplam fiyatları güncelle
                            value['total_liste_price'] = round(total_liste, 2)
                            value['total_perakende_price'] = round(total_perakende, 2)

                            # İndirim yüzdesini hesapla
                            if total_liste > 0:
                                indirim_yuzde = round(((total_liste - total_perakende) / total_liste) * 100)
                                value['total_indirim_yuzde'] = indirim_yuzde
                            else:
                                value['total_indirim_yuzde'] = 0

            # Takım güncellemelerini yap (Takım adı, Miktar, Malzeme Adı)
            degisen_takimlar = self.update_takim_data_from_tree(json_data)

            # JSON dosyasını kaydet
            with open(self.json_file, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, ensure_ascii=False, indent=2)

            self.status_label.setText(f"✅ Veriler başarıyla kaydedildi: {current_time}")

            # Başarı mesajı
            mesaj = "Veriler başarıyla kaydedildi!"

            # Değişen takımlar varsa göster
            if degisen_takimlar:
                mesaj += f"\n\n📝 Değişen Takım Adları ({len(degisen_takimlar)}):\n\n"
                for dt in degisen_takimlar:
                    mesaj += f"▪ {dt['koleksiyon']}\n"
                    mesaj += f"  Eski: {dt['eski_ad']}\n"
                    mesaj += f"  Yeni: {dt['yeni_ad']}\n\n"

            QMessageBox.information(self, "Başarılı", mesaj)

            # Verileri yeniden yükle
            self.load_data()

        except Exception as e:
            error_msg = f"Kaydetme hatası: {str(e)}"
            self.status_label.setText(f"❌ {error_msg}")
            QMessageBox.critical(self, "Hata", error_msg)


def main():
    """Standalone test için"""
    app = QApplication(sys.argv)
    window = QMainWindow()
    window.setWindowTitle("JSON ve Excel Karşılaştırma")
    window.setGeometry(100, 100, 1400, 800)

    widget = JsonGosterWidget()
    window.setCentralWidget(widget)
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
