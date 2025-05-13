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

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///health_app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Besin veritabanını yükle
FOOD_DB = [
    {
        'id': 1,
        'name': 'Tavuk Göğsü (Izgara)',
        'calories': 165,
        'protein': 31,
        'carbs': 0,
        'fat': 3.6,
        'portion': 100
    },
    {
        'id': 2,
        'name': 'Pirinç Pilavı',
        'calories': 130,
        'protein': 2.7,
        'carbs': 28,
        'fat': 0.3,
        'portion': 100
    },
    {
        'id': 3,
        'name': 'Mercimek Çorbası',
        'calories': 90,
        'protein': 6,
        'carbs': 15,
        'fat': 1.5,
        'portion': 250
    },
    {
        'id': 4,
        'name': 'Salata (Karışık)',
        'calories': 50,
        'protein': 2,
        'carbs': 8,
        'fat': 1,
        'portion': 200
    },
    {
        'id': 5,
        'name': 'Yoğurt',
        'calories': 60,
        'protein': 3.5,
        'carbs': 4.7,
        'fat': 3.3,
        'portion': 100
    }
]  # Örnek besin veritabanı

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
    today = date.today()
    meals = Meal.query.filter_by(user_id=current_user.id, date=today).all()
    
    # Calculate daily totals
    daily_totals = {
        'calories': sum(meal.calories for meal in meals),
        'protein': sum(meal.protein or 0 for meal in meals),
        'carbs': sum(meal.carbs or 0 for meal in meals),
        'fat': sum(meal.fat or 0 for meal in meals)
    }
    
    daily_goal = current_user.calculate_daily_calories()
    
    return render_template('nutrition/meals.html',
                         meals=meals,
                         daily_totals=daily_totals,
                         daily_goal=daily_goal,
                         food_db=FOOD_DB)

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
    
    if not all([meal_type, food_name, calories]):
        flash('Lütfen gerekli alanları doldurun.', 'error')
        return redirect(url_for('meals'))
    
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
            fat=float(fat) if fat else None
        )
        db.session.add(meal)
        db.session.commit()
        flash('Öğün başarıyla eklendi.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Öğün eklenirken bir hata oluştu.', 'error')
        print(f"Hata detayı: {str(e)}")  # Hata detayını logla
    
    return redirect(url_for('meals'))

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
    # Priority-ordered keyword-doctor mapping with home remedies
    keyword_doctor_map = [
        (r'baş ağrısı|migren|başım ağrıyor|bas agrisi', {
            'name': 'Dr. Ahmet Can',
            'specialty': 'Nöroloji Uzmanı',
            'rating': 4.6,
            'home_remedies': [
                'Karanlık ve sessiz bir odada dinlenin',
                'Bol su için',
                'Başınıza soğuk kompres uygulayın',
                'Stresten uzak durun',
                'Düzenli uyku uyuyun'
            ],
            'recommendation': 'Baş ağrınızın şiddeti ve süresi önemli. Eğer ağrı şiddetli ve uzun süredir devam ediyorsa, mutlaka bir nöroloji uzmanına başvurmanızı öneririm. Ayrıca baş ağrınızın yanında bulantı, kusma veya görme bozukluğu gibi belirtiler varsa acil servise başvurmanız gerekebilir.'
        }),
        (r'karın ağrısı|mide|ishal|kabızlık|karin agrisi|karin ağrısı', {
            'name': 'Dr. Ayşe Yılmaz',
            'specialty': 'Dahiliye Uzmanı',
            'rating': 4.8,
            'home_remedies': [
                'Hafif ve sindirimi kolay yiyecekler tüketin',
                'Bol su için',
                'Sıcak su torbası kullanın',
                'Bitki çayları için (nane, papatya)',
                'Dinlenin ve stresten uzak durun'
            ],
            'recommendation': 'Karın ağrınızın yeri ve şiddeti önemli. Eğer ağrı şiddetli ve uzun süredir devam ediyorsa, mutlaka bir dahiliye uzmanına başvurmanızı öneririm. Ayrıca ateş, bulantı, kusma gibi belirtiler varsa acil servise başvurmanız gerekebilir.'
        }),
        (r'göğüs ağrısı|çarpıntı|kalp|nefes darlığı|gogus agrisi', {
            'name': 'Dr. Mehmet Demir',
            'specialty': 'Kardiyoloji Uzmanı',
            'rating': 4.7,
            'home_remedies': [
                'Dinlenin ve sakin kalın',
                'Derin nefes alın',
                'Stresten uzak durun',
                'Sigara ve alkolden kaçının',
                'Düzenli egzersiz yapın'
            ],
            'recommendation': 'Göğüs ağrısı ciddi bir belirti olabilir. Eğer ağrı şiddetli ve uzun süredir devam ediyorsa, mutlaka bir kardiyoloji uzmanına başvurmanızı öneririm. Ayrıca nefes darlığı, çarpıntı gibi belirtiler varsa acil servise başvurmanız gerekebilir.'
        }),
        (r'cilt|döküntü|kaşıntı|sivilce|egzama|leke', {
            'name': 'Dr. Zeynep Yıldız',
            'specialty': 'Dermatoloji Uzmanı',
            'rating': 4.8,
            'home_remedies': [
                'Cildinizi nemlendirin',
                'Güneşten korunun',
                'Hassas cilt ürünleri kullanın',
                'Bol su için',
                'Stresten uzak durun'
            ],
            'recommendation': 'Cilt sorunlarınızın şiddeti ve yaygınlığı önemli. Eğer sorun şiddetli ve yaygınsa, mutlaka bir dermatoloji uzmanına başvurmanızı öneririm. Ayrıca kaşıntı, yanma gibi belirtiler varsa acil servise başvurmanız gerekebilir.'
        }),
        (r'diyabet|şeker|tiroid|hormon|obezite|kilo|zayıflık', {
            'name': 'Dr. Elif Kaya',
            'specialty': 'Endokrinoloji Uzmanı',
            'rating': 4.9,
            'home_remedies': [
                'Düzenli beslenin',
                'Egzersiz yapın',
                'Bol su için',
                'Stresten uzak durun',
                'Düzenli uyku uyuyun'
            ],
            'recommendation': 'Hormonal sorunlar ciddiye alınmalıdır. Eğer belirtileriniz şiddetli ve uzun süredir devam ediyorsa, mutlaka bir endokrinoloji uzmanına başvurmanızı öneririm. Ayrıca kilo kaybı, halsizlik gibi belirtiler varsa acil servise başvurmanız gerekebilir.'
        }),
    ]
    all_doctors = [
        {'name': 'Dr. Ayşe Yılmaz', 'specialty': 'Dahiliye Uzmanı', 'rating': 4.8},
        {'name': 'Dr. Mehmet Demir', 'specialty': 'Kardiyoloji Uzmanı', 'rating': 4.7},
        {'name': 'Dr. Elif Kaya', 'specialty': 'Endokrinoloji Uzmanı', 'rating': 4.9},
        {'name': 'Dr. Ahmet Can', 'specialty': 'Nöroloji Uzmanı', 'rating': 4.6},
        {'name': 'Dr. Zeynep Yıldız', 'specialty': 'Dermatoloji Uzmanı', 'rating': 4.8},
    ]
    matched_doctors = []
    complaint = None
    home_remedies = []
    doctor_recommendation = None
    
    if request.method == 'POST':
        complaint = request.form.get('complaint', '').lower()
        for pattern, doc in keyword_doctor_map:
            if re.search(pattern, complaint):
                matched_doctors = [doc]
                home_remedies = doc.get('home_remedies', [])
                doctor_recommendation = doc.get('recommendation', '')
                break
    if not matched_doctors and request.method == 'POST':
        matched_doctors = all_doctors
        
    return render_template('doctor_recommendation.html', 
                         complaint=complaint, 
                         matched_doctors=matched_doctors,
                         home_remedies=home_remedies,
                         doctor_recommendation=doctor_recommendation)

