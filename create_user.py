from database import SessionLocal, User
import bcrypt

def create_admin():
    db = SessionLocal()
    
    # Check if the user already exists
    if db.query(User).filter(User.username == "admin").first():
        print("Fout: Gebruiker 'admin' bestaat al!")
        db.close()
        return

    # Hash the password directly using bcrypt
    raw_password = "Welkom123!"
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(raw_password.encode('utf-8'), salt).decode('utf-8')
    
    # Create the user model
    admin_user = User(
        username="admin",
        password_hash=hashed_password,
        role="admin",             # Master role
        province_access="All"     # Access to everything
    )
    
    db.add(admin_user)
    db.commit()
    db.close()
    
    print("Succes: Admin gebruiker aangemaakt!")
    print("-> Gebruikersnaam: admin")
    print("-> Wachtwoord: Welkom123!")

if __name__ == "__main__":
    create_admin()
