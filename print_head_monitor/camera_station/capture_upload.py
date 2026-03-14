import requests

url = "http://192.168.1.100:8051/upload"

files = {"file": open("test.jpg","rb")}

data = {
    "machine":"HP_12000",
    "shift":"Turno 1"
}

requests.post(url,files=files,data=data)