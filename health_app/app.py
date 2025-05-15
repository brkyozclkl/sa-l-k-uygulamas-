from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
from datetime import datetime, date
from dotenv import load_dotenv
import math
import re
import pandas as pd
import json
import sqlite3
from sqlalchemy import text
import pickle

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///health_app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Besin veritabanını yükle
def load_food_db():
    try:
        with open('food_db.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return []

FOOD_DB = load_food_db()

# Besin veritabanını güncelle
def save_food_db():
    with open('food_db.json', 'w', encoding='utf-8') as f:
        json.dump(FOOD_DB, f, ensure_ascii=False, indent=4)

# Besin ekleme endpoint'i
@app.route('/add-food', methods=['POST'])
@login_required
def add_food():
    try:
        new_food = {
            'id': len(FOOD_DB) + 1,
            'name': request.form.get('name'),
            'calories': float(request.form.get('calories')),
            'protein': float(request.form.get('protein')),
            'carbs': float(request.form.get('carbs')),
            'fat': float(request.form.get('fat')),
            'portion': float(request.form.get('portion', 100))
        }
        FOOD_DB.append(new_food)
        save_food_db()
        return jsonify({'success': True, 'message': 'Besin başarıyla eklendi.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400

# Besin güncelleme endpoint'i
@app.route('/update-food/<int:food_id>', methods=['PUT'])
@login_required
def update_food(food_id):
    try:
        food = next((f for f in FOOD_DB if f['id'] == food_id), None)
        if not food:
            return jsonify({'success': False, 'message': 'Besin bulunamadı.'}), 404
        
        data = request.get_json()
        food.update({
            'name': data.get('name', food['name']),
            'calories': float(data.get('calories', food['calories'])),
            'protein': float(data.get('protein', food['protein'])),
            'carbs': float(data.get('carbs', food['carbs'])),
            'fat': float(data.get('fat', food['fat'])),
            'portion': float(data.get('portion', food['portion']))
        })
        save_food_db()
        return jsonify({'success': True, 'message': 'Besin başarıyla güncellendi.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400

# Besin silme endpoint'i
@app.route('/delete-food/<int:food_id>', methods=['DELETE'])
@login_required
def delete_food(food_id):
    try:
        global FOOD_DB
        FOOD_DB = [f for f in FOOD_DB if f['id'] != food_id]
        save_food_db()
        return jsonify({'success': True, 'message': 'Besin başarıyla silindi.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400

# Tüm besinleri listeleme endpoint'i
@app.route('/list-foods', methods=['GET'])
@login_required
def list_foods():
    return jsonify(FOOD_DB)

# Initialize extensions
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# User model
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    name = db.Column(db.String(100))
    age = db.Column(db.Integer)
    gender = db.Column(db.String(10))
    weight = db.Column(db.Float)
    height = db.Column(db.Float)
    activity_level = db.Column(db.String(20))  # Sedentary, Lightly Active, Moderately Active, Very Active, Extra Active
    goal = db.Column(db.String(20))  # Lose Weight, Maintain, Gain Weight
    last_login = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    test_results = db.relationship('TestResult', backref='user', lazy=True)
    meals = db.relationship('Meal', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def calculate_bmr(self):
        """Calculate Basal Metabolic Rate using Mifflin-St Jeor Equation"""
        if self.gender == 'male':
            bmr = 10 * self.weight + 6.25 * self.height - 5 * self.age + 5
        else:
            bmr = 10 * self.weight + 6.25 * self.height - 5 * self.age - 161
        return bmr

    def calculate_tdee(self):
        """Calculate Total Daily Energy Expenditure"""
        activity_multipliers = {
            'sedentary': 1.2,
            'lightly_active': 1.375,
            'moderately_active': 1.55,
            'very_active': 1.725,
            'extra_active': 1.9
        }
        bmr = self.calculate_bmr()
        # Eğer activity_level yoksa 'sedentary' kullan
        level = (self.activity_level or 'sedentary').lower()
        multiplier = activity_multipliers.get(level, 1.2)
        tdee = bmr * multiplier
        return tdee

    def calculate_daily_calories(self):
        """Calculate daily calorie needs based on goal"""
        tdee = self.calculate_tdee()
        goal = (self.goal or 'maintain').lower()
        if goal == 'lose_weight':
            return tdee - 500
        elif goal == 'gain_weight':
            return tdee + 500
        return tdee

# Test Result model
class TestResult(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    pdf_path = db.Column(db.String(200))
    results_data = db.Column(db.JSON)
    recommendations = db.Column(db.Text)

# Meal model
class Meal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date = db.Column(db.Date, nullable=False, default=date.today)
    meal_type = db.Column(db.String(20))  # Breakfast, Lunch, Dinner, Snack
    food_name = db.Column(db.String(100), nullable=False)
    food_id = db.Column(db.Integer)  # Besin veritabanındaki ID
    portion = db.Column(db.Float, nullable=False, default=100)  # Gram cinsinden porsiyon
    calories = db.Column(db.Float, nullable=False)
    protein = db.Column(db.Float)
    carbs = db.Column(db.Float)
    fat = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class HealthJournal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    mood = db.Column(db.String(50))
    sleep_hours = db.Column(db.Float)
    exercise = db.Column(db.String(200))
    nutrition = db.Column(db.String(200))
    complaints = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class ChronicMeasurement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date = db.Column(db.Date, nullable=False, default=date.today)
    disease_type = db.Column(db.String(50), nullable=False)  # e.g. 'diabetes', 'hypertension', 'asthma'
    measurement_type = db.Column(db.String(50), nullable=False)  # e.g. 'blood_glucose', 'blood_pressure', 'peak_flow'
    value = db.Column(db.String(50), nullable=False)  # e.g. '120', '120/80', '400'
    note = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class MoodStressTest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    mood_score = db.Column(db.Integer)
    stress_score = db.Column(db.Integer)
    result_json = db.Column(db.JSON)

class HealthGoal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    steps = db.Column(db.Integer, default=8000)
    water = db.Column(db.Float, default=2.0)  # litre
    sleep = db.Column(db.Float, default=7.0)  # saat
    weight = db.Column(db.Float, nullable=True)
    calories = db.Column(db.Integer, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

class HealthGoalEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date = db.Column(db.Date, default=date.today)
    steps = db.Column(db.Integer)
    water = db.Column(db.Float)
    sleep = db.Column(db.Float)
    weight = db.Column(db.Float)
    calories = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

def init_db():
    # Create all tables
    db.create_all()
    
    # Add new columns if they don't exist
    with db.engine.connect() as conn:
        # Check if portion column exists
        inspector = db.inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns('meal')]
        
        if 'portion' not in columns:
            conn.execute(text('ALTER TABLE meal ADD COLUMN portion FLOAT NOT NULL DEFAULT 100'))
        
        if 'food_id' not in columns:
            conn.execute(text('ALTER TABLE meal ADD COLUMN food_id INTEGER'))
        
        conn.commit()
    
    print("Database tables and columns created successfully!")

# Create database tables
with app.app_context():
    init_db()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        name = request.form.get('name')
        age = request.form.get('age')
        gender = request.form.get('gender')
        weight = request.form.get('weight')
        height = request.form.get('height')
        
        if User.query.filter_by(email=email).first():
            flash('Bu e-posta adresi zaten kayıtlı')
            return redirect(url_for('register'))
        
        user = User(
            email=email,
            name=name,
            age=age if age else None,
            gender=gender if gender else None,
            weight=float(weight) if weight else None,
            height=float(height) if height else None,
            activity_level="sedentary",  # Varsayılan değer
            goal="maintain"              # Varsayılan değer
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        flash('Kayıt başarılı! Şimdi giriş yapabilirsiniz.')
        return redirect(url_for('login'))
    return render_template('auth/register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            user.last_login = datetime.utcnow()
            db.session.commit()
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Geçersiz e-posta veya şifre')
    return render_template('auth/login.html')

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('main/dashboard.html')

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        current_user.name = request.form.get('name')
        current_user.age = request.form.get('age')
        current_user.gender = request.form.get('gender')
        current_user.weight = request.form.get('weight')
        current_user.height = request.form.get('height')
        
        try:
            db.session.commit()
            flash('Profil bilgileriniz başarıyla güncellendi.', 'success')
        except Exception as e:
            db.session.rollback()
            flash('Profil güncellenirken bir hata oluştu.', 'error')
            
    return render_template('profile/profile.html')

@app.route('/change-password', methods=['POST'])
@login_required
def change_password():
    current_password = request.form.get('current_password')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')
    
    if not check_password_hash(current_user.password, current_password):
        flash('Mevcut şifreniz yanlış.', 'error')
        return redirect(url_for('profile'))
        
    if new_password != confirm_password:
        flash('Yeni şifreler eşleşmiyor.', 'error')
        return redirect(url_for('profile'))
        
    if len(new_password) < 6:
        flash('Şifre en az 6 karakter olmalıdır.', 'error')
        return redirect(url_for('profile'))
        
    try:
        current_user.password = generate_password_hash(new_password)
        db.session.commit()
        flash('Şifreniz başarıyla değiştirildi.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Şifre değiştirilirken bir hata oluştu.', 'error')
        
    return redirect(url_for('profile'))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/calorie-calculator')
@login_required
def calorie_calculator():
    if not all([current_user.age, current_user.gender, current_user.weight, current_user.height]):
        flash('Lütfen önce profil bilgilerinizi tamamlayın.', 'warning')
        return redirect(url_for('profile'))
    
    daily_calories = current_user.calculate_daily_calories()
    bmr = current_user.calculate_bmr()
    tdee = current_user.calculate_tdee()
    
    return render_template('nutrition/calorie_calculator.html',
                         daily_calories=round(daily_calories),
                         bmr=round(bmr),
                         tdee=round(tdee))

@app.route('/update-activity-level', methods=['POST'])
@login_required
def update_activity_level():
    activity_level = request.form.get('activity_level')
    goal = request.form.get('goal')
    
    if activity_level and goal:
        current_user.activity_level = activity_level
        current_user.goal = goal
        try:
            db.session.commit()
            flash('Aktivite seviyeniz ve hedefiniz güncellendi.', 'success')
        except Exception as e:
            db.session.rollback()
            flash('Güncelleme sırasında bir hata oluştu.', 'error')
    
    return redirect(url_for('calorie_calculator'))

@app.route('/meals')
@login_required
def meals():
    # Tarih seçimi (varsayılan: bugün)
    selected_date = request.args.get('date')
    if selected_date:
        try:
            date_obj = datetime.strptime(selected_date, '%Y-%m-%d').date()
        except Exception:
            date_obj = date.today()
    else:
        date_obj = date.today()

    # O güne ait öğünleri çek
    meals = Meal.query.filter_by(user_id=current_user.id, date=date_obj).all()

    # Günlük toplamlar ve hedefler
    daily_totals = {
        'calories': sum(meal.calories for meal in meals),
        'protein': sum(meal.protein or 0 for meal in meals),
        'carbs': sum(meal.carbs or 0 for meal in meals),
        'fat': sum(meal.fat or 0 for meal in meals)
    }
    daily_goal = current_user.calculate_daily_calories()

    return render_template(
        'nutrition/meals.html',
        meals=meals,
        daily_totals=daily_totals,
        daily_goal=daily_goal,
        food_db=FOOD_DB,
        selected_date=date_obj
    )

@app.route('/add-meal', methods=['POST'])
@login_required
def add_meal():
    meal_type = request.form.get('meal_type')
    food_name = request.form.get('food_name')
    portion = float(request.form.get('portion', 100))
    calories = request.form.get('calories')
    protein = request.form.get('protein')
    carbs = request.form.get('carbs')
    fat = request.form.get('fat')
    # Tarih desteği
    date_str = request.form.get('date')
    if date_str:
        try:
            meal_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except Exception:
            meal_date = date.today()
    else:
        meal_date = date.today()
    if not all([meal_type, food_name, calories]):
        flash('Lütfen gerekli alanları doldurun.', 'error')
        return redirect(url_for('meals', date=date_str or ''))
    try:
        # Besin veritabanında ara
        food = next((f for f in FOOD_DB if f['name'] == food_name), None)
        meal = Meal(
            user_id=current_user.id,
            meal_type=meal_type,
            food_name=food_name,
            food_id=food['id'] if food else None,
            portion=portion,
            calories=float(calories),
            protein=float(protein) if protein else None,
            carbs=float(carbs) if carbs else None,
            fat=float(fat) if fat else None,
            date=meal_date
        )
        db.session.add(meal)
        db.session.commit()
        flash('Öğün başarıyla eklendi.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Öğün eklenirken bir hata oluştu.', 'error')
        print(f"Hata detayı: {str(e)}")  # Hata detayını logla
    return redirect(url_for('meals', date=date_str or ''))

@app.route('/delete-meal/<int:meal_id>', methods=['POST'])
@login_required
def delete_meal(meal_id):
    meal = Meal.query.get_or_404(meal_id)
    if meal.user_id != current_user.id:
        flash('Bu işlem için yetkiniz yok.', 'error')
        return redirect(url_for('meals'))
    
    try:
        db.session.delete(meal)
        db.session.commit()
        flash('Öğün başarıyla silindi.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Öğün silinirken bir hata oluştu.', 'error')
    
    return redirect(url_for('meals'))

@app.route('/clinic-referral', methods=['GET', 'POST'])
def clinic_referral():
    complaint = None
    recommended_clinic = None
    complaint_map = {
        'karın ağrısı': 'Dahiliye (İç Hastalıkları)',
        'baş ağrısı': 'Nöroloji',
        'nefes darlığı': 'Göğüs Hastalıkları',
        'göğüs ağrısı': 'Kardiyoloji',
        'ateş': 'Enfeksiyon Hastalıkları',
        'cilt döküntüsü': 'Dermatoloji',
        'eklem ağrısı': 'Fizik Tedavi ve Rehabilitasyon',
        'diğer': 'Aile Hekimliği'
    }
    if request.method == 'POST':
        complaint = request.form.get('complaint')
        recommended_clinic = complaint_map.get(complaint, None)
    return render_template('clinic_referral.html', complaint=complaint, recommended_clinic=recommended_clinic)

@app.route('/blood-analysis')
def blood_analysis():
    return render_template('blood_analysis.html')

@app.route('/doctor-recommendation', methods=['GET', 'POST'])
def doctor_recommendation():
    # Load doctor data from JSON file
    try:
        with open('doctor_data.json', 'r', encoding='utf-8') as f:
            doctor_data = json.load(f)
            keyword_doctor_map = [(item['pattern'], item['doctor']) for item in doctor_data['keyword_doctor_map']]
            all_doctors = doctor_data['all_doctors']
    except FileNotFoundError:
        flash('Doktor verileri yüklenemedi.', 'error')
        return redirect(url_for('dashboard'))

    matched_doctors = []
    complaint = None
    home_remedies = []
    doctor_recommendation = None
    
    if request.method == 'POST':
        complaint = request.form.get('complaint', '').strip()
        for pattern, doc in keyword_doctor_map:
            if re.search(pattern, complaint, re.IGNORECASE):
                matched_doctors = [doc]
                home_remedies = doc.get('home_remedies', [])
                doctor_recommendation = doc.get('recommendation', '')
                break
    if not matched_doctors and request.method == 'POST':
        matched_doctors = all_doctors
        home_remedies = []
        doctor_recommendation = None
        flash('Şikayetinizle tam eşleşen bir uzman bulunamadı. Tüm doktorlar listeleniyor.', 'warning')
        
    return render_template('doctor_recommendation.html', 
                         complaint=complaint, 
                         matched_doctors=matched_doctors,
                         home_remedies=home_remedies,
                         doctor_recommendation=doctor_recommendation)

def analyze_blood_test(results):
    comments = []
    general_recommendations = []
    lifestyle_recommendations = []
    
    # Load blood test references
    try:
        with open('blood_test_references.json', 'r', encoding='utf-8') as f:
            references = json.load(f)
    except FileNotFoundError:
        return "Referans değerleri yüklenemedi."

    # Hemogram analizleri
    for test_key, test_data in results['hemogram'].items():
        if test_key in references['hemogram'] and test_data not in [None, '']:
            try:
                value = float(test_data)
                ref = references['hemogram'][test_key]
                ref_range = ref['reference_range']
                
                if 'min' in ref_range and value < ref_range['min']:
                    comments.append(ref['low']['comment'])
                    general_recommendations.extend(ref['low']['recommendations'])
                elif 'max' in ref_range and value > ref_range['max']:
                    comments.append(ref['high']['comment'])
                    general_recommendations.extend(ref['high']['recommendations'])
                else:
                    comments.append(ref['normal']['comment'])
            except Exception as e:
                comments.append(f"{ref['name']} değeri analiz edilemedi: {e}")

    # Biyokimya analizleri
    for test_key, test_data in results['biyokimya'].items():
        if test_key in references['biyokimya'] and test_data not in [None, '']:
            try:
                value = float(test_data)
                ref = references['biyokimya'][test_key]
                ref_range = ref['reference_range']
                
                if 'min' in ref_range and value < ref_range['min']:
                    comments.append(ref['low']['comment'])
                    general_recommendations.extend(ref['low']['recommendations'])
                elif 'max' in ref_range and value > ref_range['max']:
                    comments.append(ref['high']['comment'])
                    general_recommendations.extend(ref['high']['recommendations'])
                else:
                    comments.append(ref['normal']['comment'])
            except Exception as e:
                comments.append(f"{ref['name']} değeri analiz edilemedi: {e}")

    # Lipid profili analizi
    lipid_status = []
    for test_key, test_data in results['biyokimya'].items():
        if test_key in references['lipid'] and test_data not in [None, '']:
            try:
                value = float(test_data)
                ref = references['lipid'][test_key]
                ref_range = ref['reference_range']
                
                if 'min' in ref_range and value < ref_range['min']:
                    lipid_status.append(f"düşük {ref['name']}")
                    general_recommendations.extend(ref['low']['recommendations'])
                elif 'max' in ref_range and value > ref_range['max']:
                    lipid_status.append(f"yüksek {ref['name']}")
                    general_recommendations.extend(ref['high']['recommendations'])
            except Exception as e:
                comments.append(f"{ref['name']} değeri analiz edilemedi: {e}")

    if lipid_status:
        comments.append(f'Lipid profilinizde {", ".join(lipid_status)} tespit edildi. Kardiyovasküler risk faktörlerini azaltmak için öneriler:')
        lifestyle_recommendations.extend(references['lifestyle_recommendations']['lipid_abnormal'])

    # Vitamin ve mineral analizleri
    vitamin_status = []
    for test_key, test_data in results['vitamin_mineral'].items():
        if test_key in references['vitamin_mineral'] and test_data not in [None, '']:
            try:
                value = float(test_data)
                ref = references['vitamin_mineral'][test_key]
                ref_range = ref['reference_range']
                
                if 'min' in ref_range and value < ref_range['min']:
                    vitamin_status.append(f"düşük {ref['name']}")
                    general_recommendations.extend(ref['low']['recommendations'])
            except Exception as e:
                comments.append(f"{ref['name']} değeri analiz edilemedi: {e}")

    if vitamin_status:
        comments.append(f'Vitamin profilinizde {", ".join(vitamin_status)} tespit edildi. Öneriler:')
        lifestyle_recommendations.extend(references['lifestyle_recommendations']['vitamin_deficiency'])

    # Genel değerlendirme ve öneriler
    if not comments:
        comments.append('Tüm değerler referans aralığında görünüyor.')
        lifestyle_recommendations.extend(references['lifestyle_recommendations']['all_normal'])

    # Sonuç raporu oluşturma
    report = []
    report.append("KAN TAHLİLİ ANALİZ RAPORU")
    report.append("=" * 30)
    report.append("\nDEĞERLENDİRME:")
    report.extend(comments)
    
    if general_recommendations:
        report.append("\nÖNERİLER:")
        report.extend([f"• {rec}" for rec in set(general_recommendations)])
    
    if lifestyle_recommendations:
        report.append("\nYAŞAM TARZI ÖNERİLERİ:")
        report.extend([f"• {rec}" for rec in set(lifestyle_recommendations)])
    
    report.append("\nNOT: Bu değerlendirme genel bilgi amaçlıdır. Kesin tanı ve tedavi için mutlaka bir hekime başvurunuz.")
    
    return "\n".join(report)

@app.route('/blood-test', methods=['GET', 'POST'])
@login_required
def blood_test():
    if request.method == 'POST':
        # Get form data
        test_date = request.form.get('test_date')
        # Create a dictionary of all blood test results
        results = {
            'hemogram': {
                'hgb': request.form.get('hgb'),
                'hct': request.form.get('hct'),
                'wbc': request.form.get('wbc'),
                'rbc': request.form.get('rbc'),
                'plt': request.form.get('plt'),
                'mcv': request.form.get('mcv')
            },
            'biyokimya': {
                'glucose': request.form.get('glucose'),
                'urea': request.form.get('urea'),
                'creatinine': request.form.get('creatinine'),
                'alt': request.form.get('alt'),
                'ast': request.form.get('ast'),
                'cholesterol': request.form.get('cholesterol'),
                'hdl': request.form.get('hdl'),
                'ldl': request.form.get('ldl'),
                'triglycerides': request.form.get('triglycerides')
            },
            'vitamin_mineral': {
                'vitamin_d': request.form.get('vitamin_d'),
                'vitamin_b12': request.form.get('vitamin_b12'),
                'iron': request.form.get('iron'),
                'ferritin': request.form.get('ferritin'),
                'folic_acid': request.form.get('folic_acid')
            }
        }
        notes = request.form.get('notes')
        # Otomatik analiz ve öneri
        auto_comment = analyze_blood_test(results)
        # Kullanıcı notu varsa ekle
        if notes:
            recommendations = auto_comment + '\n\nKullanıcı Notu: ' + notes
        else:
            recommendations = auto_comment
        # Save to database
        test_result = TestResult(
            user_id=current_user.id,
            date=datetime.strptime(test_date, '%Y-%m-%d'),
            results_data=results,
            recommendations=recommendations
        )
        db.session.add(test_result)
        db.session.commit()
        flash('Tahlil sonuçları başarıyla kaydedildi.')
        return redirect(url_for('dashboard'))
    return render_template('main/blood_test.html')

@app.route('/blood-test-detail/<int:test_id>')
@login_required
def blood_test_detail(test_id):
    test_result = TestResult.query.get_or_404(test_id)
    if test_result.user_id != current_user.id:
        flash('Bu tahlil sonucuna erişim yetkiniz yok.', 'error')
        return redirect(url_for('dashboard'))
    return render_template('main/blood_test_detail.html', test_result=test_result)

@app.route('/kriz_analizleri', methods=['GET', 'POST'])
@login_required
def kriz_analizleri():
    prediction = None
    prediction_type = None
    
    # Get user's blood test results and ensure proper serialization
    blood_tests = TestResult.query.filter_by(user_id=current_user.id).order_by(TestResult.date.desc()).all()
    
    # Debug için kan tahlili sonuçlarını kontrol et
    for test in blood_tests:
        if test.results_data:
            print(f"Test ID: {test.id}, Date: {test.date}")
            print(f"Results data: {test.results_data}")
    
    if request.method == 'POST':
        try:
            prediction_type = request.form.get('prediction_type')
            
            if prediction_type == 'diabetes':
                # Get diabetes form data
                pregnancies = float(request.form.get('pregnancies'))
                glucose = float(request.form.get('glucose'))
                blood_pressure = float(request.form.get('blood_pressure'))
                skin_thickness = float(request.form.get('skin_thickness'))
                insulin = float(request.form.get('insulin'))
                bmi = float(request.form.get('bmi'))
                diabetes_pedigree = float(request.form.get('diabetes_pedigree'))
                age = float(request.form.get('age'))

                # Load the diabetes model
                diabetes_model = pickle.load(open('saved_models/diabetes_model.sav', 'rb'))

                # Make prediction
                prediction = diabetes_model.predict([[pregnancies, glucose, blood_pressure, skin_thickness, insulin, bmi, diabetes_pedigree, age]])[0]
                
            elif prediction_type == 'heart':
                # Get heart disease form data
                age = float(request.form.get('heart_age'))
                sex = float(request.form.get('sex'))
                cp = float(request.form.get('cp'))
                trestbps = float(request.form.get('trestbps'))
                chol = float(request.form.get('chol'))
                fbs = float(request.form.get('fbs'))
                restecg = float(request.form.get('restecg'))
                thalach = float(request.form.get('thalach'))
                exang = float(request.form.get('exang'))
                oldpeak = float(request.form.get('oldpeak'))
                slope = float(request.form.get('slope'))
                ca = float(request.form.get('ca'))
                thal = float(request.form.get('thal'))

                # Load the heart disease model
                heart_disease_model = pickle.load(open('saved_models/heart_disease_model.sav', 'rb'))

                # Make prediction
                prediction = heart_disease_model.predict([[age, sex, cp, trestbps, chol, fbs, restecg, thalach, exang, oldpeak, slope, ca, thal]])[0]

        except Exception as e:
            flash(f'Bir hata oluştu: {str(e)}', 'error')
            return redirect(url_for('kriz_analizleri'))

    return render_template('kriz_analizleri.html', 
                         prediction=prediction, 
                         prediction_type=prediction_type,
                         blood_tests=blood_tests)

@app.route('/search-food', methods=['GET'])
@login_required
def search_food():
    query = request.args.get('query', '').lower()
    if not query:
        return jsonify([])
    
    # Besin veritabanında arama yap
    results = []
    for food in FOOD_DB:
        if query in food.get('name', '').lower():
            results.append({
                'id': food.get('id'),
                'name': food.get('name'),
                'calories': food.get('calories'),
                'protein': food.get('protein'),
                'carbs': food.get('carbs'),
                'fat': food.get('fat'),
                'portion': food.get('portion', 100)  # Varsayılan porsiyon 100g
            })
    
    return jsonify(results[:10])  # İlk 10 sonucu döndür

@app.route('/calculate-nutrition', methods=['POST'])
@login_required
def calculate_nutrition():
    data = request.get_json()
    food_id = data.get('food_id')
    portion = float(data.get('portion', 100))
    
    # Besin bilgilerini bul
    food = next((f for f in FOOD_DB if f.get('id') == food_id), None)
    if not food:
        return jsonify({'error': 'Besin bulunamadı'}), 404
    
    # Porsiyon oranına göre besin değerlerini hesapla
    ratio = portion / food.get('portion', 100)
    nutrition = {
        'calories': round(food.get('calories', 0) * ratio, 1),
        'protein': round(food.get('protein', 0) * ratio, 1),
        'carbs': round(food.get('carbs', 0) * ratio, 1),
        'fat': round(food.get('fat', 0) * ratio, 1)
    }
    
    return jsonify(nutrition)

@app.route('/health-journal', methods=['GET', 'POST'])
@login_required
def health_journal():
    if request.method == 'POST':
        entry = HealthJournal(
            user_id=current_user.id,
            date=request.form.get('date'),
            mood=request.form.get('mood'),
            sleep_hours=request.form.get('sleep_hours'),
            exercise=request.form.get('exercise'),
            nutrition=request.form.get('nutrition'),
            complaints=request.form.get('complaints')
        )
        db.session.add(entry)
        db.session.commit()
        flash('Günlük kaydınız eklendi.', 'success')
        return redirect(url_for('health_journal'))
    entries = HealthJournal.query.filter_by(user_id=current_user.id).order_by(HealthJournal.date.desc()).limit(30).all()
    return render_template('health_journal.html', entries=entries)

@app.route('/chronic-tracking', methods=['GET', 'POST'])
@login_required
def chronic_tracking():
    if request.method == 'POST':
        disease_type = request.form.get('disease_type')
        measurement_type = request.form.get('measurement_type')
        value = request.form.get('value')
        note = request.form.get('note')
        date_str = request.form.get('date')
        try:
            entry_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else date.today()
        except Exception:
            entry_date = date.today()
        entry = ChronicMeasurement(
            user_id=current_user.id,
            date=entry_date,
            disease_type=disease_type,
            measurement_type=measurement_type,
            value=value,
            note=note
        )
        db.session.add(entry)
        db.session.commit()
        flash('Ölçüm kaydedildi.', 'success')
        return redirect(url_for('chronic_tracking'))
    # Son 30 ölçüm
    measurements = ChronicMeasurement.query.filter_by(user_id=current_user.id).order_by(ChronicMeasurement.date.desc()).limit(30).all()
    return render_template('chronic_tracking.html', measurements=measurements)

@app.route('/chronic-tracking/data')
@login_required
def chronic_tracking_data():
    # Tüm ölçümleri JSON olarak döndür (grafik için)
    measurements = ChronicMeasurement.query.filter_by(user_id=current_user.id).order_by(ChronicMeasurement.date.asc()).all()
    data = [
        {
            'date': m.date.strftime('%Y-%m-%d'),
            'disease_type': m.disease_type,
            'measurement_type': m.measurement_type,
            'value': m.value
        }
        for m in measurements
    ]
    return jsonify(data)

@app.route('/mood-stress-test', methods=['GET', 'POST'])
@login_required
def mood_stress_test():
    # Load test data from JSON file
    try:
        with open('mood_test_data.json', 'r', encoding='utf-8') as f:
            test_data = json.load(f)
            questions = test_data['questions']
            feedback_data = test_data['feedback']
            general_analysis_data = test_data['general_analysis']
    except FileNotFoundError:
        flash('Test verileri yüklenemedi.', 'error')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        scores = {}
        counts = {}
        answers = {}
        for q in questions:
            val = request.form.get(q['id'])
            if val is not None:
                answers[q['id']] = int(val)
                cat = q['category']
                scores[cat] = scores.get(cat, 0) + int(val)
                counts[cat] = counts.get(cat, 0) + 1

        # Ortalama skorlar
        avgs = {cat: round(scores[cat]/counts[cat], 2) if counts[cat] else 0 for cat in scores}
        
        # Yorumlar ve emojiler
        feedback = {}
        for cat in avgs:
            avg = avgs[cat]
            cat_feedback = feedback_data[cat]
            
            # Find appropriate feedback level based on thresholds
            feedback_level = None
            for level, data in cat_feedback.items():
                if 'threshold' in data and avg >= data['threshold']:
                    feedback_level = level
                    break
            
            # If no threshold matched, use the lowest level
            if feedback_level is None:
                feedback_level = list(cat_feedback.keys())[-1]
            
            feedback[cat] = {
                'avg': avg,
                'text': cat_feedback[feedback_level]['text'],
                'emoji': cat_feedback[feedback_level]['emoji']
            }

        # Genel analiz
        low_cats = [cat for cat, v in feedback.items() if v['avg'] < 1.2]
        high_cats = [cat for cat, v in feedback.items() if v['avg'] > 2.2]
        
        general_analysis = ""
        if len(low_cats) >= general_analysis_data['multiple_low']['threshold']:
            general_analysis = general_analysis_data['multiple_low']['text']
        elif ('stress' in feedback and 
              feedback['stress']['avg'] > general_analysis_data['stress_motivation']['stress_threshold'] and 
              'motivation' in feedback and 
              feedback['motivation']['avg'] < general_analysis_data['stress_motivation']['motivation_threshold']):
            general_analysis = general_analysis_data['stress_motivation']['text']
        elif len(high_cats) >= general_analysis_data['multiple_high']['threshold']:
            general_analysis = general_analysis_data['multiple_high']['text']
        else:
            # Kategoriye özel öneriler
            suggestions = []
            for cat in feedback:
                if feedback[cat]['avg'] < 1.5:
                    if cat in feedback_data and 'low' in feedback_data[cat]:
                        suggestions.append(feedback_data[cat]['low']['text'])
            
            if suggestions:
                general_analysis = "\n".join(suggestions)
            else:
                general_analysis = general_analysis_data['default']

        # Kaydet
        test = MoodStressTest(
            user_id=current_user.id,
            mood_score=scores.get('mood', 0),
            stress_score=scores.get('stress', 0),
            result_json=feedback
        )
        db.session.add(test)
        db.session.commit()
        
        return render_template('mood_stress_test.html', 
                             questions=questions, 
                             result=feedback, 
                             answers=answers, 
                             general_analysis=general_analysis)
    
    return render_template('mood_stress_test.html', questions=questions)

@app.route('/health-trends')
@login_required
def health_trends():
    # Duygu & stres testleri
    mood_tests = MoodStressTest.query.filter_by(user_id=current_user.id).order_by(MoodStressTest.date.asc()).all()
    mood_data = [{'date': t.date.strftime('%Y-%m-%d'), 'mood': t.result_json.get('mood', {}).get('avg', None), 'stress': t.result_json.get('stress', {}).get('avg', None)} for t in mood_tests]
    # Kronik hastalık ölçümleri (ör: kan şekeri, tansiyon)
    chronic_measurements = ChronicMeasurement.query.filter_by(user_id=current_user.id).order_by(ChronicMeasurement.date.asc()).all()
    chronic_data = [{'date': m.date.strftime('%Y-%m-%d'), 'type': m.measurement_type, 'value': m.value} for m in chronic_measurements]
    # Son 30 gün için stres değişimi
    import datetime
    today = datetime.date.today()
    last_30 = [t for t in mood_tests if t.date.date() >= today - datetime.timedelta(days=30)]
    if len(last_30) >= 2:
        first = last_30[0].result_json.get('stress', {}).get('avg', None)
        last = last_30[-1].result_json.get('stress', {}).get('avg', None)
        if first is not None and last is not None and first > 0:
            change = round(100 * (last - first) / first, 1)
            if change < 0:
                motivation = f"Son 1 ayda stres seviyen %{abs(change)} azaldı! Harika gidiyorsun."
            elif change > 0:
                motivation = f"Son 1 ayda stres seviyen %{change} arttı. Dilersen stres yönetimi için önerilerimize göz atabilirsin."
            else:
                motivation = "Son 1 ayda stres seviyende önemli bir değişiklik olmadı."
        else:
            motivation = "Yeterli veri yok."
    else:
        motivation = "Son 1 ayda yeterli stres testi verisi yok."
    return render_template('health_trends.html', mood_data=mood_data, chronic_data=chronic_data, motivation=motivation)

@app.route('/health-goals', methods=['GET', 'POST'])
@login_required
def health_goals():
    # Kullanıcının hedefleri
    goal = HealthGoal.query.filter_by(user_id=current_user.id).first()
    if not goal:
        goal = HealthGoal(user_id=current_user.id)
        db.session.add(goal)
        db.session.commit()
    message = None
    if request.method == 'POST':
        if 'update_goal' in request.form:
            goal.steps = int(request.form.get('steps', 8000))
            goal.water = float(request.form.get('water', 2.0))
            goal.sleep = float(request.form.get('sleep', 7.0))
            goal.weight = float(request.form.get('weight') or 0) or None
            goal.calories = int(request.form.get('calories') or 0) or None
            db.session.commit()
            message = 'Hedefleriniz güncellendi.'
        elif 'add_entry' in request.form:
            entry = HealthGoalEntry(
                user_id=current_user.id,
                date=request.form.get('date') or date.today(),
                steps=int(request.form.get('entry_steps', 0)),
                water=float(request.form.get('entry_water', 0)),
                sleep=float(request.form.get('entry_sleep', 0)),
                weight=float(request.form.get('entry_weight', 0)),
                calories=int(request.form.get('entry_calories', 0))
            )
            db.session.add(entry)
            db.session.commit()
            message = 'Günlük giriş kaydedildi.'
    # Son giriş (bugün)
    today_entry = HealthGoalEntry.query.filter_by(user_id=current_user.id, date=date.today()).first()
    # Son 7 gün girişleri
    last_entries = HealthGoalEntry.query.filter_by(user_id=current_user.id).order_by(HealthGoalEntry.date.desc()).limit(7).all()
    # Rozet/tebrik: bugünkü giriş hedefleri karşıladıysa
    congrats = False
    if today_entry:
        congrats = (
            (goal.steps and today_entry.steps and today_entry.steps >= goal.steps) and
            (goal.water and today_entry.water and today_entry.water >= goal.water) and
            (goal.sleep and today_entry.sleep and today_entry.sleep >= goal.sleep)
        )
    return render_template('health_goals.html', goal=goal, today_entry=today_entry, last_entries=last_entries, congrats=congrats, message=message)

@app.route('/health-library')
def health_library():
    try:
        with open('health_library_data.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            contents = data['contents']
    except FileNotFoundError:
        flash('Sağlık kütüphanesi içeriği yüklenemedi.', 'error')
        contents = []
    return render_template('health_library.html', contents=contents)

if __name__ == '__main__':
    app.run(debug=True) 