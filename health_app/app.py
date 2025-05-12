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

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///health_app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

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
    calories = db.Column(db.Float, nullable=False)
    protein = db.Column(db.Float)
    carbs = db.Column(db.Float)
    fat = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

def init_db():
    # Create all tables
    db.create_all()
    print("Database tables created successfully!")

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
                         daily_goal=daily_goal)

@app.route('/add-meal', methods=['POST'])
@login_required
def add_meal():
    meal_type = request.form.get('meal_type')
    food_name = request.form.get('food_name')
    calories = request.form.get('calories')
    protein = request.form.get('protein')
    carbs = request.form.get('carbs')
    fat = request.form.get('fat')
    
    if not all([meal_type, food_name, calories]):
        flash('Lütfen gerekli alanları doldurun.', 'error')
        return redirect(url_for('meals'))
    
    try:
        meal = Meal(
            user_id=current_user.id,
            meal_type=meal_type,
            food_name=food_name,
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
    # Priority-ordered keyword-doctor mapping
    keyword_doctor_map = [
        (r'baş ağrısı|migren|başım ağrıyor|bas agrisi', {
            'name': 'Dr. Ahmet Can',
            'specialty': 'Nöroloji Uzmanı',
            'rating': 4.6
        }),
        (r'karın ağrısı|mide|ishal|kabızlık|karin agrisi|karin ağrısı', {
            'name': 'Dr. Ayşe Yılmaz',
            'specialty': 'Dahiliye Uzmanı',
            'rating': 4.8
        }),
        (r'göğüs ağrısı|çarpıntı|kalp|nefes darlığı|gogus agrisi', {
            'name': 'Dr. Mehmet Demir',
            'specialty': 'Kardiyoloji Uzmanı',
            'rating': 4.7
        }),
        (r'cilt|döküntü|kaşıntı|sivilce|egzama|leke', {
            'name': 'Dr. Zeynep Yıldız',
            'specialty': 'Dermatoloji Uzmanı',
            'rating': 4.8
        }),
        (r'diyabet|şeker|tiroid|hormon|obezite|kilo|zayıflık', {
            'name': 'Dr. Elif Kaya',
            'specialty': 'Endokrinoloji Uzmanı',
            'rating': 4.9
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
    if request.method == 'POST':
        complaint = request.form.get('complaint', '').lower()
        for pattern, doc in keyword_doctor_map:
            if re.search(pattern, complaint):
                matched_doctors = [doc]
                break
    if not matched_doctors and request.method == 'POST':
        matched_doctors = all_doctors
    return render_template('doctor_recommendation.html', complaint=complaint, matched_doctors=matched_doctors)

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
        
        # Save to database
        test_result = TestResult(
            user_id=current_user.id,
            date=datetime.strptime(test_date, '%Y-%m-%d'),
            results_data=results,
            recommendations=notes
        )
        db.session.add(test_result)
        db.session.commit()
        
        flash('Tahlil sonuçları başarıyla kaydedildi.')
        return redirect(url_for('dashboard'))
    
    return render_template('main/blood_test.html')

if __name__ == '__main__':
    app.run(debug=True) 