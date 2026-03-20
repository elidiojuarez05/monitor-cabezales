import streamlit as st
from streamlit_gsheets import GSheetsConnection
import json

# 🔑 CREDENCIALES DIRECTAS (SIN TOML)
creds = {
  "type": "service_account",
  "project_id": "aerial-episode-490722-d8",
  "private_key_id": "0b63769358d0b7f5d6c046d94a0a2592cfcdb517",
  "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQC6vWfA23OMbgTf\n1Plbez7rcG0kIidwqwmXfrc2T5NI6KBhgBFXokM8mSc5LZAoT3Yc1Gd/MLqEPxqM\n8kKapa8gh0eOoxpElExoSmoLqrSY71PpoLGeux3PWZ5nBpjRVRlki765yomGvVPP\nw3MRf29YZ/WRzcj+1rdaASM9MXuFNVCwNTY0t/OW7CAafqpCVf68aKxO2o5EDVr4\n/cwUZvUOIg06xjEFCO6Xp/s45lnV/bSv2GJhATa3WQBGTVAQRjZHbZUiUfyuAnnN\nKtI0zE0kRnOj82LbFYKfwkdy7oSFTr89XEsplwpTzT0IOHcTgH5RWe6t3R0HKbZX\n8ukKvSgTAgMBAAECggEAJn5jtFQocgK923wV+N8jfbn7rY6iza1cOU/kKXxm0okt\nglu5d3SZ4pR5iuZTCJQ0t0WrngLn99ngOby4sRNFUfHA9Oy3PfrJ81efm48RUlNH\nW2oGIz/UKcmCBx/LgZ9GsDzEUJ0pE07Ux4e1IR7BT5qCew9OBwYw3otMfdFE8pTM\nO04myQ+FHMHEezYdEhAGB7vOP30YUnIByf68BGIuBdHb5+LnxqOO3imBXBjy6KQH\n+8IRI60I3zuP79F2hR0eSu3fmOWMzG9HFuTgpxloq+HnPpOmG9Pu/r7Os5hvtxya\nTzehVHGocCIbowGUUkVlU26JEfXYjJfMJ5ynBMreqQKBgQDjNojGDSA52OkFwT7T\nMiWXIOiPczlRFDAlH++Roej6GXQXttq2LMtHzbW3sH/OJ7MxwEJfEbd/EtTsW6/k\nWZip6b8fb0J9piT5kiskJbx+pzYCzbfn7pMJQJvMe2Mxo0+m4iZDmV+QqBqx7Hte\n8RM4g2D9oldGhuvGxN/W9SmcmQKBgQDSZihd8KbkNmubCTRQOUxrhAGJ/iPcxT9M\ndGnlm4YXrvTkiCPEQ6Gq4yRsTQ3QWkKUJWlU5veKmCSgFGQq4q0khWWRy/BIUF/i\nI9LwX52N3WI+cNDij1CJJNO84ChkLtJbR8KpzwQYePfpsXl5zb8Os8vQISyh4QVF\nkdPVUFnJiwKBgQCH8wBhaEco9aVvwRHDMlUVmSYtducLoUWxYOtqOvN4ebRh4BH7\nQNAc1XPuRdgi1NQ+Z2gPFD2z9eOazL1wpz9WIzstJtgk8D1dat0PUtj2+zuw78Aj\nMTefKJ5P+l/+ulWVZ+k3N1Tb7AmU/gdPZnV2sf1dpT4NP/thQjkgmC5euQKBgQCM\nFc6ctWU5H27H2/oDzBKwp0SrDxXroT0C96OmZ8WBMVEGdAp0W59hezi+DxO6fM5F\nex9Fkz6P/bqtBsamsyQa4+J7j3CdhT5CAB4rQ05QrW0DK/Q4VLmHhoigAhOCmJYg\nhof6rcYJUUmnRC4gRjgGXvm9ysi/w2XSK0UCiyws/wKBgEsQoprrg/ms05KgWfyk\njxFfTF1Mk+wLqFIvWAK9dTfRHBOy22eoVobWoEJCarxJPkb2kZHhuVid6Ya9u9dn\nuIKojpMNIjY7wJprnOZ9AG9VKBX/IzGCKq8dySnksWGv6+z0BxqRBrbGwlMdhZ88\ny0TvUURexaWRheF8RwCjNT4n\n-----END PRIVATE KEY-----\n",
  "client_email": "lector-dashboard@aerial-episode-490722-d8.iam.gserviceaccount.com",
  "client_id": "101821350316171101830",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/lector-dashboard%40aerial-episode-490722-d8.iam.gserviceaccount.com",
  "universe_domain": "googleapis.com"
}

# 🔌 CONEXIÓN MANUAL
conn = GSheetsConnection(
    connection_name="gsheets",
    service_account_info=creds
)

df = conn.read()

st.write(df))

