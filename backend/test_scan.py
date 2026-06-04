import google.generativeai as genai
import sys

endpoint = "https://gcli.ggchan.dev/"
clean_endpoint = endpoint.replace("https://", "").replace("http://", "").rstrip("/")

print(f"Testing connection to clean endpoint: '{clean_endpoint}'")
client_options = {'api_endpoint': clean_endpoint}

try:
    # Use standard invalid key to test connection endpoint
    genai.configure(api_key="AIzaSyDummyKeyForTesting", client_options=client_options)
    print("Configured. Listing models with 5s timeout...")
    for m in genai.list_models(request_options={"timeout": 5.0}):
        print(m.name)
except Exception as e:
    print("Error occurred:")
    print(e)
