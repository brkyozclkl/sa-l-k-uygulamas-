from app import app, db
from sqlalchemy import text, inspect
from flask import Flask
from flask_migrate import Migrate

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///health_app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
migrate = Migrate(app, db)

def migrate():
    with app.app_context():
        inspector = inspect(db.engine)
        
        # Create meals table if it doesn't exist
        if 'meal' not in inspector.get_table_names():
            try:
                db.session.execute(text('''
                    CREATE TABLE meal (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        date DATE NOT NULL,
                        meal_type VARCHAR(20),
                        food_name VARCHAR(100) NOT NULL,
                        portion FLOAT NOT NULL DEFAULT 100,
                        calories FLOAT NOT NULL,
                        protein FLOAT,
                        carbs FLOAT,
                        fat FLOAT,
                        food_id INTEGER,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES user (id)
                    )
                '''))
                print("Created meals table")
            except Exception as e:
                print(f"Error creating meals table: {e}")

        try:
            db.session.commit()
            print("Migration completed successfully!")
        except Exception as e:
            db.session.rollback()
            print(f"Error committing changes: {e}")

if __name__ == '__main__':
    migrate()
    with app.app_context():
        # Yeni kolonları ekle
        with db.engine.connect() as conn:
            conn.execute('ALTER TABLE meal ADD COLUMN food_id INTEGER')
            conn.execute('ALTER TABLE meal ADD COLUMN portion FLOAT NOT NULL DEFAULT 100')
            conn.commit()
        print("Veritabanı başarıyla güncellendi!") 