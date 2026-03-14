import dash
from dash import html

app = dash.Dash(__name__)

app.layout = html.Div("Dashboard funcionando")

if __name__ == "__main__":
    print("Servidor iniciando...")
    app.run_server(debug=True, host="0.0.0.0", port=8050)