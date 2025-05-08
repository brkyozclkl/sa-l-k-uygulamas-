import fitz  # PyMuPDF
import pandas as pd
import numpy as np
from PIL import Image
import os
from datetime import datetime
from tabulate import tabulate
import sys

class PDFAnalyzer:
    def __init__(self):
        self.screenshot_dir = 'screenshots'
        os.makedirs(self.screenshot_dir, exist_ok=True)

    def extract_text_from_pdf(self, pdf_path):
        """Extract text from PDF file"""
        try:
            doc = fitz.open(pdf_path)
            text = ""
            for page in doc:
                text += page.get_text()
            return text
        except Exception as e:
            print(f"Error extracting text: {str(e)}")
            return None

    def take_screenshots(self, pdf_path):
        """Take screenshots of each page in the PDF"""
        try:
            doc = fitz.open(pdf_path)
            screenshots = []
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x zoom for better quality
                
                # Convert to PIL Image
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                
                # Save screenshot
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"page_{page_num + 1}_{timestamp}.png"
                filepath = os.path.join(self.screenshot_dir, filename)
                img.save(filepath)
                
                screenshots.append({
                    'page_number': page_num + 1,
                    'filepath': filepath
                })
            
            return screenshots
        except Exception as e:
            print(f"Error taking screenshots: {str(e)}")
            return None

    def parse_lab_results(self, text):
        """Parse lab results from text and convert to DataFrame"""
        try:
            # Split text into lines
            lines = text.split('\n')
            
            # Initialize lists to store data
            test_names = []
            results = []
            units = []
            reference_ranges = []
            
            # Process each line
            for line in lines:
                # Skip empty lines
                if not line.strip():
                    continue
                    
                # Try to find test results in the format: Test Adı: Değer Birim (Referans Aralığı)
                parts = line.split()
                if len(parts) >= 2:
                    # Look for patterns like "Test: 10 mg/dL (5-15)" or "Test: 10 (5-15) mg/dL"
                    test_name = parts[0].rstrip(':')
                    
                    # Try to find the value
                    value = None
                    unit = None
                    ref_range = None
                    
                    for i, part in enumerate(parts[1:], 1):
                        # Try to convert to float to find the value
                        try:
                            float(part)
                            value = part
                            # Check if next part is a unit or reference range
                            if i + 1 < len(parts):
                                next_part = parts[i + 1]
                                if '(' in next_part or '-' in next_part:
                                    ref_range = next_part.strip('()')
                                else:
                                    unit = next_part
                            break
                        except ValueError:
                            continue
                    
                    if value:
                        test_names.append(test_name)
                        results.append(value)
                        units.append(unit if unit else '')
                        reference_ranges.append(ref_range if ref_range else '')
            
            # Create DataFrame
            df = pd.DataFrame({
                'Test Adı': test_names,
                'Sonuç': results,
                'Birim': units,
                'Referans Aralığı': reference_ranges
            })
            
            # Print the raw text for debugging
            print("\nPDF'den çıkarılan ham metin:")
            print(text)
            
            return df
        except Exception as e:
            print(f"Error parsing lab results: {str(e)}")
            return None

    def display_dataframe(self, df):
        """Display DataFrame in terminal using tabulate"""
        if df is not None:
            print("\nTahlil Sonuçları:")
            print(tabulate(df, headers='keys', tablefmt='grid', showindex=False))
            
            # Display basic statistics
            print("\nİstatistiksel Analiz:")
            stats_df = df.describe()
            print(tabulate(stats_df, headers='keys', tablefmt='grid'))
        else:
            print("Veri bulunamadı veya işlenemedi.")

def main():
    # Hardcoded PDF path
    pdf_path = r"D:\sağlık uygulaması\Enabiz-Tahlilleri (2).pdf"
    
    if not os.path.exists(pdf_path):
        print(f"Hata: {pdf_path} dosyası bulunamadı.")
        sys.exit(1)

    analyzer = PDFAnalyzer()
    
    # Extract text from PDF
    print("PDF'den metin çıkarılıyor...")
    text = analyzer.extract_text_from_pdf(pdf_path)
    
    if text:
        # Take screenshots
        print("PDF sayfalarının ekran görüntüleri alınıyor...")
        screenshots = analyzer.take_screenshots(pdf_path)
        if screenshots:
            print(f"{len(screenshots)} sayfa için ekran görüntüsü alındı.")
        
        # Parse and display results
        print("Tahlil sonuçları analiz ediliyor...")
        df = analyzer.parse_lab_results(text)
        analyzer.display_dataframe(df)
    else:
        print("PDF'den metin çıkarılamadı.")

if __name__ == "__main__":
    main() 