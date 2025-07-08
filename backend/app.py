from flask import Flask, request, jsonify
from flask_cors import CORS
import itertools
import string
import os
import tempfile
import logging
import zipfile
import subprocess
import shutil

app = Flask(__name__)
CORS(app)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_rar_tools():
    """Check what RAR tools are available on the system"""
    tools = {}
    
    # Check for unrar
    if shutil.which('unrar'):
        tools['unrar'] = True
        logger.info("Found unrar tool")
    else:
        tools['unrar'] = False
    
    # Check for 7z
    if shutil.which('7z') or shutil.which('7za'):
        tools['7z'] = True
        logger.info("Found 7z tool")
    else:
        tools['7z'] = False
    
    # Check for WinRAR
    winrar_paths = [
        r"C:\Program Files\WinRAR\WinRAR.exe",
        r"C:\Program Files (x86)\WinRAR\WinRAR.exe"
    ]
    tools['winrar'] = any(os.path.exists(path) for path in winrar_paths)
    if tools['winrar']:
        logger.info("Found WinRAR")
    
    return tools

def brute_force_zip(zip_path, max_length=4, charset=string.digits):
    """Pure Python ZIP password cracker"""
    total_attempts = 0
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            # Check if ZIP file is encrypted
            encrypted = False
            for file_info in zf.filelist:
                if file_info.flag_bits & 0x1:
                    encrypted = True
                    break
            
            if not encrypted:
                return "NO_PASSWORD_NEEDED"
            
            # Try brute force
            for length in range(1, max_length + 1):
                logger.info(f"Trying passwords of length {length}")
                
                for attempt in itertools.product(charset, repeat=length):
                    password = ''.join(attempt)
                    total_attempts += 1
                    
                    if total_attempts % 100 == 0:
                        logger.info(f"Tried {total_attempts} passwords...")
                    
                    try:
                        first_file = zf.namelist()[0]
                        zf.read(first_file, pwd=password.encode('utf-8'))
                        logger.info(f"Password found: {password} (after {total_attempts} attempts)")
                        return password
                    except (RuntimeError, zipfile.BadZipFile):
                        continue
                        
            return None
            
    except Exception as e:
        raise Exception(f"Error processing ZIP file: {e}")

def brute_force_rar_with_7z(rar_path, max_length=4, charset=string.digits):
    """Brute force RAR using 7z command line tool"""
    total_attempts = 0
    
    # Find 7z executable
    sevenz_cmd = shutil.which('7z') or shutil.which('7za')
    if not sevenz_cmd:
        raise Exception("7z tool not found")
    
    # Test if file needs password
    try:
        result = subprocess.run([sevenz_cmd, 't', rar_path], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            return "NO_PASSWORD_NEEDED"
    except subprocess.TimeoutExpired:
        pass  # File probably needs password
    
    # Try brute force
    for length in range(1, max_length + 1):
        logger.info(f"Trying passwords of length {length}")
        
        for attempt in itertools.product(charset, repeat=length):
            password = ''.join(attempt)
            total_attempts += 1
            
            if total_attempts % 100 == 0:
                logger.info(f"Tried {total_attempts} passwords...")
            
            try:
                # Test password with 7z
                result = subprocess.run([sevenz_cmd, 't', rar_path, f'-p{password}'], 
                                      capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    logger.info(f"Password found: {password} (after {total_attempts} attempts)")
                    return password
            except subprocess.TimeoutExpired:
                continue
            except Exception:
                continue
    
    return None

def brute_force_archive(file_path, max_length=4, charset=string.digits):
    """Smart archive cracker that uses available tools"""
    file_ext = os.path.splitext(file_path)[1].lower()
    
    if file_ext == '.zip':
        return brute_force_zip(file_path, max_length, charset)
    elif file_ext == '.rar':
        tools = check_rar_tools()
        if tools['7z']:
            return brute_force_rar_with_7z(file_path, max_length, charset)
        else:
            available_tools = [tool for tool, available in tools.items() if available]
            if available_tools:
                raise Exception(f"RAR support requires 7z tool. Available: {', '.join(available_tools)}")
            else:
                raise Exception("RAR support requires 7z, unrar, or WinRAR. Please install one of these tools.")
    else:
        raise Exception(f"Unsupported file format: {file_ext}")

@app.route('/crack', methods=['POST'])
def crack():
    """Handle archive password cracking requests"""
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No file uploaded"}), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({"error": "No file selected"}), 400
            
        # Check file extension
        allowed_extensions = ['.zip', '.rar']
        file_ext = os.path.splitext(file.filename)[1].lower()
        if file_ext not in allowed_extensions:
            return jsonify({"error": "Only ZIP and RAR files are supported"}), 400

        # Create temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as temp_file:
            temp_path = temp_file.name
            file.save(temp_path)
        
        logger.info(f"Processing {file_ext.upper()} file: {file.filename}")
        
        # Attempt to crack the password
        password = brute_force_archive(temp_path)
        
        # Clean up temporary file
        try:
            os.unlink(temp_path)
        except Exception as e:
            logger.warning(f"Failed to delete temporary file: {e}")
        
        if password == "NO_PASSWORD_NEEDED":
            return jsonify({"message": "Archive is not password protected"}), 200
        elif password:
            return jsonify({"password": password}), 200
        else:
            return jsonify({"error": "Password not found within the search space"}), 404
            
    except Exception as e:
        logger.error(f"Error processing request: {e}")
        try:
            if 'temp_path' in locals():
                os.unlink(temp_path)
        except:
            pass
        return jsonify({"error": str(e)}), 500

@app.route('/status', methods=['GET'])
def status():
    """Health check endpoint with tool information"""
    tools = check_rar_tools()
    return jsonify({
        "status": "running", 
        "message": "Smart Archive Password Cracker API",
        "supported_formats": ["ZIP (native)", "RAR (requires external tools)"],
        "available_tools": tools
    }), 200

@app.errorhandler(413)
def too_large(e):
    return jsonify({"error": "File too large"}), 413

@app.errorhandler(500)
def internal_error(e):
    logger.error(f"Internal server error: {e}")
    return jsonify({"error": "Internal server error"}), 500

if __name__ == '__main__':
    logger.info("Starting Smart Archive Password Cracker API")
    
    # Check available tools
    tools = check_rar_tools()
    logger.info("Available tools:")
    for tool, available in tools.items():
        logger.info(f"  {tool}: {'✓' if available else '✗'}")
    
    logger.info("Configuration:")
    logger.info(f"  Max password length: 4")
    logger.info(f"  Character set: digits (0-9)")
    logger.info(f"  ZIP support: Always available (pure Python)")
    logger.info(f"  RAR support: {'Available' if any(tools.values()) else 'Requires 7z/unrar/WinRAR'}")
    
    app.run(debug=True, host='0.0.0.0', port=5001)