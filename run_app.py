import streamlit.web.cli as stcli
import os, sys

def resolve_path(path):
    if getattr(sys, 'frozen', False):
        # BUSCA DENTRO DEL EXE
        return os.path.join(sys._MEIPASS, path)
    return os.path.abspath(path)

if __name__ == "__main__":
    # Importante: headless=true evita que intente abrir 
    # una ventana de navegador antes de tiempo
    sys.argv = [
        "streamlit", "run", resolve_path("dashboard.py"),
        "--server.port=8501", "--server.headless=true"
    ]
    stcli.main()