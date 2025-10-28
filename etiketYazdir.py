import sys
import json
import os
from datetime import datetime
from pathlib import Path
from PyQt5.QtCore import Qt, QDate, QMarginsF
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                             QLabel, QApplication, QMainWindow, QMessageBox,
                             QGroupBox, QDateEdit, QPlainTextEdit)
from PyQt5.QtGui import QFont
from io import BytesIO
import qrcode
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib import colors
from reportlab.platypus import Table, TableStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import Paragraph


def get_base_dir():
    """Exe veya script dizinini döndür"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


class EtiketApp(QWidget):
    def __init__(self):
        super().__init__()
        base_dir = get_base_dir()
        self.json_file_path = Path(os.path.join(base_dir, "etiketEkle.json"))
        self.base_dir = base_dir
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()

        # Ana başlık
        title_label = QLabel("Etiket İşlemleri")
        title_label.setStyleSheet("font-size: 24px; font-weight: bold; color: #333;")
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        # Tarih seçim grubu
        date_group = QGroupBox("📆 Tarih Filtresi")
        date_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 13px;
                border: 2px solid #3498db;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 15px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        """)
        date_layout = QHBoxLayout()

        date_info_label = QLabel("Güncellenme tarihi seçilen tarihten daha yeni olan koleksiyonları göster:")
        date_info_label.setStyleSheet("font-weight: normal; font-size: 12px;")
        date_layout.addWidget(date_info_label)

        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setDisplayFormat("dd.MM.yyyy")
        self.date_edit.setStyleSheet("""
            QDateEdit {
                font-size: 13px;
                padding: 8px;
                border: 2px solid #bdc3c7;
                border-radius: 5px;
                min-width: 150px;
            }
        """)
        date_layout.addWidget(self.date_edit)
        date_layout.addStretch()
        date_group.setLayout(date_layout)
        layout.addWidget(date_group)

        # Butonlar
        button_layout = QHBoxLayout()
        button_layout.setSpacing(20)

        button_style = """
            QPushButton {
                background-color: #808080;
                color: white;
                padding: 15px;
                font-size: 18px;
                font-weight: bold;
                border-radius: 5px;
                min-width: 200px;
                border: none;
            }
            QPushButton:hover {
                background-color: #909090;
            }
        """

        btn_etiket = QPushButton("Güncel Etiket Oluştur")
        btn_etiket.setStyleSheet(button_style)
        btn_etiket.clicked.connect(self.etiket_olustur)
        button_layout.addWidget(btn_etiket)

        # Çıktı alanı
        self.output_text = QPlainTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setStyleSheet("font-family: Consolas; font-size: 17px;")

        layout.addLayout(button_layout)
        layout.addWidget(self.output_text)

        self.setLayout(layout)

    def etiket_olustur(self):
        try:
            self.output_text.clear()
            self.output_text.appendPlainText("Güncel etiket oluşturma işlemi başlatılıyor...")
            QApplication.processEvents()

            # Hata dosyasını temizle
            self.clear_error_file()

            # JSON verisini yükle
            self.output_text.appendPlainText("JSON verisi yükleniyor...")
            QApplication.processEvents()
            data = self.load_json_data()
            if data is None:
                return

            # Tarihe göre filtrele
            self.output_text.appendPlainText("Tarih filtrelemesi yapılıyor...")
            QApplication.processEvents()
            filtered_data = self.filter_by_date(data)

            if not filtered_data:
                self.output_text.appendPlainText("Seçilen tarihten sonra güncellenmiş koleksiyon bulunamadı!")
                return

            # EXC ve SUBE verilerini ayır
            exc_data, sube_data = self.separate_exc_sube(filtered_data)

            # PDF'leri oluştur
            if exc_data:
                self.output_text.appendPlainText(f"EXC için {len(exc_data)} etiket oluşturuluyor...")
                QApplication.processEvents()
                self.create_pdf(exc_data, os.path.join(self.base_dir, "Etiket_EXC.pdf"))
                self.output_text.appendPlainText("EXC PDF başarıyla oluşturuldu!")

            if sube_data:
                self.output_text.appendPlainText(f"SUBE için {len(sube_data)} etiket oluşturuluyor...")
                QApplication.processEvents()
                self.create_pdf(sube_data, os.path.join(self.base_dir, "Etiket_SUBE.pdf"))
                self.output_text.appendPlainText("SUBE PDF başarıyla oluşturuldu!")

            # QR hata kontrolü
            qr_hata_file = os.path.join(self.base_dir, "QR_Hata.txt")
            if os.path.exists(qr_hata_file):
                self.output_text.appendPlainText("\n⚠️ QR kodu oluşturulamayan ürünler:")
                with open(qr_hata_file, "r", encoding="utf-8") as f:
                    self.output_text.appendPlainText(f.read())

            self.output_text.appendPlainText("\n✅ İşlem başarıyla tamamlandı!")

        except Exception as e:
            self.output_text.appendPlainText(f"\n❌ Hata oluştu: {str(e)}")
            import traceback
            self.output_text.appendPlainText(traceback.format_exc())

    def clear_error_file(self):
        """QR hata dosyasını temizler."""
        error_file = os.path.join(self.base_dir, "QR_Hata.txt")
        if os.path.exists(error_file):
            os.remove(error_file)

    def load_json_data(self):
        """JSON dosyasını yükler."""
        try:
            if not self.json_file_path.exists():
                self.output_text.appendPlainText(f"❌ Dosya bulunamadı: {self.json_file_path}")
                return None

            with open(self.json_file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            self.output_text.appendPlainText(f"❌ JSON okuma hatası: {str(e)}")
            return None

    def filter_by_date(self, data):
        """Seçilen tarihe göre koleksiyonları filtreler."""
        selected_date = self.date_edit.date().toPyDate()
        selected_datetime = datetime.combine(selected_date, datetime.min.time())

        filtered = []

        for kategori, koleksiyonlar in data.items():
            for koleksiyon_adi, koleksiyon_verisi in koleksiyonlar.items():
                if "etiket_listesi" not in koleksiyon_verisi:
                    continue

                etiket_listesi = koleksiyon_verisi["etiket_listesi"]
                if "takim_sku" not in etiket_listesi:
                    continue

                takim_sku = etiket_listesi["takim_sku"]
                if "updated_at" not in takim_sku:
                    continue

                try:
                    updated_at = datetime.strptime(takim_sku["updated_at"], "%Y-%m-%d %H:%M:%S")
                    if updated_at > selected_datetime:
                        filtered.append({
                            'kategori': kategori,
                            'koleksiyon_adi': koleksiyon_adi,
                            'data': koleksiyon_verisi
                        })
                except ValueError:
                    continue

        return filtered

    def separate_exc_sube(self, filtered_data):
        """EXC ve SUBE verilerini ayırır."""
        exc_data = []
        sube_data = []

        for item in filtered_data:
            takim_sku = item['data']['etiket_listesi']['takim_sku']

            # SEÇ kontrolü (secDeger varsa ve "true" ise devam et)
            sec_deger = takim_sku.get('secDeger', 'true')
            if isinstance(sec_deger, str) and sec_deger.lower() != 'true':
                continue  # SEÇ işaretli değilse bu koleksiyonu atla
            elif isinstance(sec_deger, bool) and not sec_deger:
                continue

            # EXC kontrolü (excDeger "true" ise EXC listesine ekle)
            exc_deger = takim_sku.get('excDeger', 'false')
            if isinstance(exc_deger, str) and exc_deger.lower() == 'true':
                exc_data.append(item)
            elif isinstance(exc_deger, bool) and exc_deger:
                exc_data.append(item)

            # SUBE kontrolü (subeDeger "true" ise SUBE listesine ekle)
            sube_deger = takim_sku.get('subeDeger', 'false')
            if isinstance(sube_deger, str) and sube_deger.lower() == 'true':
                sube_data.append(item)
            elif isinstance(sube_deger, bool) and sube_deger:
                sube_data.append(item)

        return exc_data, sube_data

    def create_pdf(self, etiket_data, output_path):
        """PDF dosyasını oluşturur."""
        try:
            c = canvas.Canvas(output_path, pagesize=landscape(A4))

            for i, etiket in enumerate(etiket_data):
                self.draw_etiket(c, etiket)
                if i < len(etiket_data) - 1:
                    c.showPage()

            c.save()

        except Exception as e:
            self.output_text.appendPlainText(f"❌ PDF oluşturma hatası: {str(e)}")
            raise

    def draw_etiket(self, c, etiket):
        """Tek bir etiket sayfası çizer."""
        try:
            # Font ayarları
            self.setup_fonts()

            # Sayfa boyutları
            page_width, page_height = landscape(A4)

            # Kesim çizgileri
            self.draw_cutting_lines(c)

            # Başlık resmi
            try:
                header_img = ImageReader(os.path.join(get_base_dir(), "etiket_baslik.png"))
                c.drawImage(header_img, -10, page_height-175, width=590, height=90, preserveAspectRatio=True)
            except Exception as e:
                self.output_text.appendPlainText(f"⚠️ Başlık resmi yüklenemedi: {e}")

            # QR Kodu
            takim_sku = etiket['data']['etiket_listesi']['takim_sku']
            if 'url' in takim_sku and takim_sku['url']:
                qr_img = self.generate_qr_code(takim_sku['url'])
                c.drawImage(qr_img, page_width-185, page_height-175, width=100, height=100)
            else:
                with open(os.path.join(get_base_dir(), "QR_Hata.txt"), "a", encoding="utf-8") as f:
                    f.write(f"{etiket['koleksiyon_adi']} - QR kodu oluşturulamadı (URL bulunamadı)\n")

            # İndirim Yüzdesi Etiketi (header ile QR kod arasına)
            indirim_yuzde = takim_sku.get('indirim_yuzde', 0)
            if indirim_yuzde > 0:
                # İndirim etiketinin boyutları ve konumu
                etiket_width = 110
                etiket_height = 45
                # Header'ın sağ üst köşesine yerleştir (QR kodun solunda)
                etiket_x = 510  # header sağ tarafı
                etiket_y = page_height - 140

                # Kırmızı arka plan (döndürülmüş etiket efekti)
                c.saveState()
                c.translate(etiket_x, etiket_y)
                c.rotate(-17)  # 12 derece sola eğik

                # Kırmızı dikdörtgen (yuvarlatılmış köşeler)
                c.setFillColorRGB(0.07, 0.07, 0.07)  # Parlak kırmızı
                c.roundRect(0, 0, etiket_width, etiket_height, 8, fill=1, stroke=0)

                # Beyaz yazı (indirim yüzdesi)
                c.setFillColorRGB(1, 1, 1)  # Beyaz
                c.setFont('Arial-Bold', 36)
                text = f"-{indirim_yuzde}%"
                text_width = c.stringWidth(text, 'Arial-Bold', 36)
                text_x = (etiket_width - text_width) / 2
                text_y = etiket_height / 2 - 13
                c.drawString(text_x, text_y, text)

                c.restoreState()

            # Yerli Üretim Logosu
            try:
                logo_img = ImageReader(os.path.join(get_base_dir(), "yerli_uretim.jpg"))
                c.drawImage(logo_img, page_width-180, 80, width=100, height=30)
            except Exception as e:
                self.output_text.appendPlainText(f"⚠️ Logo yüklenemedi: {e}")

            # Tablo oluştur
            self.draw_table(c, etiket, page_height)

            # Dipnot
            c.setFont('Arial', 9)
            dipnot = f"Fiyat Değişiklik Tarihi: {datetime.now().strftime('%d.%m.%Y')} / Fiyatlara KDV dahildir / Üretim Yeri: TÜRKİYE"
            c.drawString(100, 80, dipnot)

        except Exception as e:
            self.output_text.appendPlainText(f"❌ Etiket çizme hatası: {str(e)}")
            raise

    def draw_table(self, c, etiket, page_height):
        """Etiket tablosunu çizer."""
        data = []
        styles = getSampleStyleSheet()

        # Başlık satırı - Koleksiyon adı
        title_style = ParagraphStyle(
            'TitleStyle',
            parent=styles['Normal'],
            fontName='Arial-Bold',
            fontSize=16,
            leading=18,
            textColor=colors.HexColor("#000000"),
            alignment=0
        )
        # takim_sku'dan urun_adi_tam bilgisini al
        takim_sku = etiket['data']['etiket_listesi']['takim_sku']
        koleksiyon_title = takim_sku.get('urun_adi_tam', f"{etiket['koleksiyon_adi']} Yatak Odası Takımı")
        title_para = Paragraph(koleksiyon_title, title_style)
        data.append([title_para, "İNDİRİMLİ FİYAT", "LİSTE FİYATI"])

        # Ürünler
        product_style = ParagraphStyle(
            'ProductStyle',
            parent=styles['Normal'],
            fontName='Arial',
            fontSize=10,
            leading=12,
            textColor=colors.black
        )

        etiket_listesi = etiket['data']['etiket_listesi']
        if 'urunler' in etiket_listesi:
            for urun in etiket_listesi['urunler']:
                product_name = Paragraph(urun['urun_adi_tam'], product_style)
                data.append([
                    product_name,
                    self.format_price(urun.get('perakende_fiyat', 0)),
                    self.format_price(urun.get('liste_fiyat', 0))
                ])

        # Paket/Kombinasyonlar
        aciklama_style = ParagraphStyle(
            'AciklamaStyle',
            parent=styles['Normal'],
            fontName='Arial-Bold',
            fontSize=14,
            leading=16,
            textColor=colors.HexColor("#000000"),
            spaceBefore=10,
            spaceAfter=10
        )

        product_count = len(etiket_listesi.get('urunler', []))

        for key, value in etiket['data'].items():
            if key != 'etiket_listesi' and isinstance(value, dict) and 'products' in value:
                paket_name_text = f"{key.title()}"
                paket_name = Paragraph(paket_name_text, aciklama_style)
                data.append([
                    paket_name,
                    self.format_price(value.get('total_perakende_price', 0)),
                    self.format_price(value.get('total_liste_price', 0))
                ])

        # Tablo stili
        style = TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#D3D3D3")),
            ('TEXTCOLOR', (0,0), (-1,0), colors.black),
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('ALIGN', (1,0), (-1,-1), 'RIGHT'),
            ('FONTNAME', (0,0), (-1,0), 'Arial-Bold'),
            ('FONTSIZE', (0,0), (-1,0), 16),
            ('BOTTOMPADDING', (0,0), (-1,0), 12),
            ('BACKGROUND', (0,1), (-1,-1), colors.white),
            ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.HexColor("#F5F5F5"), colors.white]),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('FONTNAME', (0,product_count+1), (-1,-1), 'Arial-Bold'),
            ('FONTSIZE', (0,product_count+1), (-1,-1), 14),
        ])

        # Tablo boyutları
        col_widths = [landscape(A4)[0]-425, 135, 125]
        row_heights = [30] + [17] * product_count

        # Paket satırları için yükseklik ekle
        paket_count = len([k for k in etiket['data'].keys() if k != 'etiket_listesi'])
        if paket_count > 0:
            row_heights += [20] * paket_count

        # Tabloyu çiz
        table = Table(data, colWidths=col_widths, rowHeights=row_heights)
        table.setStyle(style)
        table.wrapOn(c, landscape(A4)[0], landscape(A4)[1])
        table.drawOn(c, 80, page_height - 180 - table._height)

    def draw_cutting_lines(self, c):
        """Kesim çizgilerini çizer."""
        page_width, page_height = landscape(A4)
        line_length = 60

        c.setLineWidth(2)

        # Sol Üst
        c.line(10, page_height-10, 10+line_length, page_height-10)
        c.line(10, page_height-10, 10, page_height-10-line_length)
        # Sağ Üst
        c.line(page_width-10, page_height-10, page_width-10-line_length, page_height-10)
        c.line(page_width-10, page_height-10, page_width-10, page_height-10-line_length)
        # Sol Alt
        c.line(10, 10, 10+line_length, 10)
        c.line(10, 10, 10, 10+line_length)
        # Sağ Alt
        c.line(page_width-10, 10, page_width-10-line_length, 10)
        c.line(page_width-10, 10, page_width-10, 10+line_length)

    def generate_qr_code(self, url):
        """QR kodu oluşturur."""
        qr = qrcode.QRCode(version=1, box_size=10, border=2)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buff = BytesIO()
        img.save(buff, format="PNG")
        buff.seek(0)
        return ImageReader(buff)

    def setup_fonts(self):
        """Fontları yükler."""
        try:
            font_path = "C:/Windows/Fonts/arial.ttf"
            pdfmetrics.registerFont(TTFont('Arial', font_path))
            pdfmetrics.registerFont(TTFont('Arial-Bold', font_path))
        except:
            self.output_text.appendPlainText("⚠️ Özel fontlar yüklenemedi, sistem fontları kullanılacak")

    def format_price(self, price):
        """Fiyatı TL formatında döndürür."""
        if price == 0:
            return "0 TL"
        return f"{price:,.0f} TL".replace(",", "X").replace(".", ",").replace("X", ".")


# Geriye uyumluluk için alias
EtiketYazdirWidget = EtiketApp


def main():
    app = QApplication(sys.argv)
    window = QMainWindow()
    window.setWindowTitle("Etiket Yazdırma")
    window.setGeometry(100, 100, 1000, 700)

    widget = EtiketApp()
    window.setCentralWidget(widget)
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
