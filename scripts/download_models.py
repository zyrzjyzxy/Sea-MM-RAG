
import os
import sys
import shutil
from pathlib import Path
from huggingface_hub import snapshot_download
from dotenv import load_dotenv, find_dotenv

# Load environment variables
load_dotenv(find_dotenv(), override=True)

# Define project paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "sea-rag-backend"
MODELS_DIR = BACKEND_DIR / "models"

# Define models to download
# Format: (Repo ID, Local Directory Name)
MODELS_TO_DOWNLOAD = [
    ("BAAI/bge-small-zh-v1.5", "bge-small-zh-v1.5"),
]

def check_tools():
    """Check for external tools (Tesseract, Poppler) and print status."""
    print("\n--- Checking External Tools ---")
    
    # Check Tesseract
    tesseract_path = os.getenv("TESSERACT_PATH")
    if tesseract_path and os.path.exists(tesseract_path):
        print(f"[OK] Tesseract found at configured path: {tesseract_path}")
    else:
        # Check PATH
        if shutil.which("tesseract"):
             print(f"[OK] Tesseract found in system PATH.")
        else:
             print(f"[ERROR] Tesseract NOT found. Please install it from https://github.com/UB-Mannheim/tesseract/wiki")
    
    # Check Poppler
    poppler_path = os.getenv("POPPLER_PATH")
    if poppler_path and os.path.exists(poppler_path):
        print(f"[OK] Poppler found at configured path: {poppler_path}")
    else:
        if shutil.which("pdftoppm"):
             print(f"[OK] Poppler found in system PATH.")
        else:
             print(f"[ERROR] Poppler NOT found. Please download from https://github.com/oschwartz10612/poppler-windows/releases/")

def main():
    print(f"Project Root: {PROJECT_ROOT}")
    print(f"Models Directory: {MODELS_DIR}")
    
    # Ensure models directory exists
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    
    print("\n--- Downloading Models ---")
    for repo_id, local_name in MODELS_TO_DOWNLOAD:
        local_dir = MODELS_DIR / local_name
        
        if local_dir.exists() and any(local_dir.iterdir()):
             print(f"[OK] Model '{repo_id}' already exists at {local_dir}. Skipping download.")
             continue
        
        print(f"[DOWNLOADING] '{repo_id}' to {local_dir}...")
        try:
            snapshot_download(
                repo_id=repo_id,
                local_dir=local_dir,
                local_dir_use_symlinks=False, # Important for Windows to avoid requirement of admin rights for symlinks usually
                resume_download=True
            )
            print(f"[OK] Successfully downloaded '{repo_id}'.")
        except Exception as e:
            print(f"[ERROR] Failed to download '{repo_id}': {e}")
    
    check_tools()
    print("\n--- Done ---")
    print("If you downloaded models to a new location, remember to update your .env file with the local path if necessary.")
    print(f"Example for .env:\nEMBEDDING_MODEL_NAME={MODELS_DIR / 'bge-small-zh-v1.5'}")

if __name__ == "__main__":
    main()
