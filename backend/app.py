from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import itertools
import string
import os
import tempfile
import logging
import zipfile
import subprocess
import shutil
import json
import time
import threading
from datetime import datetime

app = Flask(__name__)
CORS(app)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration constants
DEFAULT_CHARSET = string.digits + string.ascii_letters  # 0-9, a-z, A-Z
DEFAULT_MAX_LENGTH = 6  # Up to 6 characters
DEFAULT_CHARSET_NAME = "digits and letters (0-9, a-z, A-Z)"

# Global variables for progress tracking
progress_data = {
    'attempts': 0,
    'current_length': 0,
    'current_password': '',
    'status': 'idle',
    'start_time': None,
    'found': False,
    'password': None,
    'error': None,
    'total_combinations': 0,
    'charset': DEFAULT_CHARSET_NAME,
    'max_length': DEFAULT_MAX_LENGTH
}

progress_lock = threading.Lock()

def update_progress(attempts=None, current_length=None, current_password=None, 
                   status=None, found=None, password=None, error=None, 
                   total_combinations=None, charset=None, max_length=None):
    """Thread-safe progress update"""
    with progress_lock:
        if attempts is not None:
            progress_data['attempts'] = attempts
        if current_length is not None:
            progress_data['current_length'] = current_length
        if current_password is not None:
            progress_data['current_password'] = current_password
        if status is not None:
            progress_data['status'] = status
            if status == 'starting':
                progress_data['start_time'] = datetime.now().isoformat()
        if found is not None:
            progress_data['found'] = found
        if password is not None:
            progress_data['password'] = password
        if error is not None:
            progress_data['error'] = error
        if total_combinations is not None:
            progress_data['total_combinations'] = total_combinations
        if charset is not None:
            progress_data['charset'] = charset
        if max_length is not None:
            progress_data['max_length'] = max_length

def reset_progress():
    """Reset progress data"""
    with progress_lock:
        progress_data.update({
            'attempts': 0,
            'current_length': 0,
            'current_password': '',
            'status': 'idle',
            'start_time': None,
            'found': False,
            'password': None,
            'error': None,
            'total_combinations': 0,
            'charset': DEFAULT_CHARSET_NAME,
            'max_length': DEFAULT_MAX_LENGTH
        })

def calculate_total_combinations(max_length=DEFAULT_MAX_LENGTH, charset=DEFAULT_CHARSET):
    """Calculate total number of combinations"""
    total = 0
    for length in range(1, max_length + 1):
        total += len(charset) ** length
    return total

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

def brute_force_zip(zip_path, max_length=DEFAULT_MAX_LENGTH, charset=DEFAULT_CHARSET):
    """Pure Python ZIP password cracker with progress tracking"""
    total_attempts = 0
    charset_name = "digits and letters" if charset == DEFAULT_CHARSET else "digits"
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            # Check if ZIP file is encrypted
            encrypted = False
            for file_info in zf.filelist:
                if file_info.flag_bits & 0x1:
                    encrypted = True
                    break
            
            if not encrypted:
                update_progress(status='completed')
                return "NO_PASSWORD_NEEDED"
            
            update_progress(status='cracking', charset=charset_name, max_length=max_length)
            
            # Try brute force
            for length in range(1, max_length + 1):
                update_progress(current_length=length)
                logger.info(f"Trying passwords of length {length} with charset: {charset_name}")
                
                for attempt in itertools.product(charset, repeat=length):
                    if progress_data['status'] == 'stopped':
                        return None
                        
                    password = ''.join(attempt)
                    total_attempts += 1
                    
                    update_progress(attempts=total_attempts, current_password=password)
                    
                    if total_attempts % 1000 == 0:
                        logger.info(f"Tried {total_attempts} passwords...")
                    
                    try:
                        first_file = zf.namelist()[0]
                        zf.read(first_file, pwd=password.encode('utf-8'))
                        logger.info(f"Password found: {password} (after {total_attempts} attempts)")
                        update_progress(found=True, password=password, status='completed')
                        return password
                    except (RuntimeError, zipfile.BadZipFile):
                        continue
                        
            update_progress(status='completed')
            return None
            
    except Exception as e:
        error_msg = f"Error processing ZIP file: {e}"
        update_progress(error=error_msg, status='error')
        raise Exception(error_msg)

