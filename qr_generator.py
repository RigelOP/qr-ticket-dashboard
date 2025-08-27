import qrcode
import os
import json

def generate_qr(data, output_folder="qrcodes", filename=None):
    """
    Generates a QR code in JSON format and saves it as a PNG.
    
    Args:
        data (dict or str): The data for this submission. If a dictionary is provided, it will be converted to a JSON string.
        output_folder (str): Folder where QR code images are saved
        filename (str): Optional filename for the QR code image. 
                        If None, defaults to 'qr.png'
    
    Returns:
        str: Filepath of the saved QR code image
    """
    os.makedirs(output_folder, exist_ok=True)
    
    # Prepare data for QR
    if isinstance(data, dict):
        qr_data = json.dumps(data)
    else:
        qr_data = data
    
    # Prepare filename
    if filename is None:
        filename = "qr.png"
    
    filepath = os.path.join(output_folder, filename)
    
    # Generate QR code and save
    img = qrcode.make(qr_data)
    img.save(filepath)
    
    return filepath
