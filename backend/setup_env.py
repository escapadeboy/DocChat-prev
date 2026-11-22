#!/usr/bin/env python3
"""
Helper script to generate a secure .env file from .env.example
"""
import secrets
import os
from pathlib import Path


def generate_secret_key(length: int = 32) -> str:
    """Generate a cryptographically secure random key."""
    return secrets.token_urlsafe(length)


def setup_env_file():
    """Create .env from .env.example with generated secrets."""
    backend_dir = Path(__file__).parent
    env_example = backend_dir / ".env.example"
    env_file = backend_dir / ".env"
    
    # Check if .env already exists
    if env_file.exists():
        print("⚠️  .env file already exists!")
        response = input("Do you want to overwrite it? (yes/no): ")
        if response.lower() != "yes":
            print("Cancelled. Keeping existing .env file.")
            return
    
    # Read .env.example
    if not env_example.exists():
        print(f"❌ Error: .env.example not found at {env_example}")
        return
    
    with open(env_example, 'r') as f:
        content = f.read()
    
    # Generate secure SECRET_KEY
    secret_key = generate_secret_key(32)
    
    # Replace placeholder SECRET_KEY
    content = content.replace(
        "SECRET_KEY=your-secret-key-change-in-production-use-strong-random-key",
        f"SECRET_KEY={secret_key}"
    )
    
    # Write .env file
    with open(env_file, 'w') as f:
        f.write(content)
    
    print("✅ Successfully created .env file with secure SECRET_KEY!")
    print(f"\n📝 Next steps:")
    print(f"1. Edit {env_file}")
    print(f"2. Set your DATABASE_URL")
    print(f"3. Set your OPENAI_API_KEY")
    print(f"4. Review other settings if needed")
    print(f"\n🔐 Generated SECRET_KEY length: {len(secret_key)} characters")


if __name__ == "__main__":
    setup_env_file()

