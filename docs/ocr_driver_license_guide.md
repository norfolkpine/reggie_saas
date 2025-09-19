# OCR for Driver's License Scanning - Implementation Guide

This document provides guidance on implementing OCR (Optical Character Recognition) for driver's license scanning and text extraction in the Reggie SaaS application.

## Overview

While `pypdf` is excellent for PDFs with existing text layers, it does **not** support OCR for scanned documents or image-based PDFs. For driver's license scans and similar identification documents, specialized OCR solutions are required.

## Recommended OCR Solutions

### 1. **PaddleOCR** - **Best Overall Choice**

**Why it's ideal for driver's licenses:**
- Specifically designed for document OCR with excellent accuracy on structured documents
- High accuracy on ID cards and driver's licenses
- Supports multiple languages
- Good at handling rotated text and various layouts
- Built-in text detection and recognition
- Free and open-source

**Installation:**
```bash
pip install paddlepaddle paddleocr
```

**Basic Usage:**
```python
from paddleocr import PaddleOCR

# Initialize OCR
ocr = PaddleOCR(use_angle_cls=True, lang='en')

# Process image
result = ocr.ocr('driver_license.jpg', cls=True)

# Extract text
for idx in range(len(result)):
    res = result[idx]
    for line in res:
        print(line[1][0])  # Extracted text
```

### 2. **EasyOCR** - **Great Balance**

**Why it's good:**
- User-friendly with good accuracy on structured documents
- Easy to implement
- Good accuracy on driver's licenses
- Supports 80+ languages
- Handles various image qualities well

**Installation:**
```bash
pip install easyocr
```

**Basic Usage:**
```python
import easyocr

# Initialize reader
reader = easyocr.Reader(['en'])

# Process image
result = reader.readtext('driver_license.jpg')

# Extract text
for (bbox, text, confidence) in result:
    print(f"Text: {text}, Confidence: {confidence}")
```

### 3. **Tesseract + OpenCV** - **Most Flexible**

**Why it's useful:**
- Most mature and customizable
- Highly configurable
- Good preprocessing capabilities
- Can be fine-tuned for specific document types
- Extensive community support

**Installation:**
```bash
# Install Tesseract system package
# Ubuntu/Debian: sudo apt-get install tesseract-ocr
# macOS: brew install tesseract
# Windows: Download from GitHub

pip install pytesseract opencv-python
```

**Basic Usage:**
```python
import cv2
import pytesseract
from PIL import Image

# Load and preprocess image
image = cv2.imread('driver_license.jpg')
gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

# Apply OCR
text = pytesseract.image_to_string(gray, config='--psm 6')
print(text)
```

## Implementation Strategy

### Hybrid Approach (Recommended)

Implement a fallback mechanism that tries multiple OCR methods:

```python
def extract_driver_license_text(image_path, file_type=None):
    """
    Extract text from driver's license using hybrid approach:
    1. Try pypdf first (for PDFs with text layer)
    2. Fallback to OCR for scanned documents
    """
    
    # Check if it's a PDF with existing text layer
    if file_type == 'pdf' and has_text_layer(image_path):
        return extract_with_pypdf(image_path)
    
    # For images or scanned PDFs, use OCR
    try:
        # Primary: PaddleOCR for best accuracy
        return extract_with_paddleocr(image_path)
    except Exception as e:
        print(f"PaddleOCR failed: {e}")
        try:
            # Fallback: EasyOCR
            return extract_with_easyocr(image_path)
        except Exception as e:
            print(f"EasyOCR failed: {e}")
            # Last resort: Tesseract
            return extract_with_tesseract(image_path)

def has_text_layer(pdf_path):
    """Check if PDF has extractable text layer"""
    try:
        import pypdf
        with open(pdf_path, 'rb') as file:
            reader = pypdf.PdfReader(file)
            for page in reader.pages:
                if page.extract_text().strip():
                    return True
        return False
    except:
        return False

def extract_with_paddleocr(image_path):
    """Extract text using PaddleOCR"""
    from paddleocr import PaddleOCR
    
    ocr = PaddleOCR(use_angle_cls=True, lang='en')
    result = ocr.ocr(image_path, cls=True)
    
    extracted_text = []
    for idx in range(len(result)):
        res = result[idx]
        for line in res:
            if line[1][1] > 0.5:  # Confidence threshold
                extracted_text.append(line[1][0])
    
    return "\n".join(extracted_text)

def extract_with_easyocr(image_path):
    """Extract text using EasyOCR"""
    import easyocr
    
    reader = easyocr.Reader(['en'])
    result = reader.readtext(image_path)
    
    extracted_text = []
    for (bbox, text, confidence) in result:
        if confidence > 0.5:  # Confidence threshold
            extracted_text.append(text)
    
    return "\n".join(extracted_text)

def extract_with_tesseract(image_path):
    """Extract text using Tesseract"""
    import cv2
    import pytesseract
    from PIL import Image
    
    # Load and preprocess image
    image = cv2.imread(image_path)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    
    # Apply additional preprocessing for better results
    gray = cv2.medianBlur(gray, 3)
    gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    
    # Extract text
    text = pytesseract.image_to_string(gray, config='--psm 6')
    return text
```

