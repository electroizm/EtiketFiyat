"""
Doğtaş Etiket Listesi - Ürün seçimi ve etiket oluşturma
"""

import sys
import os
import re
import json
from datetime import datetime
from pathlib import Path
import warnings
import pandas as pd
import numpy as np
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                             QLabel, QApplication, QMainWindow, QFrame,
                             QTableWidget, QTableWidgetItem, QLineEdit, QCheckBox,
                             QComboBox, QMessageBox, QHeaderView, QRadioButton, QButtonGroup,
                             QListWidget, QAbstractItemView)
from PyQt5.QtGui import QFont, QColor
import logging

warnings.filterwarnings('ignore')


def get_base_dir():
    """Exe veya script dizinini döndür"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


class EtiketListesiWindow(QMainWindow):
    """Etiket Listesi penceresi - stok_module.py ve ssh_module.py stilinde"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Etiket Listesi")

        # Data
        self.original_data = []
        self.filtered_data = []
        self.current_kategori = None
        self.current_koleksiyon = None
        self.current_takim = None

        # Checkbox ve miktar durumlarını saklamak için (SKU bazında)
        self.checked_state = {}  # {sku: True/False}
        self.miktar_state = {}   # {sku: "miktar"}

        # JSON dosya yolu
        self.json_file = os.path.join(get_base_dir(), "etiketEkle.json")

        # Yatak Odası takım kombinasyonları tanımlamaları (Regex pattern'ler)
        self.yatak_odasi_kombinasyonlari = {
            "6 Kapaklı, Karyola": {
                "aranacak_urunler": [
                    r"(?i)\b6\s*kapak(lı)?\b",
                    r'(?i)(?=.*ba(ş|s)l(ı|i)k)(?=.*160)',
                    r"(?i)^(?!.*180)(?!.*Baza)(?!.*Başlıklı).*Karyola.*160.*$",
                    r"(?i)^(?!.*ayna)(?!.*ikili)(?!.*dar)(?!.*yüksek)(?=.*şifonyer).*$",
                    r"(?i)^(?=.*ayna)(?=.*(konsol|şifonyer)).*$",
                    r"(?i)(?=.*kom[oi]din)(?=.*(çift|çekmece))?"

                ],
                "adet": {r"(?i)(?=.*kom[oi]din)(?=.*(çift|çekmece))?": 2}
            },
            "6 Kapaklı, Baza": {
                "aranacak_urunler": [
                    r"(?i)\b6\s*kapak(lı)?\b",
                    r'(?i)(?=.*ba(ş|s)l(ı|i)k)(?=.*160)',
                    r"(?i)^(?!.*başlıklı)(?=.*baza)(?=.*160).*$",
                    r"(?i)^(?!.*ayna)(?!.*ikili)(?!.*dar)(?!.*yüksek)(?=.*şifonyer).*$",
                    r"(?i)^(?=.*ayna)(?=.*(konsol|şifonyer)).*$",
                    r"(?i)(?=.*kom[oi]din)(?=.*(çift|çekmece))?"
                ],
                "adet": {r"(?i)(?=.*kom[oi]din)(?=.*(çift|çekmece))?": 2}
            },
            "5 Kapaklı, Karyola": {
                "aranacak_urunler": [
                    r"(?i)\b5\s*kapak(lı)?\b",
                    r'(?i)(?=.*ba(ş|s)l(ı|i)k)(?=.*160)',
                    r"(?i)^(?!.*180)(?!.*Baza)(?!.*Başlıklı).*Karyola.*160.*$",
                    r"(?i)^(?!.*ayna)(?!.*ikili)(?!.*dar)(?!.*yüksek)(?=.*şifonyer).*$",
                    r"(?i)^(?=.*ayna)(?=.*(konsol|şifonyer)).*$",
                    r"(?i)(?=.*kom[oi]din)(?=.*(çift|çekmece))?"
                ],
                "adet": {r"(?i)(?=.*kom[oi]din)(?=.*(çift|çekmece))?": 2}
            },
            "5 Kapaklı, Baza": {
                "aranacak_urunler": [
                    r"(?i)\b5\s*kapak(lı)?\b",
                    r'(?i)(?=.*ba(ş|s)l(ı|i)k)(?=.*160)',
                    r"(?i)^(?!.*başlıklı)(?=.*baza)(?=.*160).*$",
                    r"(?i)^(?!.*ayna)(?!.*ikili)(?!.*dar)(?!.*yüksek)(?=.*şifonyer).*$",
                    r"(?i)^(?=.*ayna)(?=.*(konsol|şifonyer)).*$",
                    r"(?i)(?=.*kom[oi]din)(?=.*(çift|çekmece))?"
                ],

                "adet": {r"(?i)(?=.*kom[oi]din)(?=.*(çift|çekmece))?": 2}
            }
        }

        # Yemek Odası takım kombinasyonları tanımlamaları (Regex pattern'ler)
        self.yemek_odasi_kombinasyonlari = {
            "Konsol, Açılır, Sandalye*6": {
                "aranacak_urunler": [
                    r"(?i)^(?!.*ayna)(?!.*mini)(?=.*konsol).*$",
                    r"(?i)^(?=.*ayna)(?=.*(konsol|şifonyer)).*$",
                    r"(?i)^(?!.*sabit)(?=.*yemek)(?=.*açılır).*$",
                    r"(?i)^(?!.*kol)(?=.*(sandalye|sand\.)).*$"
                ],
                "adet": {r"(?i)^(?!.*kol)(?=.*(sandalye|sand\.)).*$": 6}
            },
            "Konsol, Sabit, Sandalye*6": {
                "aranacak_urunler": [
                    r"(?i)^(?!.*ayna)(?!.*mini)(?=.*konsol).*$",
                    r"(?i)^(?=.*ayna)(?=.*(konsol|şifonyer)).*$",
                    r"(?i)^(?!.*açılır)(?=.*yemek)(?=.*sabit).*$",
                    r"(?i)^(?!.*kol)(?=.*(sandalye|sand\.)).*$"
                ],
                "adet": {r"(?i)^(?!.*kol)(?=.*(sandalye|sand\.)).*$": 6}
            },
            "Açılır, Sandalye*6": {
                "aranacak_urunler": [
                    r"(?i)^(?!.*sabit)(?=.*yemek)(?=.*açılır).*$",
                    r"(?i)^(?!.*kol)(?=.*(sandalye|sand\.)).*$"
                ],
                "adet": {r"(?i)^(?!.*kol)(?=.*(sandalye|sand\.)).*$": 6}
            },
            "Sabit, Sandalye*6": {
                "aranacak_urunler": [
                    r"(?i)^(?!.*açılır)(?=.*yemek)(?=.*sabit).*$",
                    r"(?i)^(?!.*kol)(?=.*(sandalye|sand\.)).*$"
                ],
                "adet": {r"(?i)^(?!.*kol)(?=.*(sandalye|sand\.)).*$": 6}
            }
        }

        # Oturma Grubu takım kombinasyonları tanımlamaları (Regex pattern'ler)
        self.oturma_grubu_kombinasyonlari = {
            "Üçlü*2, Berjer*2": {
                "aranacak_urunler": [
                    r"(?i)^(?=.*(berjer|tekli)).*$",
                    r"(?i)^(?=.*(üçlü)).*$"
                ],
                "adet": {
                    r"(?i)^(?=.*(berjer|tekli)).*$": 2,
                    r"(?i)^(?=.*(üçlü)).*$": 2
                }
            }
        }

        # Genç Odası takım kombinasyonları tanımlamaları (Regex pattern'ler)
        self.genc_odasi_kombinasyonlari = {
            "3 Kapaklı, 100 Karyola, Çalışma Masası": {
                "aranacak_urunler": [
                    r"(?i).*(3\s*kapa|3\s*kapı).*dolap.*",
                    r"(?i)^(?=.*(ba(ş|s)l(ı|i)k|100))(?!.*başlıksız)(?!.*karyola).*",
                    r"(?i)^(?=.*karyola)(?=.*100)(?!.*baza)(?=.*(başlıksız|kasa))?.*",
                    r"(?i)^(?=.*(çalışma|calısma))(?=.*masa)(?!.*üst)(?!.*modül)(?!.*eko)(?!.*kompakt).*"
                ]
            },
            "3 Kapaklı, 100 Baza, Çalışma Masası": {
                "aranacak_urunler": [
                    r"(?i).*(3\s*kapa|3\s*kapı).*dolap.*",
                    r"(?i)^(?=.*(başlık|100))(?!.*başlıksız)(?!.*karyola).*",
                    r"(?i)^(?=.*baza)(?=.*100).*",
                    r"(?i)^(?=.*(çalışma|calısma))(?=.*masa)(?!.*üst)(?!.*modül)(?!.*eko)(?!.*kompakt).*"
                ]
            }
        }

        # UI setup
        self.setup_ui()
        self.load_data()

        # Pencereyi tam ekran yap
        self.showMaximized()

    def setup_ui(self):
        """UI bileşenlerini oluştur"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Beyaz arka plan
        central_widget.setStyleSheet("""
            QWidget {
                background-color: #ffffff;
                color: #000000;
            }
        """)

        main_layout = QVBoxLayout(central_widget)

        # Arama kutusu + Temizle butonu
        search_layout = QHBoxLayout()

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Ürün Adı / SKU Ara...")
        self.search_box.setStyleSheet("""
            font-size: 16px;
            padding: 14px;
            border-radius: 5px;
            border: 1px solid #444;
            font-weight: bold;
        """)
        self.search_box.textChanged.connect(self.schedule_filter)

        # Temizle butonu
        clear_btn = QPushButton("Temizle")
        clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #dfdfdf;
                color: black;
                border: 1px solid #444;
                border-radius: 5px;
                padding: 8px 16px;
                font-size: 14px;
                font-weight: bold;
                min-width: 100px;
            }
            QPushButton:hover {
                background-color: #a0a5a2;
            }
        """)
        clear_btn.clicked.connect(self.clear_search)

        search_layout.addWidget(self.search_box, 1)
        search_layout.addWidget(clear_btn)
        main_layout.addLayout(search_layout)

        # Kategori ve Koleksiyon ComboBox'ları (yan yana)
        combo_layout = QHBoxLayout()
        combo_layout.setContentsMargins(0, 10, 0, 10)
        combo_layout.setSpacing(20)

        # Kategori ComboBox
        kategori_label = QLabel("Kategori:")
        kategori_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        combo_layout.addWidget(kategori_label)

        self.kategori_combo = QComboBox()
        self.kategori_combo.setStyleSheet("""
            QComboBox {
                font-size: 13px;
                font-weight: bold;
                padding: 5px;
                border: 1px solid #444;
                border-radius: 3px;
                min-width: 150px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox QAbstractItemView {
                font-size: 13px;
                font-weight: bold;
                selection-background-color: #007acc;
            }
        """)
        self.kategori_combo.addItem("")  # Boş seçenek
        self.kategori_combo.currentTextChanged.connect(self.on_kategori_selected)
        combo_layout.addWidget(self.kategori_combo)

        # Kategori manuel input
        self.kategori_input = QLineEdit()
        self.kategori_input.setPlaceholderText("Manuel Kategori...")
        self.kategori_input.setStyleSheet("""
            QLineEdit {
                font-size: 13px;
                padding: 5px;
                border: 1px solid #444;
                border-radius: 3px;
                min-width: 150px;
            }
        """)
        self.kategori_input.textChanged.connect(self.on_kategori_input_changed)
        combo_layout.addWidget(self.kategori_input)

        # Koleksiyon ComboBox
        koleksiyon_label = QLabel("Koleksiyon:")
        koleksiyon_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        combo_layout.addWidget(koleksiyon_label)

        self.koleksiyon_combo = QComboBox()
        self.koleksiyon_combo.setStyleSheet("""
            QComboBox {
                font-size: 13px;
                font-weight: bold;
                padding: 5px;
                border: 1px solid #444;
                border-radius: 3px;
                min-width: 150px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox QAbstractItemView {
                font-size: 13px;
                font-weight: bold;
                selection-background-color: #007acc;
            }
        """)
        self.koleksiyon_combo.addItem("")  # Boş seçenek
        self.koleksiyon_combo.currentTextChanged.connect(self.on_koleksiyon_selected)
        combo_layout.addWidget(self.koleksiyon_combo)

        # Koleksiyon manuel input
        self.koleksiyon_input = QLineEdit()
        self.koleksiyon_input.setPlaceholderText("Manuel Koleksiyon...")
        self.koleksiyon_input.setStyleSheet("""
            QLineEdit {
                font-size: 13px;
                padding: 5px;
                border: 1px solid #444;
                border-radius: 3px;
                min-width: 150px;
            }
        """)
        self.koleksiyon_input.textChanged.connect(self.on_koleksiyon_input_changed)
        combo_layout.addWidget(self.koleksiyon_input)

        combo_layout.addStretch()
        main_layout.addLayout(combo_layout)

        # Ayırıcı çizgi (başlangıçta gizli)
        self.separator = QFrame()
        self.separator.setFrameShape(QFrame.HLine)
        self.separator.setFrameShadow(QFrame.Sunken)
        self.separator.setStyleSheet("background-color: #cccccc;")
        self.separator.setMinimumHeight(2)
        self.separator.hide()
        main_layout.addWidget(self.separator)

        # Takım Seçimi Radio Butonları (başlangıçta gizli)
        self.takim_secim_widget = QWidget()
        takim_secim_layout = QHBoxLayout(self.takim_secim_widget)
        takim_secim_layout.setContentsMargins(0, 10, 0, 10)

        takim_label = QLabel("Takım Seçimi:")
        takim_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #007acc;")
        takim_secim_layout.addWidget(takim_label)

        # Radio button grubu
        self.takim_button_group = QButtonGroup()
        self.takim_radios = {}

        takimlar = ["6 Kapaklı, Karyola", "6 Kapaklı, Baza", "5 Kapaklı, Karyola", "5 Kapaklı, Baza"]
        for i, takim_adi in enumerate(takimlar):
            radio = QRadioButton(takim_adi)
            radio.setStyleSheet("""
                QRadioButton {
                    font-size: 13px;
                    font-weight: bold;
                    color: #000000;
                    padding: 3px;
                }
                QRadioButton::indicator {
                    width: 16px;
                    height: 16px;
                }
            """)
            self.takim_button_group.addButton(radio, i)
            self.takim_radios[takim_adi] = radio
            takim_secim_layout.addWidget(radio)

        # Özel isim için radio + text input
        self.custom_takim_radio = QRadioButton()
        self.custom_takim_radio.setStyleSheet("""
            QRadioButton {
                font-size: 13px;
                font-weight: bold;
                color: #000000;
                padding: 3px;
            }
            QRadioButton::indicator {
                width: 16px;
                height: 16px;
            }
        """)
        self.takim_button_group.addButton(self.custom_takim_radio, len(takimlar))

        self.custom_takim_input = QLineEdit()
        self.custom_takim_input.setPlaceholderText("Özel takım adı...")
        self.custom_takim_input.setMaximumWidth(360)
        self.custom_takim_input.setStyleSheet("""
            font-size: 13px;
            padding: 5px;
            border: 1px solid #444;
            border-radius: 3px;
        """)
        self.custom_takim_input.textChanged.connect(self.on_custom_takim_changed)

        takim_secim_layout.addWidget(self.custom_takim_radio)
        takim_secim_layout.addWidget(self.custom_takim_input)

        # Radio button değişikliğini dinle
        self.takim_button_group.buttonClicked.connect(self.on_takim_secim_changed)

        takim_secim_layout.addStretch()
        self.takim_secim_widget.hide()  # Başlangıçta gizli
        main_layout.addWidget(self.takim_secim_widget)

        # Seçili satır sayacı + Kaydet butonları
        button_layout = QHBoxLayout()

        # Seçim kontrol radio butonları grubu
        self.selection_button_group = QButtonGroup()

        # Hiçbiri radio butonu
        self.clear_all_radio = QRadioButton("Hiçbiri")
        self.clear_all_radio.setStyleSheet("""
            QRadioButton {
                font-size: 13px;
                font-weight: bold;
                padding: 5px;
            }
            QRadioButton::indicator {
                width: 18px;
                height: 18px;
            }
        """)
        self.clear_all_radio.clicked.connect(self.clear_all_checkboxes)
        self.selection_button_group.addButton(self.clear_all_radio)
        button_layout.addWidget(self.clear_all_radio)

        # Tümü radio butonu
        self.select_all_radio = QRadioButton("Tümü")
        self.select_all_radio.setStyleSheet("""
            QRadioButton {
                font-size: 13px;
                font-weight: bold;
                padding: 5px;
            }
            QRadioButton::indicator {
                width: 18px;
                height: 18px;
            }
        """)
        self.select_all_radio.clicked.connect(self.select_all_checkboxes)
        self.selection_button_group.addButton(self.select_all_radio)
        button_layout.addWidget(self.select_all_radio)

        # Seçili satır sayacı
        self.selected_count_label = QLabel("Seçili: 0")
        self.selected_count_label.setStyleSheet("""
            QLabel {
                color: #007acc;
                font-size: 14px;
                font-weight: bold;
                padding: 8px 16px;
                background-color: #f0f0f0;
                border-radius: 5px;
                border: 2px solid #007acc;
            }
        """)
        button_layout.addWidget(self.selected_count_label)

        button_layout.addStretch()

        # Etiket Listesi Kaydet butonu (Excel + JSON etiket_listesi)
        save_etiket_btn = QPushButton("Etiket Listesi Kaydet")
        save_etiket_btn.setToolTip("Seçili ürünleri Excel'e ve JSON'a 'etiket_listesi' olarak kaydeder")
        save_etiket_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 8px 16px;
                font-size: 14px;
                font-weight: bold;
                min-width: 180px;
            }
            QPushButton:hover {
                background-color: #34ce57;
            }
            QPushButton:pressed {
                background-color: #1e7e34;
            }
        """)
        save_etiket_btn.clicked.connect(self.save_etiket_listesi)

        # Takım Seçimi Kaydet butonu (JSON, sadece takım seçimi)
        save_json_btn = QPushButton("Takım Seçimi Kaydet (JSON)")
        save_json_btn.setToolTip("Takım seçimini JSON'a kaydeder (Etiket listesi gerekli)")
        save_json_btn.setStyleSheet("""
            QPushButton {
                background-color: #6f42c1;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 8px 16px;
                font-size: 14px;
                font-weight: bold;
                min-width: 120px;
            }
            QPushButton:hover {
                background-color: #8558d3;
            }
            QPushButton:pressed {
                background-color: #5a32a3;
            }
        """)
        save_json_btn.clicked.connect(self.save_selection_to_json)

        button_layout.addWidget(save_etiket_btn)
        button_layout.addWidget(save_json_btn)
        button_layout.addStretch()

        main_layout.addLayout(button_layout)

        # Tablo
        self.table = QTableWidget()
        self.table.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.EditKeyPressed)
        self.table.verticalHeader().setDefaultSectionSize(
            self.table.verticalHeader().defaultSectionSize() + 2
        )
        self.table.setStyleSheet("""
            QTableWidget {
                font-size: 15px;
                font-weight: bold;
            }
        """)
        main_layout.addWidget(self.table)

        # Status label
        self.status_label = QLabel("Hazır")
        self.status_label.setStyleSheet("""
            QLabel {
                color: #000000;
                padding: 8px;
                background-color: #f0f0f0;
                border-top: 1px solid #cccccc;
                font-size: 13px;
                font-weight: bold;
            }
        """)
        main_layout.addWidget(self.status_label)

        # Filter timer (debounce için)
        self.filter_timer = QTimer()
        self.filter_timer.setSingleShot(True)
        self.filter_timer.timeout.connect(self.filter_data)

    def load_data(self):
        """Lokal Excel dosyasından verileri yükle"""
        try:
            self.status_label.setText("🔄 Veriler yükleniyor...")
            QApplication.processEvents()

            # Lokal Excel dosyası yolu
            excel_file = os.path.join(get_base_dir(), "dogtasCom.xlsx")

            if not os.path.exists(excel_file):
                self.status_label.setText(f"❌ Excel dosyası bulunamadı: {excel_file}")
                QMessageBox.warning(self, "Uyarı", f"Excel dosyası bulunamadı:\n{excel_file}")
                return

            # Sheet1 sayfasını oku
            df = pd.read_excel(excel_file, sheet_name="Sheet1")

            # DataFrame'i listeye çevir
            self.original_data = df.to_dict('records')

            # Kategori radio butonlarını oluştur
            self.populate_kategori_radios()

            # Tabloyu güncelle
            self.filtered_data = self.original_data.copy()
            self.update_table()

            self.status_label.setText(f"✅ {len(self.original_data)} kayıt yüklendi")

        except Exception as e:
            error_msg = f"Veri yükleme hatası: {str(e)}"
            logging.error(error_msg)
            self.status_label.setText(f"❌ {error_msg}")
            QMessageBox.critical(self, "Hata", error_msg)

    def populate_kategori_radios(self):
        """Kategorileri ComboBox olarak doldur"""
        # Kategorileri topla
        kategoriler = set()
        for row in self.original_data:
            if 'kategori' in row and row['kategori']:
                kategoriler.add(str(row['kategori']))

        # Kategori ComboBox'ını doldur
        self.kategori_combo.blockSignals(True)
        self.kategori_combo.clear()
        self.kategori_combo.addItem("")  # Boş seçenek
        for kategori in sorted(kategoriler):
            self.kategori_combo.addItem(kategori)
        self.kategori_combo.blockSignals(False)

    def on_kategori_selected(self, kategori):
        """Kategori seçildiğinde çağrılır"""
        if not kategori or kategori.strip() == "":
            self.current_kategori = None
            self.koleksiyon_combo.clear()
            self.koleksiyon_combo.addItem("")
            self.separator.hide()
            self.takim_secim_widget.hide()
            self.filter_data()
            return

        self.current_kategori = kategori

        # Manuel input'u temizle
        self.kategori_input.blockSignals(True)
        self.kategori_input.clear()
        self.kategori_input.blockSignals(False)

        # Koleksiyon ComboBox'ını güncelle
        self.update_koleksiyon_list(kategori)

        # Takım seçimi ve ayırıcıyı gizle
        self.separator.hide()
        self.takim_secim_widget.hide()

        # Veriyi filtrele
        self.filter_data()

    def update_koleksiyon_list(self, kategori):
        """Seçilen kategoriye göre koleksiyon ComboBox'ını güncelle"""
        # Koleksiyonları topla
        koleksiyonlar = set()
        for row in self.original_data:
            if 'kategori' in row and str(row['kategori']) == kategori:
                if 'KOLEKSIYON' in row and row['KOLEKSIYON']:
                    koleksiyon = str(row['KOLEKSIYON']).strip()
                    if koleksiyon:
                        koleksiyonlar.add(koleksiyon)

        # Koleksiyon ComboBox'ını doldur
        self.koleksiyon_combo.blockSignals(True)
        self.koleksiyon_combo.clear()
        self.koleksiyon_combo.addItem("")  # Boş seçenek
        for koleksiyon in sorted(koleksiyonlar):
            self.koleksiyon_combo.addItem(koleksiyon)
        self.koleksiyon_combo.blockSignals(False)

    def on_koleksiyon_selected(self, koleksiyon):
        """Koleksiyon seçildiğinde çağrılır"""
        if not koleksiyon or koleksiyon.strip() == "":
            self.current_koleksiyon = None
            self.separator.hide()
            self.takim_secim_widget.hide()
            self.filter_data()
            return

        self.current_koleksiyon = koleksiyon
        self.current_takim = None  # Takım seçimini sıfırla

        # Manuel input'u temizle
        self.koleksiyon_input.blockSignals(True)
        self.koleksiyon_input.clear()
        self.koleksiyon_input.blockSignals(False)

        # Ayırıcı çizgiyi göster
        self.separator.show()

        # Takım seçimi widget'ını göster ve kategoriye göre takımları güncelle
        # Combo box seçiminde kategoriye özel takımlar + özel takım alanı göster
        if self.current_kategori in ["Yatak Odası", "Yemek Odası", "Oturma Grubu", "Doğtaş Genç ve Çocuk Odası"]:
            self.update_takim_radios(self.current_kategori, show_predefined=True)
            self.takim_secim_widget.show()
        else:
            # Diğer kategoriler için sadece özel takım alanı
            self.update_takim_radios(self.current_kategori, show_predefined=False)
            self.takim_secim_widget.show()

        # Veriyi filtrele
        self.filter_data()

    def on_kategori_input_changed(self, text):
        """Manuel kategori input değiştiğinde çağrılır"""
        if not text or text.strip() == "":
            self.current_kategori = None
            self.separator.hide()
            self.takim_secim_widget.hide()
            # Manuel input temizlendiğinde filtrelemeyi geri getir
            if self.kategori_combo.currentText():
                self.filter_data()
            return

        self.current_kategori = text.strip()

        # ComboBox seçimini temizle
        self.kategori_combo.blockSignals(True)
        self.kategori_combo.setCurrentIndex(0)
        self.kategori_combo.blockSignals(False)

        # Koleksiyon ComboBox'ını temizle
        self.koleksiyon_combo.blockSignals(True)
        self.koleksiyon_combo.clear()
        self.koleksiyon_combo.addItem("")
        self.koleksiyon_combo.blockSignals(False)

        # Takım seçimi ve ayırıcıyı gizle (manuel koleksiyon girilene kadar)
        self.separator.hide()
        self.takim_secim_widget.hide()

        # Manuel girişte filtreleme YAPMA - sadece değerleri sakla

        # Eğer koleksiyon da manuel girilmişse, özel takım adını güncelle
        if self.koleksiyon_input.text().strip():
            self.separator.show()
            # Manuel girişte sadece özel takım alanını göster
            self.update_takim_radios(None, show_predefined=False)
            self.takim_secim_widget.show()
            self.update_custom_takim_name()

    def on_koleksiyon_input_changed(self, text):
        """Manuel koleksiyon input değiştiğinde çağrılır"""
        if not text or text.strip() == "":
            self.current_koleksiyon = None
            self.separator.hide()
            self.takim_secim_widget.hide()
            # Manuel input temizlendiğinde filtrelemeyi geri getir
            if self.koleksiyon_combo.currentText():
                self.filter_data()
            return

        self.current_koleksiyon = text.strip()
        self.current_takim = None  # Takım seçimini sıfırla

        # ComboBox seçimini temizle
        self.koleksiyon_combo.blockSignals(True)
        self.koleksiyon_combo.setCurrentIndex(0)
        self.koleksiyon_combo.blockSignals(False)

        # Ayırıcı çizgiyi göster
        self.separator.show()

        # Manuel girişte SADECE özel takım alanını göster (kategoriye özel takımları gösterme)
        self.update_takim_radios(None, show_predefined=False)
        self.takim_secim_widget.show()

        # Özel takım adını otomatik doldur
        self.update_custom_takim_name()

        # Manuel girişte filtreleme YAPMA - sadece takım widget'ını göster

    def update_takim_radios(self, kategori, show_predefined=True):
        """Kategoriye göre takım radio butonlarını güncelle

        Args:
            kategori: Kategori adı
            show_predefined: True ise kategoriye özel takımları göster, False ise sadece özel takım alanını göster
        """
        # Mevcut radio butonları temizle (özel takım hariç)
        for takim_adi, radio in list(self.takim_radios.items()):
            self.takim_button_group.removeButton(radio)
            radio.deleteLater()

        self.takim_radios.clear()

        # Kategoriye göre takımları belirle (sadece show_predefined=True ise)
        takimlar = []
        if show_predefined and kategori:
            if kategori == "Yatak Odası":
                takimlar = ["6 Kapaklı, Karyola", "6 Kapaklı, Baza", "5 Kapaklı, Karyola", "5 Kapaklı, Baza"]
            elif kategori == "Yemek Odası":
                takimlar = ["Konsol, Açılır, Sandalye*6", "Konsol, Sabit, Sandalye*6", "Açılır, Sandalye*6", "Sabit, Sandalye*6"]
            elif kategori == "Oturma Grubu":
                takimlar = ["Üçlü*2, Berjer*2", "Üçlü, İkili, Berjer", "İkili Modül-Kollu*2, Köşe Modülü"]
            elif kategori == "Doğtaş Genç ve Çocuk Odası":
                takimlar = ["3 Kapaklı, 100 Karyola, Çalışma Masası", "3 Kapaklı, 100 Baza, Çalışma Masası"]

        # Layout'dan mevcut radio butonlarını temizle (özel takım hariç)
        layout = self.takim_secim_widget.layout()
        # Custom radio ve input'u geçici olarak kaldır
        layout.removeWidget(self.custom_takim_radio)
        layout.removeWidget(self.custom_takim_input)

        # Stretch'i kaldır
        while layout.count() > 1:  # Label'dan sonraki tüm widget'ları kaldır
            item = layout.takeAt(1)
            if item.widget():
                item.widget().deleteLater()

        # Yeni radio butonları ekle (kategoriye özel takımlar)
        for i, takim_adi in enumerate(takimlar):
            radio = QRadioButton(takim_adi)
            radio.setStyleSheet("""
                QRadioButton {
                    font-size: 13px;
                    font-weight: bold;
                    color: #000000;
                    padding: 3px;
                }
                QRadioButton::indicator {
                    width: 16px;
                    height: 16px;
                }
            """)
            self.takim_button_group.addButton(radio, i)
            self.takim_radios[takim_adi] = radio
            layout.insertWidget(layout.count(), radio)

        # Custom radio ve input'u en sona ekle (her zaman görünsün)
        layout.addWidget(self.custom_takim_radio)
        layout.addWidget(self.custom_takim_input)
        layout.addStretch()

    def on_custom_takim_changed(self, text):
        """Özel takım ismi girildiğinde custom radio'yu seç"""
        if text.strip():
            self.custom_takim_radio.setChecked(True)

    def update_custom_takim_name(self):
        """Manuel kategori ve koleksiyon girişlerine göre özel takım adını otomatik doldur"""
        try:
            # Manuel input'lardan değerleri al
            kategori = self.kategori_input.text().strip()
            koleksiyon = self.koleksiyon_input.text().strip()

            # İkisi de doluysa özel takım adını oluştur
            if kategori and koleksiyon:
                ozel_takim_adi = f"{kategori} - {koleksiyon}"
                self.custom_takim_input.blockSignals(True)
                self.custom_takim_input.setText(ozel_takim_adi)
                self.custom_takim_input.blockSignals(False)
                # Özel takım radio'sunu seç
                self.custom_takim_radio.setChecked(True)
        except Exception as e:
            logging.error(f"Özel takım adı güncelleme hatası: {str(e)}")

    def auto_select_by_sku(self):
        """SKU'ya göre otomatik checkbox seçimi yap (3 ile başlayan ve 10 haneli)"""
        # Bu fonksiyon artık update_table içinde otomatik yapılıyor
        pass

    def sort_filtered_data_alphabetically(self):
        """Filtered data'yı malzeme adına göre alfabetik sırala (checkbox işaretliler önce)"""
        try:
            sorted_data = []
            for row_data in self.filtered_data:
                row_sku = str(row_data.get('sku', '')).strip()
                is_checked = self.checked_state.get(row_sku, False)
                urun_adi_tam = str(row_data.get('urun_adi_tam', '')).lower()

                sorted_data.append({
                    'data': row_data,
                    'is_checked': is_checked,
                    'urun_adi_tam': urun_adi_tam
                })

            # Sıralama: Önce checkbox işaretliler (0), sonra alfabetik
            sorted_data.sort(key=lambda x: (not x['is_checked'], x['urun_adi_tam']))

            # Veriyi güncelle
            self.filtered_data = [item['data'] for item in sorted_data]

        except Exception as e:
            logging.error(f"Veri sıralama hatası: {str(e)}")

    def schedule_filter(self):
        """Filtreleme işlemini zamanlı olarak başlat"""
        # Her durumda filtreleme yap (manuel modda sadece malzeme adı filtresi)
        self.filter_timer.stop()
        self.filter_timer.start(200)

    def filter_data(self):
        """Verileri filtrele"""
        try:
            search_text = self.search_box.text().strip().lower()

            # Filtreleme öncesi checkbox durumlarını kaydet (sadece tablo varsa)
            if self.table.rowCount() > 0:
                self.save_checkbox_states()

            # Seçili satırların SKU'larını al
            checked_skus = set(sku for sku, is_checked in self.checked_state.items() if is_checked)

            # Sadece manuel inputlar kullanılıyorsa (combo'lar boşsa)
            is_manual_only = (not self.kategori_combo.currentText() and not self.koleksiyon_combo.currentText()) and \
                             (self.kategori_input.text().strip() or self.koleksiyon_input.text().strip())

            # Filtreleme
            filtered = []
            for row in self.original_data:
                # Seçili satırları her zaman dahil et (filtrelemeye tabi tutma)
                row_sku = str(row.get('sku', '')).strip()
                if row_sku in checked_skus:
                    filtered.append(row)
                    continue

                # Tam manuel girişte kategori ve koleksiyon filtrelemesi yapma
                if not is_manual_only:
                    # Kategori filtresi (combo box kullanıldığında)
                    if self.current_kategori:
                        if 'kategori' not in row or str(row['kategori']) != self.current_kategori:
                            continue

                    # Koleksiyon filtresi (combo box kullanıldığında)
                    if self.current_koleksiyon:
                        if 'KOLEKSIYON' not in row or str(row['KOLEKSIYON']).strip() != self.current_koleksiyon:
                            continue

                # Arama filtresi - Hem ürün adı hem de SKU'da ara
                if search_text:
                    found = False

                    # Ürün adında ara
                    if 'urun_adi_tam' in row:
                        urun_adi = str(row['urun_adi_tam']).lower()
                        # Regex pattern (her kelime için AND operasyonu)
                        parts = [re.escape(part) for part in search_text.split() if part]
                        pattern = r'(?=.*?{})'.format(')(?=.*?'.join(parts))
                        if re.search(pattern, urun_adi):
                            found = True

                    # SKU'da ara
                    if not found and 'sku' in row:
                        sku = str(row['sku']).lower()
                        if search_text in sku:
                            found = True

                    if not found:
                        continue

                filtered.append(row)

            self.filtered_data = filtered

            # Malzeme adına göre alfabetik sırala (seçili olmayanlar için)
            self.sort_filtered_data_alphabetically()

            self.update_table()

            self.status_label.setText(f"✅ {len(filtered)} kayıt gösteriliyor")

        except Exception as e:
            logging.error(f"Filtreleme hatası: {str(e)}")
            self.status_label.setText(f"❌ Filtreleme hatası: {str(e)}")

    def clear_search(self):
        """Arama kutusunu ve tüm filtreleri temizle"""
        self.search_box.clear()

        # Kategori seçimini temizle
        self.kategori_combo.blockSignals(True)
        self.kategori_combo.setCurrentIndex(0)  # Boş seçenek
        self.kategori_combo.blockSignals(False)
        self.current_kategori = None

        # Koleksiyon seçimini temizle
        self.koleksiyon_combo.blockSignals(True)
        self.koleksiyon_combo.setCurrentIndex(0)  # Boş seçenek
        self.koleksiyon_combo.blockSignals(False)
        self.current_koleksiyon = None

        # Manuel input alanlarını temizle
        self.kategori_input.blockSignals(True)
        self.kategori_input.clear()
        self.kategori_input.blockSignals(False)

        self.koleksiyon_input.blockSignals(True)
        self.koleksiyon_input.clear()
        self.koleksiyon_input.blockSignals(False)

        # Özel takım adı alanını temizle
        self.custom_takim_input.blockSignals(True)
        self.custom_takim_input.clear()
        self.custom_takim_input.blockSignals(False)

        # Takım seçimi radio butonlarını temizle
        if self.takim_button_group.checkedButton():
            self.takim_button_group.setExclusive(False)
            self.takim_button_group.checkedButton().setChecked(False)
            self.takim_button_group.setExclusive(True)

        # Seçim kontrol radio butonlarını temizle
        if self.selection_button_group.checkedButton():
            self.selection_button_group.setExclusive(False)
            self.selection_button_group.checkedButton().setChecked(False)
            self.selection_button_group.setExclusive(True)

        # Takım seçimi ve ayırıcıyı gizle
        self.separator.hide()
        self.takim_secim_widget.hide()
        self.current_takim = None

        # Tüm checkbox'ları ve miktarları temizle
        self.checked_state.clear()
        self.miktar_state.clear()

        # Tabloyu tamamen temizle (update_table içinde save_checkbox_states çağrılmasın diye)
        self.table.setRowCount(0)
        self.table.setColumnCount(0)

        # Tüm veriyi göster
        self.filtered_data = self.original_data.copy()
        self.update_table()

    def update_table(self):
        """Tabloyu güncelle"""
        if not self.filtered_data:
            self.table.setRowCount(0)
            self.table.setColumnCount(0)
            return

        # Mevcut durumları kaydet (sadece tablo daha önce oluşturulmuşsa)
        if self.table.rowCount() > 0:
            self.save_checkbox_states()

        self.table.blockSignals(True)
        self.table.clearContents()

        try:
            # Sütun sıralaması: Seç, Miktar, urun_adi, urun_adi_tam, LISTE, PERAKENDE, kategori, KOLEKSIYON, urun_url
            column_order = ["urun_adi", "urun_adi_tam", "LISTE", "PERAKENDE", "kategori", "KOLEKSIYON", "urun_url"]

            # Başlık isimleri
            header_labels = {
                "urun_adi": "Ürün Adı",
                "urun_url": "URL",
                "urun_adi_tam": "Malzeme Adı",
                "LISTE": "LISTE",
                "PERAKENDE": "PERAKENDE",
                "kategori": "Kategori",
                "KOLEKSIYON": "KOLEKSIYON"
            }

            # Mevcut sütunları kontrol et ve sıralı listeyi oluştur
            all_keys = set(self.filtered_data[0].keys())
            data_keys = [key for key in column_order if key in all_keys]

            # Eksik sütunları sona ekle
            for key in all_keys:
                if key not in data_keys:
                    data_keys.append(key)

            # Header listesi oluştur - Seç, Miktar + diğerleri
            headers = ["Seç", "Miktar"] + [header_labels.get(key, key) for key in data_keys]

            # Tablo boyutlarını ayarla
            self.table.setRowCount(len(self.filtered_data))
            self.table.setColumnCount(len(headers))
            self.table.setHorizontalHeaderLabels(headers)

            # Verileri tabloya ekle
            for row_idx, row_data in enumerate(self.filtered_data):
                row_sku = str(row_data.get('sku', '')).strip()

                # Seç checkbox
                checkbox_widget = QWidget()
                checkbox_layout = QHBoxLayout(checkbox_widget)
                checkbox_layout.setContentsMargins(0, 0, 0, 0)
                checkbox_layout.setAlignment(Qt.AlignCenter)

                checkbox = QCheckBox()
                # Global checkbox durumunu kullan
                checkbox.setChecked(self.checked_state.get(row_sku, False))

                # SKU'yu checkbox widget'a data olarak sakla
                checkbox.setProperty('sku', row_sku)

                checkbox.setStyleSheet("""
                    QCheckBox {
                        font-size: 14px;
                        font-weight: bold;
                    }
                    QCheckBox::indicator {
                        width: 18px;
                        height: 18px;
                    }
                """)
                # Checkbox değiştiğinde sayacı güncelle ve sırala
                checkbox.clicked.connect(self.on_checkbox_changed)
                checkbox_layout.addWidget(checkbox)
                self.table.setCellWidget(row_idx, 0, checkbox_widget)

                # Miktar sütunu - global değeri kullan
                miktar_value = self.miktar_state.get(row_sku, "1")
                miktar_item = QTableWidgetItem(miktar_value)
                miktar_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsEditable)
                font = QFont()
                font.setPointSize(15)
                font.setBold(True)
                miktar_item.setFont(font)
                self.table.setItem(row_idx, 1, miktar_item)

                # Diğer sütunlar
                for col_idx, key in enumerate(data_keys):
                    value = row_data.get(key, "")

                    # Sayısal değerlerde .0 ifadesini kaldır
                    if isinstance(value, (int, float)):
                        if isinstance(value, float) and value.is_integer():
                            display_value = str(int(value))
                        else:
                            display_value = str(value)
                    elif pd.isna(value) or value is None:
                        display_value = ""
                    else:
                        display_value = str(value)

                    item = QTableWidgetItem(display_value)
                    item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsEditable)
                    item.setFont(font)
                    self.table.setItem(row_idx, col_idx + 2, item)  # +2 çünkü Seç ve Miktar önce geliyor

            # Sütun genişliklerini ayarla
            header = self.table.horizontalHeader()
            header.setSectionResizeMode(0, QHeaderView.Fixed)
            self.table.setColumnWidth(0, 60)
            header.setSectionResizeMode(1, QHeaderView.Fixed)
            self.table.setColumnWidth(1, 80)

            for i in range(2, len(headers)):
                header.setSectionResizeMode(i, QHeaderView.ResizeToContents)

        finally:
            self.table.blockSignals(False)

        # Sayacı güncelle
        self.update_selected_count()

    def on_checkbox_changed(self):
        """Checkbox değiştiğinde sayacı güncelle ve tabloyu sırala"""
        # Hiçbiri/Tümü radio butonlarının seçimini kaldır
        if self.selection_button_group.checkedButton():
            self.selection_button_group.setExclusive(False)
            self.selection_button_group.checkedButton().setChecked(False)
            self.selection_button_group.setExclusive(True)

        # Checkbox durumlarını global değişkene kaydet
        self.save_checkbox_states()

        self.update_selected_count()
        # Kısa bir gecikme ile sıralama yap (UI responsive kalsın)
        QTimer.singleShot(100, self.sort_table_by_checkbox_status)

    def update_selected_count(self):
        """Seçili satır sayısını güncelle"""
        try:
            count = 0
            for row_idx in range(self.table.rowCount()):
                checkbox_widget = self.table.cellWidget(row_idx, 0)
                if checkbox_widget:
                    checkbox = checkbox_widget.findChild(QCheckBox)
                    if checkbox and checkbox.isChecked():
                        count += 1

            self.selected_count_label.setText(f"Seçili: {count}")
        except Exception as e:
            logging.error(f"Sayaç güncelleme hatası: {str(e)}")

    def clear_all_checkboxes(self):
        """Tüm checkbox'ları kaldır"""
        try:
            # Global state'i temizle
            self.checked_state.clear()

            # Tablodaki checkbox'ları temizle
            for row_idx in range(self.table.rowCount()):
                checkbox_widget = self.table.cellWidget(row_idx, 0)
                if checkbox_widget:
                    checkbox = checkbox_widget.findChild(QCheckBox)
                    if checkbox and checkbox.isChecked():
                        checkbox.setChecked(False)

            # Sayacı güncelle ve sırala
            self.update_selected_count()
            QTimer.singleShot(100, self.sort_table_by_checkbox_status)
        except Exception as e:
            logging.error(f"Checkbox temizleme hatası: {str(e)}")

    def select_all_checkboxes(self):
        """Tüm checkbox'ları işaretle"""
        try:
            # Tablodaki tüm satırları işaretle ve global state'e kaydet
            for row_idx in range(self.table.rowCount()):
                if row_idx < len(self.filtered_data):
                    row_sku = str(self.filtered_data[row_idx].get('sku', '')).strip()
                    if row_sku:
                        self.checked_state[row_sku] = True

                checkbox_widget = self.table.cellWidget(row_idx, 0)
                if checkbox_widget:
                    checkbox = checkbox_widget.findChild(QCheckBox)
                    if checkbox and not checkbox.isChecked():
                        checkbox.setChecked(True)

            # Sayacı güncelle ve sırala
            self.update_selected_count()
            QTimer.singleShot(100, self.sort_table_by_checkbox_status)
        except Exception as e:
            logging.error(f"Checkbox seçme hatası: {str(e)}")

    def save_checkbox_states(self):
        """Mevcut checkbox ve miktar durumlarını global değişkene kaydet"""
        for row_idx in range(self.table.rowCount()):
            # Checkbox widget'tan SKU'yu al (data olarak saklanıyor)
            checkbox_widget = self.table.cellWidget(row_idx, 0)
            if checkbox_widget:
                checkbox = checkbox_widget.findChild(QCheckBox)
                if checkbox:
                    # SKU'yu widget property'sinden al
                    row_sku = checkbox.property('sku')
                    if row_sku:
                        self.checked_state[row_sku] = checkbox.isChecked()

                        # Miktar durumu
                        miktar_item = self.table.item(row_idx, 1)
                        if miktar_item:
                            self.miktar_state[row_sku] = miktar_item.text()

    def get_checked_rows_from_table(self):
        """Global checkbox state'inden seçili satırları döndür"""
        checked_rows = []
        for row in self.original_data:
            row_sku = str(row.get('sku', '')).strip()
            if row_sku and self.checked_state.get(row_sku, False):
                checked_rows.append({
                    'data': row.copy(),
                    'miktar': self.miktar_state.get(row_sku, "1")
                })
        return checked_rows

    def sort_table_by_checkbox_status(self):
        """Tablodaki satırları checkbox durumuna göre sırala (seçililer üstte, sonra alfabetik)"""
        try:
            if self.table.rowCount() == 0:
                return

            # Checkbox durumlarını kaydet
            if self.table.rowCount() > 0 and len(self.filtered_data) > 0:
                self.save_checkbox_states()

            # Malzeme adına göre alfabetik sırala (seçililer önce)
            self.sort_filtered_data_alphabetically()

            # Tabloyu güncelle
            self.update_table()

            # Sayacı güncelle
            self.update_selected_count()

        except Exception as e:
            logging.error(f"Tablo sıralama hatası: {str(e)}")

    def on_takim_secim_changed(self, button):
        """Radio button seçimi değiştiğinde çağrılır - otomatik ürün seçimi yapar (Regex + Exclude destekli)"""
        try:
            # Hiçbiri/Tümü radio butonlarının seçimini kaldır
            if self.selection_button_group.checkedButton():
                self.selection_button_group.setExclusive(False)
                self.selection_button_group.checkedButton().setChecked(False)
                self.selection_button_group.setExclusive(True)

            # Seçilen takım adını belirle
            if button == self.custom_takim_radio:
                takim_adi = self.custom_takim_input.text().strip()
                if not takim_adi:
                    return
                self.current_takim = takim_adi
                # Özel takım için otomatik seçim yapma
                return
            else:
                takim_adi = button.text()
                self.current_takim = takim_adi

            # Kategoriye göre doğru kombinasyon dictionary'sini seç
            kombinasyon_dict = None
            if self.current_kategori == "Yatak Odası":
                kombinasyon_dict = self.yatak_odasi_kombinasyonlari
            elif self.current_kategori == "Yemek Odası":
                kombinasyon_dict = self.yemek_odasi_kombinasyonlari
            elif self.current_kategori == "Oturma Grubu":
                kombinasyon_dict = self.oturma_grubu_kombinasyonlari
            elif self.current_kategori == "Doğtaş Genç ve Çocuk Odası":
                kombinasyon_dict = self.genc_odasi_kombinasyonlari
            else:
                # Diğer kategoriler için kombinasyon yok, çık
                return

            # Seçilen takım kombinasyonunu al
            if not kombinasyon_dict or takim_adi not in kombinasyon_dict:
                return

            kombinasyon = kombinasyon_dict[takim_adi]
            aranacak_pattern_listesi = kombinasyon["aranacak_urunler"]
            adet_bilgileri = kombinasyon.get("adet", {})
            exclude_patterns = kombinasyon.get("exclude_patterns", {})

            # Önce tüm checkbox'ları temizle ve miktarları 1'e sıfırla
            for row_idx in range(self.table.rowCount()):
                checkbox_widget = self.table.cellWidget(row_idx, 0)
                if checkbox_widget:
                    checkbox = checkbox_widget.findChild(QCheckBox)
                    if checkbox:
                        checkbox.setChecked(False)

                # Miktar sütununu 1'e sıfırla
                miktar_item = self.table.item(row_idx, 1)
                if miktar_item:
                    miktar_item.setText("1")

            # Regex pattern'leri kullanarak ürünleri bul ve seç
            for pattern in aranacak_pattern_listesi:
                for row_idx in range(self.table.rowCount()):
                    row_data = self.filtered_data[row_idx]

                    # Ürün adını al
                    if 'urun_adi_tam' not in row_data:
                        continue

                    urun_adi_tam = str(row_data['urun_adi_tam'])

                    # Regex pattern ile eşleşme kontrolü
                    if re.search(pattern, urun_adi_tam, re.IGNORECASE):
                        # Exclude pattern kontrolü
                        should_exclude = False
                        if pattern in exclude_patterns:
                            for exclude_pattern in exclude_patterns[pattern]:
                                if re.search(exclude_pattern, urun_adi_tam, re.IGNORECASE):
                                    should_exclude = True
                                    break

                        if should_exclude:
                            continue  # Bu ürünü atla

                        # Checkbox'ı işaretle
                        checkbox_widget = self.table.cellWidget(row_idx, 0)
                        if checkbox_widget:
                            checkbox = checkbox_widget.findChild(QCheckBox)
                            if checkbox:
                                checkbox.setChecked(True)

                        # Adet bilgisi varsa güncelle
                        miktar = 1
                        for adet_pattern, adet_degeri in adet_bilgileri.items():
                            if re.search(adet_pattern, urun_adi_tam, re.IGNORECASE):
                                miktar = adet_degeri
                                break

                        # Miktar sütununu güncelle
                        miktar_item = self.table.item(row_idx, 1)
                        if miktar_item:
                            miktar_item.setText(str(miktar))

                        break  # Bu pattern için ürünü bulduk, bir sonraki pattern'e geç

            # Sayacı güncelle ve seçilileri üste sırala
            self.update_selected_count()
            QTimer.singleShot(100, self.sort_table_by_checkbox_status)

            self.status_label.setText(f"✅ {takim_adi} takımı için ürünler otomatik seçildi")

        except Exception as e:
            logging.error(f"Takım seçimi hatası: {str(e)}")
            self.status_label.setText(f"❌ Takım seçimi hatası: {str(e)}")

    def save_etiket_to_json(self, selected_data):
        """Etiket listesini JSON'a kaydet (Kategori → Koleksiyon → etiket_listesi)"""
        try:
            if not self.current_kategori or not self.current_koleksiyon:
                QMessageBox.warning(self, "Uyarı", "Önce Kategori ve Koleksiyon seçmelisiniz!")
                return

            # Önce seçili satırları topla
            selected_rows = []
            for row_idx in range(self.table.rowCount()):
                checkbox_widget = self.table.cellWidget(row_idx, 0)
                if checkbox_widget:
                    checkbox = checkbox_widget.findChild(QCheckBox)
                    if checkbox and checkbox.isChecked():
                        row_data = self.filtered_data[row_idx]
                        if 'sku' in row_data and 'urun_adi_tam' in row_data:
                            selected_rows.append(row_data)

            # Seçili ürünleri ayır: urunler ve takim_sku
            urunler = []
            takim_sku_data = None

            # TEK SATIR SEÇİLİYSE: SKU kontrolü YAPMADAN hem urunler[] hem de takim_sku olarak kaydet
            if len(selected_rows) == 1:
                row_data = selected_rows[0]
                sku = str(row_data['sku']).strip()

                # LISTE fiyatı
                liste_fiyat = 0
                if 'LISTE' in row_data and row_data['LISTE']:
                    try:
                        liste_fiyat = float(row_data['LISTE'])
                    except:
                        pass

                # PERAKENDE fiyatı
                perakende_fiyat = 0
                if 'PERAKENDE' in row_data and row_data['PERAKENDE']:
                    try:
                        perakende_fiyat = float(row_data['PERAKENDE'])
                    except:
                        pass

                # URL
                url = str(row_data.get('urun_url', ''))

                # İndirim yüzdesi
                indirim_yuzde = 0
                if liste_fiyat > 0:
                    indirim_yuzde = int((1 - (perakende_fiyat / liste_fiyat)) * 100)

                # Hem urunler[] hem de takim_sku olarak kaydet
                urunler.append({
                    'sku': sku,
                    'urun_adi_tam': row_data['urun_adi_tam'],
                    'liste_fiyat': liste_fiyat,
                    'perakende_fiyat': perakende_fiyat
                })

                takim_sku_data = {
                    'sku': sku,
                    'urun_adi_tam': row_data['urun_adi_tam'],
                    'url': url,
                    'liste_fiyat': liste_fiyat,
                    'perakende_fiyat': perakende_fiyat,
                    'indirim_yuzde': indirim_yuzde,
                    'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }

            # ÇOKLU SATIR SEÇİLİYSE: 3 ile başlayan 10 haneli SKU kontrolü YAP
            else:
                for row_data in selected_rows:
                    sku = str(row_data['sku']).strip()

                    # LISTE fiyatı
                    liste_fiyat = 0
                    if 'LISTE' in row_data and row_data['LISTE']:
                        try:
                            liste_fiyat = float(row_data['LISTE'])
                        except:
                            pass

                    # PERAKENDE fiyatı
                    perakende_fiyat = 0
                    if 'PERAKENDE' in row_data and row_data['PERAKENDE']:
                        try:
                            perakende_fiyat = float(row_data['PERAKENDE'])
                        except:
                            pass

                    # URL
                    url = str(row_data.get('urun_url', ''))

                    # SKU kontrolü: 3 ile başlayan VE 10 haneli → urunler[], DİĞERLERİ → takim_sku
                    if sku.startswith('3') and len(sku) == 10:
                        # Ürünler listesine ekle (indirim_yuzde YOK)
                        urunler.append({
                            'sku': sku,
                            'urun_adi_tam': row_data['urun_adi_tam'],
                            'liste_fiyat': liste_fiyat,
                            'perakende_fiyat': perakende_fiyat
                        })
                    else:
                        # Takım SKU'su (indirim_yuzde VAR)
                        indirim_yuzde = 0
                        if liste_fiyat > 0:
                            indirim_yuzde = int((1 - (perakende_fiyat / liste_fiyat)) * 100)

                        takim_sku_data = {
                            'sku': sku,
                            'urun_adi_tam': row_data['urun_adi_tam'],
                            'url': url,
                            'liste_fiyat': liste_fiyat,
                            'perakende_fiyat': perakende_fiyat,
                            'indirim_yuzde': indirim_yuzde,
                            'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        }

            # Ürün sayısı kontrolü (11'den fazla ise uyarı)
            if len(urunler) > 11:
                QMessageBox.warning(
                    self,
                    "Uyarı",
                    f"Ürün sayısı 11'den fazla olamaz!\n\nSeçili ürün sayısı: {len(urunler)}\n\nLütfen en fazla 11 ürün seçin."
                )
                return

            if not urunler and not takim_sku_data:
                QMessageBox.warning(self, "Uyarı", "Hiç ürün seçilmedi!")
                return

            # JSON yapısını oluştur/güncelle - Kategori → Koleksiyon → etiket_listesi
            if os.path.exists(self.json_file):
                with open(self.json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            else:
                data = {}

            # Kategori → Koleksiyon hiyerarşisi
            if self.current_kategori not in data:
                data[self.current_kategori] = {}

            if self.current_koleksiyon not in data[self.current_kategori]:
                data[self.current_kategori][self.current_koleksiyon] = {}

            # Mevcut etiket listesi varsa göster ve onay iste
            if 'etiket_listesi' in data[self.current_kategori][self.current_koleksiyon]:
                existing_data = data[self.current_kategori][self.current_koleksiyon]['etiket_listesi']
                existing_urunler = existing_data.get('urunler', [])

                existing_product_list = "\n".join([f"{p.get('urun_adi_tam', '')} ({p.get('sku', '')})" for p in existing_urunler])

                reply = QMessageBox.question(
                    self,
                    "Etiket Listesi Mevcut",
                    f"{self.current_koleksiyon} {self.current_kategori}\n\n"
                    f"Mevcut etiket listesi:\n{existing_product_list}\n\n"
                    f"Yeni seçilen {len(urunler)} ürün ile güncellensin mi?",
                    QMessageBox.Yes | QMessageBox.No
                )

                if reply != QMessageBox.Yes:
                    return
            else:
                # Yeni kayıt için onay iste
                product_list = "\n".join([f"{p.get('urun_adi_tam', '')} ({p.get('sku', '')})" for p in urunler])

                reply = QMessageBox.question(
                    self,
                    "Etiket Listesi Kaydet",
                    f"{self.current_koleksiyon} {self.current_kategori}\n\n"
                    f"{len(urunler)} ürün kaydedilecek:\n{product_list}\n\n"
                    f"Kaydetmek istiyor musunuz?",
                    QMessageBox.Yes | QMessageBox.No
                )

                if reply != QMessageBox.Yes:
                    return

            # Etiket listesini kaydet
            etiket_listesi = {
                'urunler': urunler
            }

            # Takım SKU'su varsa ekle
            if takim_sku_data:
                etiket_listesi['takim_sku'] = takim_sku_data

            data[self.current_kategori][self.current_koleksiyon]['etiket_listesi'] = etiket_listesi

            # Kategori ve koleksiyonları alfabetik sırala
            sorted_data = {}
            for kategori in sorted(data.keys()):
                sorted_data[kategori] = {}
                for koleksiyon in sorted(data[kategori].keys()):
                    sorted_data[kategori][koleksiyon] = data[kategori][koleksiyon]

            # JSON dosyasına kaydet
            os.makedirs(os.path.dirname(self.json_file), exist_ok=True)
            with open(self.json_file, 'w', encoding='utf-8') as f:
                json.dump(sorted_data, f, ensure_ascii=False, indent=2)

        except Exception as e:
            logging.error(f"Etiket listesi JSON kaydetme hatası: {str(e)}")

    def save_selection_to_json(self):
        """Takım seçimini JSON dosyasına kaydet (Kategori → Koleksiyon → Takım)"""
        try:
            if not self.current_kategori or not self.current_koleksiyon:
                QMessageBox.warning(self, "Uyarı", "Önce Kategori ve Koleksiyon seçmelisiniz!")
                return

            # JSON dosyasını oku
            if os.path.exists(self.json_file):
                with open(self.json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            else:
                data = {}

            # Etiket listesi kontrolü - Kategori → Koleksiyon → etiket_listesi
            if (self.current_kategori not in data or
                self.current_koleksiyon not in data.get(self.current_kategori, {}) or
                'etiket_listesi' not in data.get(self.current_kategori, {}).get(self.current_koleksiyon, {})):
                QMessageBox.warning(
                    self,
                    "Uyarı",
                    f"'{self.current_koleksiyon} {self.current_kategori}' için etiket listesi bulunamadı!\n\n"
                    f"Önce 'Etiket Listesi Kaydet' butonunu kullanarak etiket listesini kaydetmelisiniz."
                )
                return

            # Takım adını belirle
            if self.custom_takim_radio.isChecked():
                takim_adi = self.custom_takim_input.text().strip()
                if not takim_adi:
                    QMessageBox.warning(self, "Uyarı", "Özel takım adı boş olamaz!")
                    return
            else:
                # Hangi radio buton seçili kontrol et
                takim_adi = None
                for name, radio in self.takim_radios.items():
                    if radio.isChecked():
                        takim_adi = name
                        break

                if not takim_adi:
                    QMessageBox.warning(self, "Uyarı", "Takım seçimi yapmalısınız!")
                    return

            # Seçili ürünleri topla
            selected_products = []
            total_liste_price = 0
            total_perakende_price = 0
            product_details = []  # Miktar x urun_adi_tam için

            for row_idx in range(self.table.rowCount()):
                checkbox_widget = self.table.cellWidget(row_idx, 0)
                if checkbox_widget:
                    checkbox = checkbox_widget.findChild(QCheckBox)
                    if checkbox and checkbox.isChecked():
                        row_data = self.filtered_data[row_idx]

                        # Miktar sütunundan değeri al
                        miktar_item = self.table.item(row_idx, 1)
                        miktar = int(miktar_item.text()) if miktar_item and miktar_item.text().isdigit() else 1

                        if 'sku' in row_data and 'urun_adi_tam' in row_data:
                            sku = str(row_data['sku']).strip()

                            # LISTE fiyatı
                            liste_price = 0
                            if 'LISTE' in row_data and row_data['LISTE']:
                                try:
                                    liste_price = float(row_data['LISTE']) * miktar
                                except:
                                    pass

                            # PERAKENDE fiyatı
                            perakende_price = 0
                            if 'PERAKENDE' in row_data and row_data['PERAKENDE']:
                                try:
                                    perakende_price = float(row_data['PERAKENDE']) * miktar
                                except:
                                    pass

                            # Products'a sadece sku, urun_adi_tam, miktar ekle
                            selected_products.append({
                                'sku': sku,
                                'urun_adi_tam': row_data['urun_adi_tam'],
                                'miktar': miktar
                            })
                            total_liste_price += liste_price
                            total_perakende_price += perakende_price

                            # Miktar x urun_adi_tam bilgisi
                            product_details.append(f"{miktar} x {row_data['urun_adi_tam']}")

            if not selected_products:
                QMessageBox.warning(self, "Uyarı", "Hiç ürün seçilmedi!")
                return

            # Kategori → Koleksiyon hiyerarşisi
            if self.current_kategori not in data:
                data[self.current_kategori] = {}

            if self.current_koleksiyon not in data[self.current_kategori]:
                data[self.current_kategori][self.current_koleksiyon] = {}

            # Toplam indirim yüzdesi hesapla
            total_indirim_yuzde = 0
            if total_liste_price > 0:
                total_indirim_yuzde = int((1 - (total_perakende_price / total_liste_price)) * 100)

            # Takım daha önce varsa, mevcut bilgileri göster ve güncelleme için onay iste
            if takim_adi in data[self.current_kategori][self.current_koleksiyon]:
                existing_data = data[self.current_kategori][self.current_koleksiyon][takim_adi]
                existing_products = existing_data.get('products', [])
                existing_liste = existing_data.get('total_liste_price', 0)
                existing_perakende = existing_data.get('total_perakende_price', 0)
                existing_indirim = existing_data.get('total_indirim_yuzde', 0)

                existing_product_list = "\n".join([f"{p.get('miktar', 1)} x {p.get('urun_adi_tam', '')}" for p in existing_products])

                new_product_list = "\n".join(product_details)

                reply = QMessageBox.question(
                    self,
                    "Takım Mevcut",
                    f"{self.current_koleksiyon} {self.current_kategori}\n\n"
                    f"{takim_adi}\n\n"
                    f"MEVCUT:\n"
                    f"LISTE: {existing_liste:,.2f} TL\n"
                    f"PERAKENDE: {existing_perakende:,.2f} TL\n"
                    f"İNDİRİM: %{existing_indirim}\n"
                    f"Ürünler:\n{existing_product_list}\n\n"
                    f"YENİ:\n"
                    f"LISTE: {total_liste_price:,.2f} TL\n"
                    f"PERAKENDE: {total_perakende_price:,.2f} TL\n"
                    f"İNDİRİM: %{total_indirim_yuzde}\n"
                    f"Ürünler:\n{new_product_list}\n\n"
                    f"Güncellemek istiyor musunuz?",
                    QMessageBox.Yes | QMessageBox.No
                )

                if reply != QMessageBox.Yes:
                    return
            else:
                # Yeni kayıt için onay iste
                product_info = "\n".join(product_details)

                reply = QMessageBox.question(
                    self,
                    "Takım Seçimi Kaydet",
                    f"{self.current_koleksiyon} {self.current_kategori}\n\n"
                    f"{takim_adi}\n\n"
                    f"LISTE: {total_liste_price:,.2f} TL\n"
                    f"PERAKENDE: {total_perakende_price:,.2f} TL\n"
                    f"İNDİRİM: %{total_indirim_yuzde}\n\n"
                    f"Ürünler:\n{product_info}\n\n"
                    f"Kaydetmek istiyor musunuz?",
                    QMessageBox.Yes | QMessageBox.No
                )

                if reply != QMessageBox.Yes:
                    return

            # Takım bilgisini kaydet
            data[self.current_kategori][self.current_koleksiyon][takim_adi] = {
                'products': selected_products,
                'total_liste_price': total_liste_price,
                'total_perakende_price': total_perakende_price,
                'total_indirim_yuzde': total_indirim_yuzde
            }

            # Kategori ve koleksiyonları alfabetik sırala
            sorted_data = {}
            for kategori in sorted(data.keys()):
                sorted_data[kategori] = {}
                for koleksiyon in sorted(data[kategori].keys()):
                    sorted_data[kategori][koleksiyon] = data[kategori][koleksiyon]

            # JSON dosyasına kaydet
            os.makedirs(os.path.dirname(self.json_file), exist_ok=True)
            with open(self.json_file, 'w', encoding='utf-8') as f:
                json.dump(sorted_data, f, ensure_ascii=False, indent=2)

            # Başarı mesajı
            product_info = "\n".join(product_details)

            self.status_label.setText(f"✅ Takım kaydedildi: {len(selected_products)} ürün - {total_perakende_price:,.2f} TL")
            QMessageBox.information(
                self,
                "Başarılı",
                f"{self.current_koleksiyon} {self.current_kategori}\n\n"
                f"{takim_adi}\n\n"
                f"LISTE: {total_liste_price:,.2f} TL\n"
                f"PERAKENDE: {total_perakende_price:,.2f} TL\n"
                f"İNDİRİM: %{total_indirim_yuzde}\n\n"
                f"Ürünler:\n{product_info}"
            )

        except Exception as e:
            error_msg = f"JSON kaydetme hatası: {str(e)}"
            logging.error(error_msg)
            self.status_label.setText(f"❌ {error_msg}")
            QMessageBox.critical(self, "Hata", error_msg)

    def save_etiket_listesi(self):
        """Seçili satırları JSON'a etiket_listesi olarak kaydet"""
        try:
            # Seçili satırları topla - sadece 3 ile başlayan SKU'lar
            selected_data = []

            for row_idx in range(self.table.rowCount()):
                checkbox_widget = self.table.cellWidget(row_idx, 0)
                if checkbox_widget:
                    checkbox = checkbox_widget.findChild(QCheckBox)
                    if checkbox and checkbox.isChecked():
                        # Bu satırın verilerini al
                        row_data = self.filtered_data[row_idx]

                        # Sadece 3 ile başlayan SKU'ları al
                        if 'sku' in row_data and 'urun_adi_tam' in row_data:
                            sku = str(row_data['sku']).strip()
                            if sku.startswith('3'):
                                selected_data.append({
                                    'sku': sku,
                                    'urun_adi_tam': row_data['urun_adi_tam'],
                                    'koleksiyon': row_data.get('KOLEKSIYON', ''),
                                    'kategori': row_data.get('kategori', '')
                                })

            if not selected_data:
                QMessageBox.information(self, "Bilgi", "3 ile başlayan SKU'ya sahip en az bir satır seçin.")
                return

            # JSON'a etiket_listesi olarak kaydet
            self.save_etiket_to_json(selected_data)

            self.status_label.setText(f"✅ {len(selected_data)} ürün JSON dosyasına etiket_listesi olarak kaydedildi")

        except Exception as e:
            error_msg = f"Kaydetme hatası: {str(e)}"
            logging.error(error_msg)
            self.status_label.setText(f"❌ {error_msg}")
            QMessageBox.critical(self, "Hata", error_msg)

    def save_etiket_toplam_listesi(self):
        """Seçili satırları Etiket_Toplam_Listesi.xlsx dosyasına kaydet (sadece 3 ile başlayan SKU'lar + Miktar)"""
        try:
            # Seçili satırları topla - sadece 3 ile başlayan SKU'lar
            selected_data = []

            for row_idx in range(self.table.rowCount()):
                checkbox_widget = self.table.cellWidget(row_idx, 0)
                if checkbox_widget:
                    checkbox = checkbox_widget.findChild(QCheckBox)
                    if checkbox and checkbox.isChecked():
                        # Bu satırın verilerini al
                        row_data = self.filtered_data[row_idx]

                        # Miktar sütunundan değeri al
                        miktar_item = self.table.item(row_idx, 1)
                        miktar = miktar_item.text() if miktar_item else "1"

                        # Sadece 3 ile başlayan SKU'ları al
                        if 'sku' in row_data and 'urun_adi_tam' in row_data:
                            sku = str(row_data['sku']).strip()
                            if sku.startswith('3'):
                                selected_data.append({
                                    'sku': sku,
                                    'urun_adi_tam': row_data['urun_adi_tam'],
                                    'miktar': miktar
                                })

            if not selected_data:
                QMessageBox.information(self, "Bilgi", "3 ile başlayan SKU'ya sahip en az bir satır seçin.")
                return

            # title değerini oluştur (Koleksiyon + Kategori)
            if self.current_koleksiyon and self.current_kategori:
                title = f"{self.current_koleksiyon} {self.current_kategori}"
                koleksiyon_val = self.current_koleksiyon
            else:
                title = ""
                koleksiyon_val = ""

            # Tek satırlık veri oluştur
            row_dict = {
                'KOLEKSIYON': koleksiyon_val,
                'title': title,
                'aciklama': None
            }

            # urun, sap ve adet sütunlarını ekle
            for idx, data in enumerate(selected_data, 1):
                row_dict[f'urun{idx}'] = data['urun_adi_tam']
                row_dict[f'sap{idx}'] = data['sku']
                row_dict[f'adet{idx}'] = data['miktar']

            # DataFrame oluştur
            df = pd.DataFrame([row_dict])

            # Çıktı dizinini oluştur
            output_dir = r"D:\GoogleDrive\PRG\Fiyat\Etiket"
            os.makedirs(output_dir, exist_ok=True)

            # Dosya yolunu oluştur
            output_file = os.path.join(output_dir, "Etiket_Toplam_Listesi.xlsx")

            # Excel'e kaydet
            df.to_excel(output_file, index=False, engine='openpyxl')

            self.status_label.setText(f"✅ {len(selected_data)} ürün Etiket_Toplam_Listesi.xlsx dosyasına kaydedildi")
            QMessageBox.information(self, "Başarılı", f"{len(selected_data)} ürün başarıyla kaydedildi:\n{output_file}")

        except Exception as e:
            error_msg = f"Kaydetme hatası: {str(e)}"
            logging.error(error_msg)
            self.status_label.setText(f"❌ {error_msg}")
            QMessageBox.critical(self, "Hata", error_msg)


def main():
    """Ana program"""
    app = QApplication(sys.argv)
    window = EtiketListesiWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
