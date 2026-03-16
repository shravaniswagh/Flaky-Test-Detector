import urllib.request, os, uuid, json

url = 'http://localhost:5000/upload-tests'
filename = 'repro_tests.py'

# 1. Upload
with open(filename, 'rb') as f:
    content = f.read()

boundary = '----Boundary' + uuid.uuid4().hex
body = (f'--{boundary}\r\n'
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f'Content-Type: text/plain\r\n\r\n').encode() + content + (f'\r\n--{boundary}--\r\n').encode()

req = urllib.request.Request(url, data=body, headers={'Content-Type': f'multipart/form-data; boundary={boundary}'})

try:
    with urllib.request.urlopen(req) as res:
        print("Upload Status:", res.status)
        print(res.read().decode())
except Exception as e:
    print("Upload Failed:", e)

# 2. Check Count
try:
    with urllib.request.urlopen('http://localhost:5000/flaky-tests') as res:
        data = json.loads(res.read().decode())
        print("Total Test Count:", data.get('count'))
except Exception as e:
    print("Fetch Count Failed:", e)