def brute_force_rar_with_tools(rar_path, max_length=DEFAULT_MAX_LENGTH, charset=DEFAULT_CHARSET):
    """Brute force RAR using available command line tools with progress tracking"""
    total_attempts = 0
    charset_name = "digits and letters" if charset == DEFAULT_CHARSET else "digits"
    
    # Find available tools in order of preference
    tools = check_rar_tools()
    
    # Try 7z first
    if tools['7z']:
        cmd_tool = shutil.which('7z') or shutil.which('7za')
        test_cmd = [cmd_tool, 't', rar_path]
        password_cmd = lambda pwd: [cmd_tool, 't', rar_path, f'-p{pwd}']
        logger.info("Using 7z tool")
    # Try unrar
    elif tools['unrar']:
        cmd_tool = shutil.which('unrar')
        test_cmd = [cmd_tool, 't', rar_path]
        password_cmd = lambda pwd: [cmd_tool, 't', f'-p{pwd}', rar_path]
        logger.info("Using unrar tool")
    # Try WinRAR
    elif tools['winrar']:
        winrar_paths = [
            r"C:\Program Files\WinRAR\WinRAR.exe",
            r"C:\Program Files (x86)\WinRAR\WinRAR.exe"
        ]
        cmd_tool = next((path for path in winrar_paths if os.path.exists(path)), None)
        if not cmd_tool:
            error_msg = "WinRAR executable not found"
            update_progress(error=error_msg, status='error')
            raise Exception(error_msg)
        test_cmd = [cmd_tool, 't', '-ibck', '-inul', '-y', rar_path]
        password_cmd = lambda pwd: [cmd_tool, 't', '-ibck', '-inul', '-y', f'-p{pwd}', rar_path]
        logger.info("Using WinRAR tool")
    else:
        error_msg = "No RAR tool found"
        update_progress(error=error_msg, status='error')
        raise Exception(error_msg)
    
    # Test if file needs password
    try:
        result = subprocess.run(test_cmd, capture_output=True, text=True, timeout=10, 
                              creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        if result.returncode == 0:
            update_progress(status='completed')
            return "NO_PASSWORD_NEEDED"
    except subprocess.TimeoutExpired:
        pass  # File probably needs password
    
    update_progress(status='cracking', charset=charset_name, max_length=max_length)
    
    # Try brute force
    for length in range(1, max_length + 1):
        update_progress(current_length=length)
        logger.info(f"Trying passwords of length {length} with charset: {charset_name}")
        
        for attempt in itertools.product(charset, repeat=length):
            if progress_data['status'] == 'stopped':
                return None
                
            password = ''.join(attempt)
            total_attempts += 1
            
            update_progress(attempts=total_attempts, current_password=password)
            
            if total_attempts % 1000 == 0:
                logger.info(f"Tried {total_attempts} passwords...")
            
            try:
                result = subprocess.run(password_cmd(password), 
                                      capture_output=True, text=True, timeout=10,
                                      creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                if result.returncode == 0:
                    logger.info(f"Password found: {password} (after {total_attempts} attempts)")
                    update_progress(found=True, password=password, status='completed')
                    return password
            except subprocess.TimeoutExpired:
                continue
            except Exception:
                continue
    
    update_progress(status='completed')
    return None

def brute_force_archive(file_path, max_length=DEFAULT_MAX_LENGTH, charset=DEFAULT_CHARSET):
    """Smart archive cracker that uses available tools with progress tracking"""
    file_ext = os.path.splitext(file_path)[1].lower()
    
    # Calculate total combinations
    total_combinations = calculate_total_combinations(max_length, charset)
    update_progress(total_combinations=total_combinations)
    
    if file_ext == '.zip':
        return brute_force_zip(file_path, max_length, charset)
    elif file_ext == '.rar':
        tools = check_rar_tools()
        if any(tools.values()):
            return brute_force_rar_with_tools(file_path, max_length, charset)
        else:
            error_msg = "RAR support requires 7z, unrar, or WinRAR. Please install one of these tools."
            update_progress(error=error_msg, status='error')
            raise Exception(error_msg)
    else:
        error_msg = f"Unsupported file format: {file_ext}"
        update_progress(error=error_msg, status='error')
        raise Exception(error_msg)

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

        # Get parameters from form data
        max_length = int(request.form.get('max_length', DEFAULT_MAX_LENGTH))
        charset_type = request.form.get('charset', 'alphanumeric')
        
        # Set charset based on selection
        if charset_type == 'digits':
            charset = string.digits
            charset_name = "digits (0-9)"
        elif charset_type == 'lowercase':
            charset = string.ascii_lowercase
            charset_name = "lowercase letters (a-z)"
        elif charset_type == 'uppercase':
            charset = string.ascii_uppercase
            charset_name = "uppercase letters (A-Z)"
        elif charset_type == 'letters':
            charset = string.ascii_letters
            charset_name = "letters (a-z, A-Z)"
        else:  # alphanumeric (default)
            charset = DEFAULT_CHARSET
            charset_name = DEFAULT_CHARSET_NAME

        # Validate max_length
        if max_length < 1 or max_length > 8:
            return jsonify({"error": "Max length must be between 1 and 8"}), 400

        # Create temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as temp_file:
            temp_path = temp_file.name
            file.save(temp_path)
        
        logger.info(f"Processing {file_ext.upper()} file: {file.filename}")
        logger.info(f"Parameters - Max length: {max_length}, Charset: {charset_name}")
        
        # Reset progress and start cracking
        reset_progress()
        update_progress(status='starting', max_length=max_length, charset=charset_name)
        
        # Run cracking in a separate thread to avoid blocking
        def crack_thread():
            try:
                password = brute_force_archive(temp_path, max_length, charset)
                
                # Clean up temporary file
                try:
                    os.unlink(temp_path)
                except Exception as e:
                    logger.warning(f"Failed to delete temporary file: {e}")
                
            except Exception as e:
                logger.error(f"Error processing request: {e}")
                update_progress(error=str(e), status='error')
                try:
                    os.unlink(temp_path)
                except:
                    pass
        
        # Start cracking thread
        threading.Thread(target=crack_thread, daemon=True).start()
        
        return jsonify({
            "message": "Cracking started. Use /progress endpoint to monitor progress.",
            "max_length": max_length,
            "charset": charset_name
        }), 200
        
    except Exception as e:
        logger.error(f"Error processing request: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/progress', methods=['GET'])
def get_progress():
    """Get current progress of password cracking"""
    with progress_lock:
        data = progress_data.copy()
        
        # Calculate speed if we have start time and attempts
        if data['start_time'] and data['attempts'] > 0:
            start_time = datetime.fromisoformat(data['start_time'])
            elapsed_seconds = (datetime.now() - start_time).total_seconds()
            if elapsed_seconds > 0:
                data['speed'] = round(data['attempts'] / elapsed_seconds, 2)
                # Estimate remaining time
                if data['total_combinations'] > 0 and data['attempts'] > 0:
                    remaining_attempts = data['total_combinations'] - data['attempts']
                    data['estimated_remaining'] = round(remaining_attempts / data['speed'], 2)
            else:
                data['speed'] = 0
                data['estimated_remaining'] = None
        else:
            data['speed'] = 0
            data['estimated_remaining'] = None
    
    return jsonify(data)

@app.route('/progress/stream', methods=['GET'])
def progress_stream():
    """Server-Sent Events endpoint for real-time progress updates"""
    def generate():
        yield "data: {}\n\n".format(json.dumps({"type": "connected"}))
        
        last_data = None
        while True:
            with progress_lock:
                current_data = progress_data.copy()
            
            # Only send updates if data has changed
            if current_data != last_data:
                # Calculate speed and remaining time
                if current_data['start_time'] and current_data['attempts'] > 0:
                    start_time = datetime.fromisoformat(current_data['start_time'])
                    elapsed_seconds = (datetime.now() - start_time).total_seconds()
                    if elapsed_seconds > 0:
                        current_data['speed'] = round(current_data['attempts'] / elapsed_seconds, 2)
                        if current_data['total_combinations'] > 0 and current_data['attempts'] > 0:
                            remaining_attempts = current_data['total_combinations'] - current_data['attempts']
                            current_data['estimated_remaining'] = round(remaining_attempts / current_data['speed'], 2)
                    else:
                        current_data['speed'] = 0
                        current_data['estimated_remaining'] = None
                else:
                    current_data['speed'] = 0
                    current_data['estimated_remaining'] = None
                
                yield "data: {}\n\n".format(json.dumps(current_data))
                last_data = current_data
            
            # Stop streaming if cracking is completed or errored
            if current_data['status'] in ['completed', 'error']:
                break
                
            time.sleep(0.1)  # Update every 100ms
    
    return Response(generate(), mimetype='text/event-stream')

@app.route('/stop', methods=['POST'])
def stop_cracking():
    """Stop the current cracking process"""
    update_progress(status='stopped')
    return jsonify({"message": "Cracking process stopped"}), 200

@app.route('/status', methods=['GET'])
def status():
    """Health check endpoint with tool information"""
    tools = check_rar_tools()
    return jsonify({
        "status": "running", 
        "message": "Advanced Archive Password Cracker API",
        "supported_formats": ["ZIP (native)", "RAR (requires external tools)"],
        "available_tools": tools,
        "current_progress": progress_data['status'],
        "default_max_length": DEFAULT_MAX_LENGTH,
        "default_charset": DEFAULT_CHARSET_NAME
    }), 200

@app.errorhandler(413)
def too_large(e):
    return jsonify({"error": "File too large"}), 413

@app.errorhandler(500)
def internal_error(e):
    logger.error(f"Internal server error: {e}")
    return jsonify({"error": "Internal server error"}), 500

if __name__ == '__main__':
    logger.info("Starting Advanced Archive Password Cracker API")
    
    # Check available tools
    tools = check_rar_tools()
    logger.info("Available tools:")
    for tool, available in tools.items():
        logger.info(f"  {tool}: {'✓' if available else '✗'}")
    
    logger.info("Configuration:")
    logger.info(f"  Default max password length: {DEFAULT_MAX_LENGTH}")
    logger.info(f"  Default character set: {DEFAULT_CHARSET_NAME}")
    logger.info(f"  ZIP support: Always available (pure Python)")
    logger.info(f"  RAR support: {'Available' if any(tools.values()) else 'Requires 7z/unrar/WinRAR'}")
    
    app.run(debug=True, host='0.0.0.0', port=5001)