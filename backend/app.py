from flask import Flask, request, jsonify
import rarfile
import itertools
import string
import os

app = Flask(__name__)

# Brute-force function (simple 4-digit demo)
def brute_force_rar(rar_path, max_length=4, charset=string.digits):
    with rarfile.RarFile(rar_path) as rf:
        for length in range(1, max_length + 1):
            for attempt in itertools.product(charset, repeat=length):
                password = ''.join(attempt)
                try:
                    rf.extractall(pwd=password.encode())
                    return password  # Success!
                except:
                    continue
    return None  # Failed

@app.route('/crack', methods=['POST'])
def crack():
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    file = request.files['file']
    if not file.filename.endswith('.rar'):
        return jsonify({"error": "Only RAR files are supported"}), 400

    temp_path = "temp.rar"
    file.save(temp_path)
    
    password = brute_force_rar(temp_path)
    os.remove(temp_path)  # Clean up

    if password:
        return jsonify({"password": password})
    else:
        return jsonify({"error": "Password not found"}), 404

if __name__ == '__main__':
    app.run(debug=True)