def analyze_blood_test(results):
    comments = []
    general_recommendations = []
    lifestyle_recommendations = []
    
    # Hemogram
    hgb = results['hemogram'].get('hgb')
    hct = results['hemogram'].get('hct')
    wbc = results['hemogram'].get('wbc')
    plt = results['hemogram'].get('plt')
    mcv = results['hemogram'].get('mcv')
    
    # Biyokimya
    glucose = results['biyokimya'].get('glucose')
    urea = results['biyokimya'].get('urea')
    creatinine = results['biyokimya'].get('creatinine')
    alt = results['biyokimya'].get('alt')
    ast = results['biyokimya'].get('ast')
    cholesterol = results['biyokimya'].get('cholesterol')
    hdl = results['biyokimya'].get('hdl')
    ldl = results['biyokimya'].get('ldl')
    triglycerides = results['biyokimya'].get('triglycerides')
    
    # Vitamin ve Mineraller
    vitamin_d = results['vitamin_mineral'].get('vitamin_d')
    vitamin_b12 = results['vitamin_mineral'].get('vitamin_b12')
    iron = results['vitamin_mineral'].get('iron')
    ferritin = results['vitamin_mineral'].get('ferritin')
    folic_acid = results['vitamin_mineral'].get('folic_acid')

    # Hemogram analizleri
    if hgb not in [None, '']:
        try:
            hgb = float(hgb)
            if hgb < 12:
                comments.append('Hemoglobin (HGB) düşük (Referans: 12-17 g/dL). Bu durum anemi belirtisi olabilir.')
                general_recommendations.extend([
                    'Demir açısından zengin besinler tüketin (kırmızı et, karaciğer, yumurta)',
                    'C vitamini içeren besinlerle birlikte demir içeren besinleri tüketin',
                    'Çay ve kahve tüketimini yemeklerden 2 saat sonraya bırakın',
                    'Doktorunuza danışarak demir takviyesi kullanmayı düşünebilirsiniz'
                ])
            elif hgb > 17:
                comments.append('Hemoglobin (HGB) yüksek (Referans: 12-17 g/dL). Bu durum polisitemi veya dehidrasyon belirtisi olabilir.')
                general_recommendations.extend([
                    'Günlük su tüketiminizi artırın (en az 2-2.5 litre)',
                    'Düzenli egzersiz yapın',
                    'Sigara kullanıyorsanız bırakmayı düşünün'
                ])
            else:
                comments.append('Hemoglobin (HGB) değeriniz normal aralıkta (12-17 g/dL).')
        except Exception as e:
            comments.append(f'Hemoglobin (HGB) değeri analiz edilemedi: {e}')

    if wbc not in [None, '']:
        try:
            wbc = float(wbc)
            if wbc < 4:
                comments.append('Beyaz kan hücresi (WBC) düşük (Referans: 4-11 x10^9/L). Bağışıklık sisteminiz zayıf olabilir.')
                general_recommendations.extend([
                    'Bağışıklık sistemini güçlendiren besinler tüketin (C vitamini, çinko, probiyotikler)',
                    'Düzenli uyku uyuyun (7-8 saat)',
                    'Stresten uzak durun',
                    'Hijyen kurallarına dikkat edin'
                ])
            elif wbc > 11:
                comments.append('Beyaz kan hücresi (WBC) yüksek (Referans: 4-11 x10^9/L). Enfeksiyon veya iltihap belirtisi olabilir.')
                general_recommendations.extend([
                    'Dinlenmeye özen gösterin',
                    'Bol sıvı tüketin',
                    'Ateşiniz varsa doktorunuza başvurun',
                    'Enfeksiyon belirtileri varsa antibiyotik kullanımı için doktorunuza danışın'
                ])
            else:
                comments.append('Beyaz kan hücresi (WBC) değeriniz normal aralıkta (4-11 x10^9/L).')
        except Exception as e:
            comments.append(f'WBC değeri analiz edilemedi: {e}')

    # Biyokimya analizleri
    if glucose not in [None, '']:
        try:
            glucose = float(glucose)
            if glucose < 70:
                comments.append('Açlık glukozu düşük (Referans: 70-100 mg/dL). Hipoglisemi riski olabilir.')
                general_recommendations.extend([
                    'Düzenli ve sık öğünler tüketin',
                    'Kompleks karbonhidratları tercih edin',
                    'Şekerli gıdalardan kaçının',
                    'Öğün atlamamaya dikkat edin'
                ])
            elif glucose > 100:
                comments.append('Açlık glukozu yüksek (Referans: 70-100 mg/dL). İnsülin direnci veya diyabet riski olabilir.')
                general_recommendations.extend([
                    'Rafine şeker ve karbonhidratlardan kaçının',
                    'Lifli gıdalar tüketin',
                    'Düzenli egzersiz yapın',
                    'Kilo kontrolüne dikkat edin',
                    'Doktorunuza danışarak OGTT testi yaptırabilirsiniz'
                ])
            else:
                comments.append('Açlık glukozu değeriniz normal aralıkta (70-100 mg/dL).')
        except Exception as e:
            comments.append(f'Glukoz değeri analiz edilemedi: {e}')

    # Lipid profili analizi
    lipid_status = []
    if cholesterol not in [None, '']:
        try:
            cholesterol = float(cholesterol)
            if cholesterol > 200:
                lipid_status.append('yüksek kolesterol')
                general_recommendations.extend([
                    'Doymuş yağlardan kaçının',
                    'Zeytinyağı gibi sağlıklı yağları tercih edin',
                    'Haftada en az 2 kez balık tüketin',
                    'Lifli gıdalar tüketin',
                    'Düzenli egzersiz yapın'
                ])
        except Exception as e:
            comments.append(f'Kolesterol değeri analiz edilemedi: {e}')

    if hdl not in [None, '']:
        try:
            hdl = float(hdl)
            if hdl < 40:
                lipid_status.append('düşük HDL')
                general_recommendations.extend([
                    'Düzenli egzersiz yapın (özellikle kardiyovasküler egzersizler)',
                    'Omega-3 içeren besinler tüketin',
                    'Sigara kullanıyorsanız bırakın',
                    'Alkol tüketimini sınırlayın'
                ])
        except Exception as e:
            comments.append(f'HDL değeri analiz edilemedi: {e}')

    if ldl not in [None, '']:
        try:
            ldl = float(ldl)
            if ldl > 100:
                lipid_status.append('yüksek LDL')
                general_recommendations.extend([
                    'Doymuş yağlardan kaçının',
                    'Trans yağlardan uzak durun',
                    'Lifli gıdalar tüketin',
                    'Düzenli egzersiz yapın',
                    'Kilo kontrolüne dikkat edin'
                ])
        except Exception as e:
            comments.append(f'LDL değeri analiz edilemedi: {e}')

    if lipid_status:
        comments.append(f'Lipid profilinizde {", ".join(lipid_status)} tespit edildi. Kardiyovasküler risk faktörlerini azaltmak için öneriler:')
        lifestyle_recommendations.extend([
            'Akdeniz tipi beslenmeyi benimseyin',
            'Haftada en az 150 dakika orta şiddette egzersiz yapın',
            'Stres yönetimi için meditasyon veya yoga yapın',
            'Düzenli uyku uyuyun',
            'Sigara ve alkolden uzak durun'
        ])

    # Vitamin ve mineral analizleri
    vitamin_status = []
    if vitamin_d not in [None, '']:
        try:
            vitamin_d = float(vitamin_d)
            if vitamin_d < 30:
                vitamin_status.append('düşük D vitamini')
                general_recommendations.extend([
                    'Güneş ışığından yararlanın (günde 15-20 dakika)',
                    'Yağlı balık, yumurta sarısı ve mantar tüketin',
                    'Doktorunuza danışarak D vitamini takviyesi kullanmayı düşünebilirsiniz'
                ])
        except Exception as e:
            comments.append(f'D vitamini değeri analiz edilemedi: {e}')

    if vitamin_b12 not in [None, '']:
        try:
            vitamin_b12 = float(vitamin_b12)
            if vitamin_b12 < 200:
                vitamin_status.append('düşük B12 vitamini')
                general_recommendations.extend([
                    'Kırmızı et, balık, yumurta ve süt ürünleri tüketin',
                    'Vejetaryenseniz, B12 takviyesi için doktorunuza danışın',
                    'Düzenli olarak B12 seviyenizi kontrol ettirin'
                ])
        except Exception as e:
            comments.append(f'B12 vitamini değeri analiz edilemedi: {e}')

    if vitamin_status:
        comments.append(f'Vitamin profilinizde {", ".join(vitamin_status)} tespit edildi. Öneriler:')
        lifestyle_recommendations.extend([
            'Dengeli ve çeşitli beslenin',
            'Mevsiminde sebze ve meyve tüketin',
            'Düzenli olarak vitamin seviyelerinizi kontrol ettirin'
        ])

    # Genel değerlendirme ve öneriler
    if not comments:
        comments.append('Tüm değerler referans aralığında görünüyor.')
        lifestyle_recommendations.extend([
            'Mevcut sağlıklı yaşam tarzınızı sürdürün',
            'Düzenli check-up yaptırmaya devam edin',
            'Dengeli beslenme ve düzenli egzersiz alışkanlığınızı koruyun',
            'Stres yönetimi ve yeterli uyku için özen gösterin'
        ])

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

@app.route('/kriz-analizleri')
def kriz_analizleri():
    return render_template('kriz_analizleri.html')

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

if __name__ == '__main__':
    app.run(debug=True) 