## Image Preprocessing for Better OCR Results

### Essential Preprocessing Steps

```python
import cv2
import numpy as np

def preprocess_driver_license(image_path):
    """
    Preprocess driver's license image for better OCR accuracy
    """
    # Load image
    image = cv2.imread(image_path)
    
    # Convert to grayscale
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    
    # Noise reduction
    denoised = cv2.medianBlur(gray, 3)
    
    # Contrast enhancement
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
    enhanced = clahe.apply(denoised)
    
    # Binarization
    binary = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    
    # Morphological operations to clean up
    kernel = np.ones((1,1), np.uint8)
    cleaned = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    
    return cleaned

def correct_perspective(image):
    """
    Correct perspective distortion in driver's license image
    """
    # This is a simplified example - in practice, you'd need
    # to detect the license boundaries and apply perspective correction
    height, width = image.shape[:2]
    
    # Define source and destination points for perspective correction
    # (These would be detected automatically in a real implementation)
    src_points = np.float32([[0, 0], [width, 0], [width, height], [0, height]])
    dst_points = np.float32([[0, 0], [width, 0], [width, height], [0, height]])
    
    # Calculate perspective transformation matrix
    matrix = cv2.getPerspectiveTransform(src_points, dst_points)
    
    # Apply perspective correction
    corrected = cv2.warpPerspective(image, matrix, (width, height))
    
    return corrected
```

## Driver's License Specific Data Extraction

### Structured Data Parsing

```python
import re
from datetime import datetime

def parse_driver_license_data(extracted_text):
    """
    Parse structured data from driver's license text
    """
    data = {}
    
    # Common patterns for driver's license fields
    patterns = {
        'license_number': r'(?:DL|LIC|LICENSE|ID)\s*#?\s*:?\s*([A-Z0-9\s-]+)',
        'name': r'(?:NAME|FULL NAME)\s*:?\s*([A-Z\s,.-]+)',
        'date_of_birth': r'(?:DOB|DATE OF BIRTH|BIRTH)\s*:?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
        'expiration': r'(?:EXP|EXPIRES|EXPIRATION)\s*:?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
        'address': r'(?:ADDRESS|ADDR)\s*:?\s*([A-Z0-9\s,.-]+)',
        'state': r'(?:STATE)\s*:?\s*([A-Z]{2})',
    }
    
    for field, pattern in patterns.items():
        match = re.search(pattern, extracted_text, re.IGNORECASE)
        if match:
            data[field] = match.group(1).strip()
    
    return data

def validate_driver_license_data(data):
    """
    Validate extracted driver's license data
    """
    validation_results = {}
    
    # Validate license number format (varies by state)
    if 'license_number' in data:
        license_num = data['license_number'].replace(' ', '').replace('-', '')
        validation_results['license_number_valid'] = len(license_num) >= 6
    
    # Validate date formats
    if 'date_of_birth' in data:
        try:
            dob = datetime.strptime(data['date_of_birth'], '%m/%d/%Y')
            validation_results['dob_valid'] = dob < datetime.now()
        except:
            validation_results['dob_valid'] = False
    
    if 'expiration' in data:
        try:
            exp = datetime.strptime(data['expiration'], '%m/%d/%Y')
            validation_results['expiration_valid'] = exp > datetime.now()
        except:
            validation_results['expiration_valid'] = False
    
    return validation_results
```

## Integration with Existing FileReaderTools

### Enhanced FileReaderTools Implementation

