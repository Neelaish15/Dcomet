# Dcomet Project Setup Instructions

This project uses a virtual environment for dependency management and reproducibility.

## Setup Steps

1. **Create and Activate Virtual Environment**
   - The `.venv` folder is already created for you.
   - To activate on Windows (PowerShell):
     ```powershell
     .venv\Scripts\Activate.ps1
     ```
   - To activate on Windows (cmd):
     ```cmd
     .venv\Scripts\activate.bat
     ```

2. **Install Dependencies**
   - All required dependencies are installed in the virtual environment.
   - If you need to reinstall, run:
     ```powershell
     .venv\Scripts\python.exe -m pip install -r requirements.txt
     ```

3. **Run the Project**
   - To run the main scripts:
     ```powershell
     .venv\Scripts\python.exe "DSO DER.py"
     .venv\Scripts\python.exe "DSO SLD.py"
     ```

## Regenerating requirements.txt
If you add new dependencies, regenerate `requirements.txt` with:
```powershell
.venv\Scripts\python.exe -m pip freeze > requirements.txt
```

---

## Project Structure
- `DSO DER.py` — Main Python script
- `DSO SLD.py` — Secondary Python script
- `sketch_sep4a.ino` — Arduino sketch
- `.venv/` — Virtual environment (do not edit manually)
- `requirements.txt` — Python dependencies
- `README.md` — Project instructions (this file)
