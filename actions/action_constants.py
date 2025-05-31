# actions/action_constants.py
import os
from dotenv import load_dotenv
project_root = os.path.join(os.path.dirname(
    __file__), '..')
dotenv_path = os.path.join(project_root, '.env')
load_dotenv(dotenv_path=dotenv_path) 

API_ROOT_URL = os.getenv("API_ROOT_URL")

if not API_ROOT_URL:
    error_message = (
        "ERROR: API_ROOT_URL tidak ditemukan di environment variables. "
        "Pastikan variabel ini sudah diatur di file .env Anda dan file .env sudah dimuat dengan benar."
    )
    print(error_message)
