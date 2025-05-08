from app import app, db
from sqlalchemy import text, inspect

def migrate():
    with app.app_context():
        inspector = inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns('user')]
        
        # Add new columns if they don't exist
        if 'activity_level' not in columns:
            try:
                db.session.execute(text('ALTER TABLE user ADD COLUMN activity_level VARCHAR(20) DEFAULT "sedentary"'))
                print("Added activity_level column")
            except Exception as e:
                print(f"Error adding activity_level column: {e}")

        if 'goal' not in columns:
            try:
                db.session.execute(text('ALTER TABLE user ADD COLUMN goal VARCHAR(20) DEFAULT "maintain"'))
                print("Added goal column")
            except Exception as e:
                print(f"Error adding goal column: {e}")

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
                        calories FLOAT NOT NULL,
                        protein FLOAT,
                        carbs FLOAT,
                        fat FLOAT,
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