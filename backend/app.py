from flask import Flask, request, jsonify
from flask_cors import CORS
import rarfile
import itertools
import string
import os
import tempfile
import logging

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Brute-force function with improved error handling
def brute_force_rar(rar_path, max_length=4, charset=string.digits):
    """
    Brute force RAR password using itertools
    
    Args:
        rar_path (str): Path to the RAR file
        max_length (int): Maximum password length to try
        charset (str): Character set to use for password generation
    
    Returns:
        str or None: Found password or None if not found
    """
    try:
        with rarfile.RarFile(rar_path) as rf:
            # Test if file is encrypted
            if not rf.needs_password():
                logger.info("RAR file is not password protected")
                return "NO_PASSWORD_NEEDED"
            
            total_attempts = 0
            for length in range(1, max_length + 1):
                logger.info(f"Trying passwords of length {length}")
                
                for attempt in itertools.product(charset, repeat=length):
                    password = ''.join(attempt)
                    total_attempts += 1
                    
                    try:
                        # Try to test the password without extracting
                        rf.setpassword(password)
                        # Test by trying to read file info
                        rf.testrar()
                        logger.info(f"Password found: {password} (after {total_attempts} attempts)")
                        return password
                    except rarfile.RarWrongPassword:
                        continue
                    except Exception as e:
                        logger.error(f"Unexpected error testing password '{password}': {e}")
                        continue
                        
            logger.info(f"Password not found after {total_attempts} attempts")
            return None
            
    except rarfile.RarCannotExec:
        logger.error("RAR executable not found. Please install WinRAR or 7-Zip")
        raise Exception("RAR executable not found. Please install WinRAR or 7-Zip")
    except Exception as e:
        logger.error(f"Error opening RAR file: {e}")
        raise Exception(f"Error opening RAR file: {e}")

@app.route('/crack', methods=['POST'])
def crack():
    """Handle RAR password cracking requests"""
    try:
        # Check if file was uploaded
        if 'file' not in request.files:
            return jsonify({"error": "No file uploaded"}), 400
        
        file = request.files['file']
        
        # Check if file was selected
        if file.filename == '':
            return jsonify({"error": "No file selected"}), 400
            
        # Check file extension
        if not file.filename.lower().endswith('.rar'):
            return jsonify({"error": "Only RAR files are supported"}), 400

        # Create temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.rar') as temp_file:
            temp_path = temp_file.name
            file.save(temp_path)
        
        logger.info(f"Processing RAR file: {file.filename}")
        
        # Attempt to crack the password
        password = brute_force_rar(temp_path)
        
        # Clean up temporary file
        try:
            os.unlink(temp_path)
        except Exception as e:
            logger.warning(f"Failed to delete temporary file: {e}")
        
        if password == "NO_PASSWORD_NEEDED":
            return jsonify({"message": "RAR file is not password protected"}), 200
        elif password:
            return jsonify({"password": password}), 200
        else:
            return jsonify({"error": "Password not found within the search space"}), 404
            
    except Exception as e:
        logger.error(f"Error processing request: {e}")
        # Clean up temporary file in case of error
        try:
            if 'temp_path' in locals():
                os.unlink(temp_path)
        except:
            pass
        return jsonify({"error": str(e)}), 500

@app.route('/status', methods=['GET'])
def status():
    """Health check endpoint"""
    return jsonify({"status": "running", "message": "RAR Password Cracker API"}), 200

@app.errorhandler(413)
def too_large(e):
    """Handle file too large error"""
    return jsonify({"error": "File too large"}), 413

@app.errorhandler(500)
def internal_error(e):
    """Handle internal server errors"""
    logger.error(f"Internal server error: {e}")
    return jsonify({"error": "Internal server error"}), 500

if __name__ == '__main__':
    logger.info("Starting RAR Password Cracker API")
    logger.info("Current configuration:")
    logger.info(f"  Max password length: 4")
    logger.info(f"  Character set: digits (0-9)")
    logger.info(f"  CORS enabled: Yes")
    
    app.run(debug=True, host='0.0.0.0', port=5001)