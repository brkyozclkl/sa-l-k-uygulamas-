import PyPDF2
import pdf2image
import pytesseract
from PIL import Image
import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
import json
import re
import os
import fitz  # PyMuPDF
import io
from datetime import datetime

# Poppler path configuration
POPPLER_PATH = r'C:\Program Files\poppler-24.08.0\Library\bin'

# Verify Poppler installation
if not os.path.exists(POPPLER_PATH):
    raise Exception(f"Poppler not found at {POPPLER_PATH}. Please install Poppler and update the path.")

if not os.path.exists(os.path.join(POPPLER_PATH, 'pdfinfo.exe')):
    raise Exception(f"pdfinfo.exe not found in {POPPLER_PATH}. Please check your Poppler installation.")

class PDFProcessor:
    def __init__(self):
        self.reference_ranges = {
            'Hemoglobin': {'min': 12, 'max': 16, 'unit': 'g/dL'},
            'WBC': {'min': 4000, 'max': 11000, 'unit': '/µL'},
            'Platelets': {'min': 150000, 'max': 450000, 'unit': '/µL'},
            'Glucose': {'min': 70, 'max': 100, 'unit': 'mg/dL'},
            'Creatinine': {'min': 0.6, 'max': 1.2, 'unit': 'mg/dL'},
            'ALT': {'min': 7, 'max': 56, 'unit': 'U/L'},
            'AST': {'min': 10, 'max': 40, 'unit': 'U/L'},
            'Total Cholesterol': {'min': 125, 'max': 200, 'unit': 'mg/dL'},
            'HDL': {'min': 40, 'max': 60, 'unit': 'mg/dL'},
            'LDL': {'min': 0, 'max': 100, 'unit': 'mg/dL'},
            'Triglycerides': {'min': 0, 'max': 150, 'unit': 'mg/dL'},
            'TSH': {'min': 0.4, 'max': 4.0, 'unit': 'µIU/mL'},
            'Vitamin D': {'min': 30, 'max': 100, 'unit': 'ng/mL'},
            'Iron': {'min': 60, 'max': 170, 'unit': 'µg/dL'},
            'Ferritin': {'min': 30, 'max': 400, 'unit': 'ng/mL'},
            'B12': {'min': 200, 'max': 900, 'unit': 'pg/mL'},
            'Folic Acid': {'min': 2.7, 'max': 17, 'unit': 'ng/mL'},
            'Calcium': {'min': 8.5, 'max': 10.5, 'unit': 'mg/dL'},
            'Magnesium': {'min': 1.7, 'max': 2.2, 'unit': 'mg/dL'},
            'Potassium': {'min': 3.5, 'max': 5.0, 'unit': 'mmol/L'},
            'Sodium': {'min': 135, 'max': 145, 'unit': 'mmol/L'},
            'Urea': {'min': 10, 'max': 50, 'unit': 'mg/dL'},
            'Uric Acid': {'min': 3.5, 'max': 7.2, 'unit': 'mg/dL'},
            'CRP': {'min': 0, 'max': 5, 'unit': 'mg/L'},
            'ESR': {'min': 0, 'max': 20, 'unit': 'mm/h'},
        }
        self.screenshot_dir = 'static/screenshots'
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
            
            # Simple parsing logic (you may need to adjust based on your PDF format)
            for line in lines:
                if any(keyword in line.lower() for keyword in ['test', 'parametre', 'değer', 'sonuç']):
                    parts = line.split()
                    if len(parts) >= 3:
                        test_names.append(parts[0])
                        results.append(parts[1])
                        units.append(parts[2] if len(parts) > 2 else '')
                        reference_ranges.append(parts[3] if len(parts) > 3 else '')
            
            # Create DataFrame
            df = pd.DataFrame({
                'Test Adı': test_names,
                'Sonuç': results,
                'Birim': units,
                'Referans Aralığı': reference_ranges
            })
            
            return df
        except Exception as e:
            print(f"Error parsing lab results: {str(e)}")
            return None

    def analyze_results(self, df, user_data):
        """Analyze lab results and generate recommendations"""
        recommendations = []
        
        try:
            # Convert numeric columns
            df['Sonuç'] = pd.to_numeric(df['Sonuç'], errors='coerce')
            
            # Basic analysis
            for _, row in df.iterrows():
                if pd.notna(row['Sonuç']):
                    # Get reference range
                    ref_range = row['Referans Aralığı']
                    if ref_range and '-' in ref_range:
                        min_val, max_val = map(float, ref_range.split('-'))
                        
                        # Check if result is within range
                        if row['Sonuç'] < min_val:
                            recommendations.append(f"{row['Test Adı']} değeri düşük. Doktorunuza danışmanızı öneririz.")
                        elif row['Sonuç'] > max_val:
                            recommendations.append(f"{row['Test Adı']} değeri yüksek. Doktorunuza danışmanızı öneririz.")
            
            # Add general recommendations based on user data
            if user_data.get('age'):
                if user_data['age'] > 50:
                    recommendations.append("Yaşınız göz önünde bulundurulduğunda, düzenli sağlık kontrollerinizi yaptırmanızı öneririz.")
            
            return recommendations
        except Exception as e:
            print(f"Error analyzing results: {str(e)}")
            return ["Sonuçlar analiz edilirken bir hata oluştu."]

    def get_statistical_analysis(self, df):
        """Generate statistical analysis of the results"""
        try:
            stats = {
                'summary': df.describe(),
                'correlation': df.corr() if df.select_dtypes(include=[np.number]).shape[1] > 1 else None,
                'missing_values': df.isnull().sum(),
                'unique_values': df.nunique()
            }
            return stats
        except Exception as e:
            print(f"Error in statistical analysis: {str(e)}")
            return None

    def generate_report(self, results, recommendations):
        """Generate a comprehensive health report"""
        report = {
            'results': results,
            'recommendations': recommendations,
            'timestamp': pd.Timestamp.now().isoformat()
        }
        
        return report 