```python
# Add to apps/reggie/agents/tools/filereader.py

class EnhancedFileReaderTools(FileReaderTools):
    def __init__(self):
        super().__init__()
        self.register(self.read_file_with_ocr)
    
    def read_file_with_ocr(
        self, 
        content: bytes, 
        file_type: str | None = None, 
        file_name: str | None = None, 
        max_chars: int = 20000,
        enable_ocr: bool = True
    ) -> str:
        """
        Enhanced file reading with OCR fallback for scanned documents
        """
        # First try standard text extraction
        try:
            text = self.read_file(content, file_type, file_name, max_chars)
            
            # If we got minimal text and OCR is enabled, try OCR
            if enable_ocr and len(text.strip()) < 100:
                return self._extract_with_ocr(content, file_type, file_name, max_chars)
            
            return text
            
        except Exception as e:
            if enable_ocr:
                return self._extract_with_ocr(content, file_type, file_name, max_chars)
            raise e
    
    def _extract_with_ocr(self, content: bytes, file_type: str, file_name: str, max_chars: int) -> str:
        """Extract text using OCR methods"""
        # Convert PDF to image if needed
        if file_type == 'pdf':
            image_path = self._convert_pdf_to_image(content)
        else:
            image_path = self._save_bytes_to_temp_image(content, file_name)
        
        try:
            # Try PaddleOCR first
            return self._extract_with_paddleocr(image_path, max_chars)
        except Exception as e:
            print(f"PaddleOCR failed: {e}")
            try:
                # Fallback to EasyOCR
                return self._extract_with_easyocr(image_path, max_chars)
            except Exception as e:
                print(f"EasyOCR failed: {e}")
                # Last resort: Tesseract
                return self._extract_with_tesseract(image_path, max_chars)
        finally:
            # Clean up temporary files
            if os.path.exists(image_path):
                os.unlink(image_path)
```

## Security and Compliance Considerations

### Data Protection
- **Encryption**: Encrypt sensitive data at rest and in transit
- **Access Control**: Implement proper authentication and authorization
- **Data Retention**: Follow applicable data retention policies
- **Audit Logging**: Log all access to sensitive data

### Privacy Compliance
- **GDPR**: Ensure compliance with European data protection regulations
- **CCPA**: Follow California Consumer Privacy Act requirements
- **PII Handling**: Implement proper handling of personally identifiable information
- **Data Minimization**: Only extract and store necessary information

## Performance Optimization

### Caching and Optimization
```python
# Implement caching for OCR models
from functools import lru_cache

@lru_cache(maxsize=1)
def get_ocr_model():
    """Cache OCR model initialization"""
    from paddleocr import PaddleOCR
    return PaddleOCR(use_angle_cls=True, lang='en')

# Batch processing for multiple documents
def process_multiple_documents(file_paths):
    """Process multiple documents efficiently"""
    ocr = get_ocr_model()
    results = []
    
    for file_path in file_paths:
        try:
            result = ocr.ocr(file_path, cls=True)
            results.append(process_ocr_result(result))
        except Exception as e:
            results.append(f"Error processing {file_path}: {e}")
    
    return results
```

## Testing and Validation

### OCR Accuracy Testing
```python
def test_ocr_accuracy(test_images, expected_texts):
    """Test OCR accuracy against known samples"""
    results = []
    
    for image_path, expected in test_images:
        extracted = extract_driver_license_text(image_path)
        accuracy = calculate_text_similarity(extracted, expected)
        results.append({
            'image': image_path,
            'accuracy': accuracy,
            'extracted': extracted,
            'expected': expected
        })
    
    return results

def calculate_text_similarity(text1, text2):
    """Calculate similarity between two text strings"""
    from difflib import SequenceMatcher
    return SequenceMatcher(None, text1.lower(), text2.lower()).ratio()
```

## Dependencies

Add these to your `requirements.txt`:

```txt
# OCR Dependencies
paddlepaddle>=2.4.0
paddleocr>=2.6.0
easyocr>=1.6.0
pytesseract>=0.3.10
opencv-python>=4.5.0

# Image processing
Pillow>=9.0.0
numpy>=1.21.0

# PDF to image conversion
pdf2image>=1.16.0
```

## Conclusion

Implementing OCR for driver's license scanning requires:

1. **Choosing the right OCR library** (PaddleOCR recommended)
2. **Implementing proper preprocessing** for better accuracy
3. **Adding structured data parsing** for driver's license fields
4. **Ensuring security and compliance** with data protection regulations
5. **Testing thoroughly** with various document types and qualities

The hybrid approach ensures maximum compatibility while providing the best possible text extraction for both regular PDFs and scanned documents.
