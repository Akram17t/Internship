import requests

url = "http://localhost:11434/api/generate"

data = {
    "model": "llama3.1:latest",
    "prompt": "Say Hello, World!. Only respond with the text i mentioned, no other text or formatting.",
    "stream": False,
}

response = requests.post(url, json=data)
# print(response.status_code)
# print(response.text)

print(response.json()["response"])