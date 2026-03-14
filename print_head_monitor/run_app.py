import streamlit.web.cli as stcli
import os, sys

def resolve_path(path):
    resolved_path = getattr(sys, '_MEIPASS', os.path.abspath(os.getcwd()))
    return os.path.join(resolved_path, path)

if __name__ == "__main__":
    # Indicamos a Streamlit dónde está el script principal dentro del EXE
    sys.argv = [
        "streamlit",
        "run",
        resolve_path("dashboard/dashboard.py"),
        "--global.developmentMode=false",
    ]
    sys.exit(stcli.main())